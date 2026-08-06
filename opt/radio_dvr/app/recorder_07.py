import os
import time
import uuid
import signal
import subprocess
import threading
from pathlib import Path

import requests

from app.logger import get_logger
from app.settings import DATA_DIR
from app.timezone import now_peru

logger = get_logger("recorder")


class RadioRecorder:
    """
    Motor DVR de grabación para una emisora de radio.
    Versión requests+Session: maneja cookies, redirecciones 302, headers
    realistas y reintentos ante fallos del CDN.
    """

    def __init__(self, station: dict):
        self.station = station
        self.process = None
        self._download_thread = None
        self._stop_event = None
        self._download_session = None

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
    # Descarga del stream (núcleo requests + cookies + reintentos)
    # ---------------------------------------------------------
    def _download_stream(self):
        """
        Thread worker: realiza la petición inicial, captura cookies,
        sigue el 302 al CDN y escribe el stream en bloques de 8KB.
        Incluye reintentos si el CDN no responde inicialmente.
        """
        url = self.station["url"]
        referer = self.station.get("referer", "https://www.emisorasco.com/")
        origin = self.station.get("origin", "https://www.emisorasco.com")

        # Asegurar que el archivo AAC exista desde el inicio (incluso si está vacío)
        self.aac_file = self.wav_directory / "recording.aac"

        # --- Sesión HTTP con headers realistas ---
        self._download_session = requests.Session()
        self._download_session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Referer": referer,
            "Origin": origin,
            "Connection": "keep-alive",
        })

        stream_url = None

        try:
            # ── PASO 1: Petición inicial (captura cookies + redirección) ──
            logger.info(f"[Session] Petición inicial a {url[:60]}...")
            r1 = self._download_session.get(
                url,
                allow_redirects=False,
                timeout=(30, 30),  # 30s para conectar, 30s para leer respuesta
                stream=False,
            )

            logger.info(f"[Session] Status inicial: {r1.status_code}")
            for cookie in self._download_session.cookies:
                logger.info(f"[Session] Cookie recibida: {cookie.name}")

            if r1.status_code in (301, 302, 307, 308):
                stream_url = r1.headers.get("Location")
                if not stream_url:
                    logger.error("[Session] Redirección 302 sin header Location")
                    return
                logger.info(f"[Session] Redirección a CDN: {stream_url[:80]}...")
            elif r1.status_code == 200:
                stream_url = url
                logger.info("[Session] Stream directo (sin redirección)")
            else:
                logger.error(f"[Session] Status inesperado: {r1.status_code}")
                return

            # ── PASO 2: Stream desde el CDN con cookies (con reintentos) ──
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                if self._stop_event.is_set():
                    logger.info("[Session] Stop solicitado antes de conectar al CDN.")
                    return

                try:
                    logger.info(f"[Session] Intento {attempt}/{max_retries} conectando al CDN...")
                    r2 = self._download_session.get(
                        stream_url,
                        stream=True,
                        timeout=(30, 60),  # 30s conectar, 60s entre chunks
                        headers={"Referer": "https://mdstrm.com/"},
                    )

                    if r2.status_code != 200:
                        logger.error(f"[Session] CDN respondió HTTP {r2.status_code}")
                        if attempt < max_retries:
                            wait = 5 * attempt
                            logger.info(f"[Session] Reintentando en {wait}s...")
                            time.sleep(wait)
                            continue
                        return

                    # ── PASO 3: Escribir chunks al disco ──
                    logger.info(f"[Session] Conexión establecida. Grabando a: {self.aac_file.name}")
                    bytes_written = 0
                    last_chunk_time = time.time()

                    with open(self.aac_file, "wb") as f:
                        for chunk in r2.iter_content(chunk_size=8192):
                            if self._stop_event.is_set():
                                logger.info("[Session] Stop solicitado. Cerrando stream...")
                                break

                            if chunk:
                                f.write(chunk)
                                bytes_written += len(chunk)
                                last_chunk_time = time.time()

                            # Safety check: si no llega nada en 90s, romper y reintentar
                            if time.time() - last_chunk_time > 90:
                                logger.warning("[Session] 90s sin recibir datos. Posible corte del CDN.")
                                break

                    logger.info(
                        f"[Session] Descarga finalizada. Total: {bytes_written / 1024:.1f} KB"
                    )

                    # Si escribimos algo, salimos del loop de reintentos
                    if bytes_written > 0:
                        return
                    elif attempt < max_retries:
                        logger.info(f"[Session] 0 bytes recibidos. Reintentando...")
                        time.sleep(5 * attempt)

                except requests.exceptions.Timeout as exc:
                    logger.error(f"[Session] Timeout en intento {attempt}: {exc}")
                    if attempt < max_retries:
                        wait = 5 * attempt
                        logger.info(f"[Session] Reintentando en {wait}s...")
                        time.sleep(wait)
                    else:
                        logger.error("[Session] Agotados todos los reintentos por timeout.")
                except requests.exceptions.RequestException as exc:
                    logger.error(f"[Session] Error de red en intento {attempt}: {exc}")
                    if attempt < max_retries:
                        time.sleep(5 * attempt)
                    else:
                        raise

        except Exception:
            logger.exception("[Session] Error inesperado durante la descarga")
        finally:
            if self._download_session:
                self._download_session.close()
                self._download_session = None
            logger.info("[Session] Sesión cerrada.")

    # ---------------------------------------------------------
    # ffmpeg (conversión post-grabación)
    # ---------------------------------------------------------
    def convert_to_wav(self):
        if not self.aac_file or not self.aac_file.exists():
            logger.error("No existe archivo AAC para convertir.")
            return False

        # Si el archivo está vacío, no tiene sentido convertir
        if self.aac_file.stat().st_size == 0:
            logger.error("El archivo AAC existe pero está vacío (0 bytes).")
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

            self._stop_event = threading.Event()
            self._download_thread = threading.Thread(
                target=self._download_stream,
                daemon=True,
                name=f"Recorder-{self.station['nombre']}"
            )

            logger.info(
                f"Iniciando sesión {self.session_id} para {self.station['nombre']}"
            )

            self._download_thread.start()
            time.sleep(3)

            if not self._download_thread.is_alive():
                logger.error("El thread de descarga terminó inmediatamente después de iniciar.")
                self._release_lock()
                self._download_thread = None
                self._stop_event = None
                return False

            logger.info(f"Descarga iniciada correctamente (session={self.session_id})")
            return True

        except Exception:
            logger.exception("Error iniciando la grabación.")
            self._release_lock()
            self._download_thread = None
            self._stop_event = None
            return False

    def stop(self):
        if self._stopping:
            return True

        self._stopping = True

        try:
            if self._download_thread is not None and self._download_thread.is_alive():
                logger.info(f"Deteniendo descarga de sesión {self.session_id}")
                self._stop_event.set()

                self._download_thread.join(timeout=30)

                if self._download_thread.is_alive():
                    logger.warning(
                        "El thread de descarga no respondió al stop dentro de 30s."
                    )

                logger.info("Descarga detenida.")

            # Conversión post-grabación
            self.convert_to_wav()

            return True
        except Exception:
            logger.exception("Error deteniendo la grabación.")
            return False
        finally:
            self.process = None
            self._download_thread = None
            self._stop_event = None
            self.start_time = None
            self.session_id = None
            self._release_lock()
            self._stopping = False

    # ---------------------------------------------------------
    # Estado
    # ---------------------------------------------------------
    def is_running(self):
        return self._download_thread is not None and self._download_thread.is_alive()

    def get_status(self):
        return {
            "station": self.station["nombre"],
            "running": self.is_running(),
            "pid": os.getpid(),
            "session_id": self.session_id,
            "started_at": self.start_time.isoformat() if self.start_time else None,
            "session_directory": str(self.session_directory) if self.session_directory else None,
        }