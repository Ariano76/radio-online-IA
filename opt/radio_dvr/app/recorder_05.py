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
    Versión VPS-friendly: usa curl (OpenSSL) para descargar el stream,
    y ffmpeg local para convertir a WAV al finalizar el bloque.
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
        self.aac_file = None

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
    # curl (descarga del stream)
    # ---------------------------------------------------------
    def build_curl_command(self):
        self.aac_file = self.wav_directory / "recording.aac"

        return [
            "curl",
            "-s",                       # Silencioso
            "-L",                       # Seguir redirects
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "--connect-timeout", "15",
            "--max-time", "0",          # Sin límite de tiempo (bloque completo)
            "-o", str(self.aac_file),   # Archivo de salida
            self.station["url"],
        ]

    # ---------------------------------------------------------
    # ffmpeg (conversión post-grabación)
    # ---------------------------------------------------------
    def convert_to_wav(self):
        if not self.aac_file or not self.aac_file.exists():
            logger.error("No existe archivo AAC para convertir.")
            return False

        wav_file = self.wav_directory / "recording.wav"

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-i", str(self.aac_file),
            "-ac", str(self.station["channels"]),
            "-ar", str(self.station["sample_rate"]),
            "-c:a", "pcm_s16le",
            "-f", "wav",
            str(wav_file),
        ]

        try:
            logger.info(f"Convirtiendo {self.aac_file.name} a WAV...")
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=300,
            )
            if result.returncode == 0:
                logger.info(f"Conversión exitosa: {wav_file.name}")
                # Opcional: eliminar AAC original para ahorrar espacio
                # self.aac_file.unlink()
                return True
            else:
                logger.error(f"FFmpeg devolvió código {result.returncode}")
                return False
        except Exception:
            logger.exception("Error en conversión FFmpeg.")
            return False

    # ---------------------------------------------------------
    # Ciclo de vida
    # ---------------------------------------------------------
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
            command = self.build_curl_command()

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
                logger.error("curl terminó inmediatamente después de iniciar.")
                self._release_lock()
                self.process = None
                return False

            logger.info(f"curl iniciado correctamente (PID={self.process.pid})")
            return True

        except Exception:
            logger.exception("Error iniciando la grabación.")
            self._release_lock()
            self.process = None
            return False

    def stop(self):
        if self._stopping:
            return True

        self._stopping = True

        try:
            if self.process is not None and self.process.poll() is None:
                logger.info(f"Deteniendo descarga de sesión {self.session_id}")
                try:
                    self.process.send_signal(signal.SIGINT)
                    self.process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    logger.warning("curl no respondió; enviando SIGKILL.")
                    self.process.kill()
                    self.process.wait(timeout=5)
                except ProcessLookupError:
                    pass
                logger.info("Descarga detenida correctamente.")

            # Conversión post-grabación
            self.convert_to_wav()

            return True
        except Exception:
            logger.exception("Error deteniendo la grabación.")
            return False
        finally:
            self.process = None
            self.start_time = None
            self.session_id = None
            self._release_lock()
            self._stopping = False

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