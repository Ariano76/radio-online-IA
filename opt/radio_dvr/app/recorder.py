# ---------------------------------------------------------
# Version recorder.py que maneja la grabación de una emisora de radio usando FFmpeg
# funcionando al 100% desde una VPS comercial como la de Oracle.
# Se hicieron ajustes para que toda la transmision se grabe como un solo archivo WAV y posteriormente se dividira en segmentos de 30 minutos para evitar bloqueos del CDN.
# ---------------------------------------------------------

import os
import time
import uuid
import signal
import subprocess
from pathlib import Path

from app.logger import get_logger
from app.settings import DATA_DIR
from app.timezone import now_peru

logger = get_logger("recorder")

class RadioRecorder:
    """
    Motor DVR de grabación para una emisora de radio.
    Versión VPS-friendly: grabación continua por bloque para evitar
    bloqueos del CDN por detección de segmentación.
    """

    def __init__(self, station: dict):
        self.station = station
        self.process = None
        self.session_id = None
        self.start_time = None
        self.session_directory = None
        self.wav_directory = None
        self.lock_file = None
        self._stopping = False

        self.env = os.environ.copy()
        self.env["TZ"] = "America/Lima"

    # ---------------------------------------------------------
    # Directorios
    # ---------------------------------------------------------
    def _create_session_directory(self):
        now = now_peru()
        session_name = now.strftime("session_%Y%m%d_%H%M%S")
        self.session_directory = (
            DATA_DIR
            / self.station["nombre"]
            / now.strftime("%Y")
            / now.strftime("%m")
            / now.strftime("%d")
            / session_name
        )
        self.wav_directory = self.session_directory / "wav"
        self.wav_directory.mkdir(parents=True, exist_ok=True)

    def current_wav_directory(self):
        return self.wav_directory

    def current_segment(self):
        """
        Devuelve el archivo de grabación continua actual.
        """
        if self.wav_directory is None:
            return None

        recording = self.wav_directory / "recording.wav"
        if recording.exists():
            return recording

        return None

    # ---------------------------------------------------------
    # Lock
    # ---------------------------------------------------------
    def _lock_directory(self):
        run_dir = DATA_DIR.parent / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _acquire_lock(self):
        self.lock_file = (
            self._lock_directory()
            / f"{self.station['nombre']}.pid"
        )

        if self.lock_file.exists():
            try:
                pid = int(self.lock_file.read_text().strip())
                os.kill(pid, 0)
                raise RuntimeError(
                    f"Ya existe una grabación activa para {self.station['nombre']} (PID={pid})"
                )
            except ProcessLookupError:
                logger.warning("Se encontró un lock huérfano. Eliminándolo.")
                self.lock_file.unlink()
            except ValueError:
                self.lock_file.unlink()

        self.lock_file.write_text(str(os.getpid()))

    def _release_lock(self):
        if self.lock_file and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except Exception:
                logger.exception("No fue posible eliminar el archivo PID.")

    # ---------------------------------------------------------
    # FFmpeg
    # ---------------------------------------------------------
    def build_ffmpeg_command(self):
        sample_rate = self.station["sample_rate"]
        channels = self.station["channels"]

        # Grabación continua en un único archivo WAV por bloque
        output_file = self.wav_directory / "recording.wav"

        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_on_network_error", "1",
            "-reconnect_on_http_error", "4xx,5xx",
            "-reconnect_delay_max", "15",
            "-rw_timeout", "15000000",
            "-thread_queue_size", "1024",
            "-i", self.station["url"],
            "-ac", str(channels),
            "-ar", str(sample_rate),
            "-c:a", "pcm_s16le",
            "-f", "wav",
            str(output_file),
        ]

    # ---------------------------------------------------------
    # Ciclo de vida
    # ---------------------------------------------------------
    """"
    def start(self):
        required = ["nombre", "url", "segmento_minutos", "sample_rate", "channels"]
        for field in required:
            if field not in self.station:
                raise ValueError(
                    f"Falta el parámetro '{field}' en la configuración de la emisora."
                )

        if self.is_running():
            logger.warning(f"La emisora {self.station['nombre']} ya está grabando.")
            return False

        try:
            self._acquire_lock()
            self.session_id = str(uuid.uuid4())
            self.start_time = now_peru()
            self._create_session_directory()
            command = self.build_ffmpeg_command()

            logger.info(
                f"Iniciando sesión {self.session_id} para {self.station['nombre']}"
            )

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self.env,
            )

            time.sleep(3)

            if self.process.poll() is not None:
                logger.error("FFmpeg terminó inmediatamente después de iniciar.")
                self._release_lock()
                self.process = None
                return False

            logger.info(f"FFmpeg iniciado correctamente (PID={self.process.pid})")
            return True

        except Exception:
            logger.exception("Error iniciando la grabación.")
            self._release_lock()
            self.process = None
            return False
    """

    def start(self):
        required = ["nombre", "url", "segmento_minutos", "sample_rate", "channels"]
        for field in required:
            if field not in self.station:
                raise ValueError(
                    f"Falta el parámetro '{field}' en la configuración de la emisora."
                )

        if self.is_running():
            logger.warning(f"La emisora {self.station['nombre']} ya está grabando.")
            return False

        try:
            self._acquire_lock()
            self.session_id = str(uuid.uuid4())
            self.start_time = now_peru()
            self._create_session_directory()
            command = self.build_ffmpeg_command()

            # LOG DE FFMPEG PARA DIAGNÓSTICO
            ffmpeg_log_path = self.session_directory / "ffmpeg.log"
            self.ffmpeg_log = open(ffmpeg_log_path, "w")

            logger.info(
                f"Iniciando sesión {self.session_id} para {self.station['nombre']}"
            )
            logger.debug(f"Comando FFmpeg: {' '.join(command)}")

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=self.ffmpeg_log,
                env=self.env,
            )

            time.sleep(3)

            if self.process.poll() is not None:
                logger.error("FFmpeg terminó inmediatamente después de iniciar.")
                self.ffmpeg_log.close()
                self._release_lock()
                self.process = None
                return False

            logger.info(f"FFmpeg iniciado correctamente (PID={self.process.pid})")
            return True

        except Exception:
            logger.exception("Error iniciando la grabación.")
            if hasattr(self, 'ffmpeg_log') and self.ffmpeg_log:
                self.ffmpeg_log.close()
            self._release_lock()
            self.process = None
            return False


    def stop(self):
        if self._stopping:
            return True

        self._stopping = True

        try:
            if self.process is not None and self.process.poll() is None:
                logger.info(f"Deteniendo sesión {self.session_id}")
                try:
                    self.process.send_signal(signal.SIGINT)
                    self.process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg no respondió; enviando SIGKILL.")
                    self.process.kill()
                    self.process.wait(timeout=5)
                except ProcessLookupError:
                    pass
                logger.info("Grabación detenida correctamente.")

            return True
        except Exception:
            logger.exception("Error deteniendo FFmpeg.")
            return False
        finally:
            self.process = None
            self.start_time = None
            self.session_id = None
            self._release_lock()
            self._stopping = False

            # Cerrar log de FFmpeg
            # Implementado para encontrar el problema en el VPS, 
            # solucionado se puede eliminar esta parte
            if hasattr(self, 'ffmpeg_log') and self.ffmpeg_log:
                try:
                    self.ffmpeg_log.close()
                except Exception:
                    pass

    # ---------------------------------------------------------
    # Estado
    # ---------------------------------------------------------
    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def get_status(self):
        return {
            "station": self.station["nombre"],
            "running": self.is_running(),
            "pid": self.process.pid if self.process else None,
            "session_id": self.session_id,
            "started_at": self.start_time.isoformat() if self.start_time else None,
            "session_directory": str(self.session_directory) if self.session_directory else None,
        }