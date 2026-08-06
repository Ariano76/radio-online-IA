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
    Versión robusta: ciclo de reintentos INDEPENDIENTE (cada intento refresca
    cookies y URL del CDN desde cero), lock auto-liberante ante fallos del thread,
    timeout generoso para el primer chunk, y fallback a curl.
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
        self._lock_owned_by_thread = False
        self._failed = False
        self._fail_reason = None
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
    # Lock (robusto contra huérfanos)
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

                # Verificar que el PID realmente pertenezca a nuestro scheduler
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as f:
                        cmdline = f.read().decode("utf-8", errors="replace").replace("\x00", " ")
                    if "python" not in cmdline.lower() and "scheduler" not in cmdline.lower():
                        logger.warning(
                            f"Lock huérfano detectado: PID={pid} no es el scheduler "
                            f"(cmdline: {cmdline[:60]}...). Eliminando."
                        )
                        self.lock_file.unlink()
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    logger.warning("Se encontró un lock huérfano. Eliminándolo.")
                    self.lock_file.unlink()

            except ProcessLookupError:
                logger.warning("Se encontró un lock huérfano. Eliminándolo.")
                self.lock_file.unlink()
            except ValueError:
                self.lock_file.unlink()

        self.lock_file.write_text(str(os.getpid()))

    def _release_lock(self):
        if self.lock_file and self.lock_file.exists():
            try:
                current_pid = str(os.getpid())
                stored_pid = self.lock_file.read_text().strip()
                if stored_pid == current_pid:
                    self.lock_file.unlink()
                else:
                    logger.warning(
                        f"No se eliminó el lock: PID almacenado ({stored_pid}) != "
                        f"PID actual ({current_pid})"
                    )
            except Exception:
                logger.exception("No fue posible eliminar el archivo PID.")

    # ---------------------------------------------------------
    # Descarga del stream (ciclos de reintentos independientes)
    # ---------------------------------------------------------
    def _download_stream(self):
        """
        Thread worker: realiza hasta 3 ciclos de reintentos INDEPENDIENTES.
        Cada ciclo crea una Session nueva, obtiene cookies frescas y una
        URL de CDN fresca. Si todos fallan, intenta 1 fallback con curl.
        """
        url = self.station["url"]
        referer = self.station.get("referer", "https://www.emisorasco.com/")
        origin = self.station.get("origin", "https://www.emisorasco.com")

        self.aac_file = self.wav_directory / "recording.aac"
        success = False
        self._lock_owned_by_thread = True

        try:
            # ── CICLO DE REINTENTOS CON REQUESTS (máx 3) ──
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                if self._stop_event.is_set():
                    logger.info("[Session] Stop solicitado antes de conectar.")
                    return

                session = None
                try:
                    logger.info(f"[Session] === Intento {attempt}/{max_attempts} ===")
                    session = requests.Session()
                    session.headers.update({
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

                    # PASO A: Petición inicial a mdstrm.com (cookies + redirect)
                    logger.info(f"[Session] Petición inicial a {url[:60]}...")
                    r1 = session.get(
                        url,
                        allow_redirects=False,
                        timeout=(30, 30),
                        stream=False,
                    )

                    logger.info(f"[Session] Status inicial: {r1.status_code}")
                    for cookie in session.cookies:
                        logger.info(f"[Session] Cookie: {cookie.name}")

                    if r1.status_code in (301, 302, 307, 308):
                        stream_url = r1.headers.get("Location")
                        if not stream_url:
                            logger.error("[Session] 302 sin header Location")
                            continue
                        logger.info(f"[Session] CDN: {stream_url[:80]}...")
                    elif r1.status_code == 200:
                        stream_url = url
                        logger.info("[Session] Stream directo")
                    else:
                        logger.error(f"[Session] Status inesperado: {r1.status_code}")
                        continue

                    # PASO B: Stream desde CDN con timeout generoso para primer chunk
                    logger.info(f"[Session] Conectando al CDN...")
                    r2 = session.get(
                        stream_url,
                        stream=True,
                        timeout=(30, 180),  # 30s conectar, 180s para primer chunk
                        headers={"Referer": "https://mdstrm.com/"},
                    )

                    if r2.status_code != 200:
                        logger.error(f"[Session] CDN HTTP {r2.status_code}")
                        continue

                    # PASO C: Escribir chunks
                    logger.info(f"[Session] Grabando a: {self.aac_file.name}")
                    bytes_written = 0
                    chunk_count = 0
                    last_chunk_time = time.time()

                    with open(self.aac_file, "wb") as f:
                        for chunk in r2.iter_content(chunk_size=8192):
                            if self._stop_event.is_set():
                                logger.info("[Session] Stop solicitado.")
                                success = True
                                break

                            if chunk:
                                f.write(chunk)
                                bytes_written += len(chunk)
                                last_chunk_time = time.time()
                                chunk_count += 1

                            # Si no llega nada en 90s, romper (stream probablemente cortado)
                            if time.time() - last_chunk_time > 90:
                                logger.warning("[Session] 90s sin datos. Stream cortado.")
                                break

                    logger.info(
                        f"[Session] Fin intento {attempt}. Chunks: {chunk_count}, "
                        f"Bytes: {bytes_written}"
                    )

                    if bytes_written > 1024:
                        success = True
                        return  # Éxito total, salir del thread
                    else:
                        logger.warning(f"[Session] 0 bytes en intento {attempt}.")

                except requests.exceptions.Timeout as exc:
                    logger.error(f"[Session] Timeout intento {attempt}: {exc}")
                except requests.exceptions.RequestException as exc:
                    logger.error(f"[Session] Error red intento {attempt}: {exc}")
                except Exception:
                    logger.exception(f"[Session] Error inesperado intento {attempt}")
                finally:
                    if session:
                        session.close()

                # Backoff antes del siguiente intento
                if attempt < max_attempts and not self._stop_event.is_set():
                    wait = 10 * attempt
                    logger.info(f"[Session] Esperando {wait}s antes del siguiente intento...")
                    time.sleep(wait)

            # ── FALLBACK A CURL (1 intento) ──
            if not success and not self._stop_event.is_set():
                logger.warning("[Session] Requests agotado. Fallback a curl...")
                success = self._download_with_curl(url, referer)

            if not success:
                self._failed = True
                self._fail_reason = "Agotados todos los intentos (requests + curl)"
                logger.error(f"[Session] {self._fail_reason}")

        finally:
            # Liberar lock SIEMPRE que el thread termine, si somos los dueños
            if self._lock_owned_by_thread:
                self._release_lock()
                self._lock_owned_by_thread = False
            logger.info("[Session] Thread de descarga finalizado.")

    def _download_with_curl(self, url: str, referer: str) -> bool:
        """
        Fallback final usando curl. Realiza un ciclo completo independiente.
        """
        self.aac_file = self.wav_directory / "recording.aac"
        cookie_jar = self.wav_directory / ".curl_cookies.txt"

        command = [
            "curl",
            "-s", "-L",
            "-c", str(cookie_jar),
            "-b", str(cookie_jar),
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--connect-timeout", "60",
            "--max-time", "0",
            "-H", f"Referer: {referer}",
            "-o", str(self.aac_file),
            url,
        ]

        try:
            logger.info(f"[Curl] Ejecutando fallback...")
            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=self.env,
            )

            while proc.poll() is None:
                if self._stop_event.is_set():
                    logger.info("[Curl] Stop solicitado. Matando curl...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return False
                time.sleep(1)

            stderr = ""
            if proc.stderr:
                stderr = proc.stderr.read().decode("utf-8", errors="ignore")[:200]

            if proc.returncode == 0:
                if self.aac_file.exists() and self.aac_file.stat().st_size > 1024:
                    logger.info(f"[Curl] Éxito: {self.aac_file.stat().st_size / 1024:.1f} KB")
                    return True
                else:
                    logger.error("[Curl] Archivo vacío o no creado.")
                    return False
            else:
                logger.error(f"[Curl] Falló código {proc.returncode}. {stderr}")
                return False

        except Exception:
            logger.exception("[Curl] Error ejecutando curl")
            return False
        finally:
            if cookie_jar.exists():
                try:
                    cookie_jar.unlink()
                except Exception:
                    pass

    # ---------------------------------------------------------
    # ffmpeg (conversión post-grabación)
    # ---------------------------------------------------------
    def convert_to_wav(self):
        if not self.aac_file or not self.aac_file.exists():
            logger.error("No existe archivo AAC para convertir.")
            return False

        if self.aac_file.stat().st_size == 0:
            logger.error("El archivo AAC está vacío (0 bytes).")
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

        # Resetear estado de fallo
        self._failed = False
        self._fail_reason = None

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
                logger.error("El thread de descarga terminó inmediatamente.")
                self._release_lock()
                self._download_thread = None
                self._stop_event = None
                return False

            logger.info(f"Descarga iniciada (session={self.session_id})")
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
                self._download_thread.join(timeout=45)

                if self._download_thread.is_alive():
                    logger.warning("El thread no respondió al stop en 45s.")

            # Conversión post-grabación
            self.convert_to_wav()

            return True
        except Exception:
            logger.exception("Error deteniendo la grabación.")
            return False
        finally:
            self._lock_owned_by_thread = False
            self._release_lock()
            self.process = None
            self._download_thread = None
            self._stop_event = None
            self.start_time = None
            self.session_id = None
            self._stopping = False

    # ---------------------------------------------------------
    # Estado
    # ---------------------------------------------------------
    def is_running(self):
        return self._download_thread is not None and self._download_thread.is_alive()

    def has_failed(self):
        """Retorna True si la grabación falló después de agotar todos los intentos."""
        return self._failed

    def get_status(self):
        return {
            "station": self.station["nombre"],
            "running": self.is_running(),
            "failed": self._failed,
            "fail_reason": self._fail_reason,
            "pid": os.getpid(),
            "session_id": self.session_id,
            "started_at": self.start_time.isoformat() if self.start_time else None,
            "session_directory": str(self.session_directory) if self.session_directory else None,
        }