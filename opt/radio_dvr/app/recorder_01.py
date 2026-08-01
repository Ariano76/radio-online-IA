import os
import time
import uuid
import signal
import atexit
import subprocess
from pathlib import Path

from app.logger import get_logger
from app.settings import DATA_DIR
from app.timezone import now_peru

logger = get_logger("recorder")

class RadioRecorder:
    """
    Motor DVR de grabación para una emisora de radio.

    Responsabilidades:
    - Crear una sesión de grabación.
    - Construir el comando FFmpeg.
    - Iniciar FFmpeg.
    - Detener FFmpeg.
    - Exponer el estado del proceso.

    Este módulo NO administra:
    - Base de datos.
    - Conversión MP3.
    - Watchdog.
    - Scheduler.
    - WhisperX.
    - Manifest JSON.
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

        atexit.register(self.cleanup)

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, self._signal_handler)

    # ---------------------------------------------------------
    # Manejo de señales
    # ---------------------------------------------------------

    def _signal_handler(self, signum, frame):
        logger.info(
            f"Señal recibida: {signum}. Finalizando grabación..."
        )
        self.stop()

    def cleanup(self):
        self.stop()

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

        files = sorted(self.wav_directory.glob("*.wav"))

        if not files:
            return None

        return files[-1]

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

                logger.warning(
                    "Se encontró un lock huérfano. Eliminándolo."
                )

                self.lock_file.unlink()

            except ValueError:

                self.lock_file.unlink()

        self.lock_file.write_text(str(os.getpid()))

    def _release_lock(self):

        if self.lock_file and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except Exception:
                logger.exception(
                    "No fue posible eliminar el archivo PID."
                )

    # ---------------------------------------------------------
    # FFmpeg
    # ---------------------------------------------------------

    def build_ffmpeg_command(self):

        segment_seconds = self.station["segmento_minutos"] * 60

        sample_rate = self.station["sample_rate"]

        channels = self.station["channels"]

        output_pattern = self.wav_directory / "%H%M%S.wav"

        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
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
            "-f", "segment",
            "-segment_time", str(segment_seconds),
            "-segment_atclocktime", "1",
            "-strftime", "1",
            "-reset_timestamps", "1",
            str(output_pattern),
        ]

    # ---------------------------------------------------------
    # Ciclo de vida
    # ---------------------------------------------------------

    def start(self):

        if self.is_running():

            required = [
                "nombre",
                "url",
                "segmento_minutos",
                "sample_rate",
                "channels"
                ]

            for field in required:
                if field not in self.station:
                    raise ValueError(
                        f"Falta el parámetro '{field}' en la configuración de la emisora."
                    )

            logger.warning(
                f"La emisora {self.station['nombre']} ya está grabando."
            )
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

                logger.error(
                    "FFmpeg terminó inmediatamente después de iniciar."
                )

                self._release_lock()
                self.process = None

                return False

            logger.info(
                f"FFmpeg iniciado correctamente (PID={self.process.pid})"
            )

            return True

        except Exception:

            logger.exception(
                "Error iniciando la grabación."
            )

            self._release_lock()

            self.process = None

            return False

    def stop(self):

        if self._stopping:
            return True

        self._stopping = True

        try:

            if self.process is not None:

                if self.process.poll() is None:

                    logger.info(
                        f"Deteniendo sesión {self.session_id}"
                    )

                    try:

                        self.process.send_signal(signal.SIGINT)

                        self.process.wait(timeout=20)

                    except subprocess.TimeoutExpired:

                        logger.warning(
                            "FFmpeg no respondió; enviando SIGKILL."
                        )

                        self.process.kill()

                        self.process.wait(timeout=5)

                    except ProcessLookupError:
                        pass

                    logger.info(
                        "Grabación detenida correctamente."
                    )

            return True

        except Exception:

            logger.exception(
                "Error deteniendo FFmpeg."
            )

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

        return (
            self.process is not None
            and self.process.poll() is None
        )

    def get_status(self):

        return {
            "station": self.station["nombre"],
            "running": self.is_running(),
            "pid": (
                self.process.pid
                if self.process
                else None
            ),
            "session_id": self.session_id,
            "started_at": (
                self.start_time.isoformat()
                if self.start_time
                else None
            ),
            "session_directory": (
                str(self.session_directory)
                if self.session_directory
                else None
            ),
        }