import time
from pathlib import Path
from app.logger import get_logger
from app.timezone import now_peru

logger = get_logger("watchdog")

class ProcessWatchdog:
#
# Supervisa una instancia de RadioRecorder.

# Responsabilidades:
# - Verificar que FFmpeg continúe ejecutándose.
# - Verificar que el segmento WAV activo siga creciendo.
# - Detectar congelamientos del stream.
# - Exponer el estado del monitoreo.

# Este módulo NO reinicia grabaciones automáticamente.
#La decisión de reiniciar corresponde al Scheduler.

    def __init__(
        self,
        recorder,
        freeze_timeout=60,
        check_interval=10,
    ):
        self.recorder = recorder
        self.freeze_timeout = freeze_timeout
        self.check_interval = check_interval

        self.last_size = 0
        self.last_growth = now_peru()

    # ---------------------------------------------------------
    # Proceso
    # ---------------------------------------------------------

    def process_alive(self):
        return self.recorder.is_running()

    # ---------------------------------------------------------
    # Segmento activo
    # ---------------------------------------------------------

    def current_segment(self):
        return self.recorder.current_segment()

    # ---------------------------------------------------------
    # Crecimiento del archivo
    # ---------------------------------------------------------

    def file_growing(self):
        segment = self.current_segment()

        if segment is None:
            return True
        try:
            size = segment.stat().st_size
        except FileNotFoundError:
            return True

        if size > self.last_size:
            self.last_size = size
            self.last_growth = now_peru()
            return True

        elapsed = (
            now_peru() - self.last_growth
        ).total_seconds()

        if elapsed > self.freeze_timeout:
            logger.error(
                f"El segmento {segment.name} no ha crecido durante {elapsed:.0f} segundos."
            )
            return False

        return True

    # ---------------------------------------------------------
    # Estado
    # ---------------------------------------------------------

    def health_check(self):
        process_ok = self.process_alive()
        growth_ok = self.file_growing()

        healthy = process_ok and growth_ok

        return {
            "healthy": healthy,
            "process_alive": process_ok,
            "file_growing": growth_ok,
            "last_growth": self.last_growth.isoformat(),
            "current_segment": (
                str(self.current_segment())
                if self.current_segment()
                else None
            ),
        }

    # ---------------------------------------------------------
    # Espera de cierre
    # ---------------------------------------------------------

    @staticmethod
    def wait_until_closed(path: Path, stable_seconds=3):
        """
        Espera hasta que el archivo deje de crecer.
        Se utiliza antes de iniciar procesos como
        conversión MP3 o transcripción.
        """

        previous_size = -1
        stable_count = 0

        while True:
            try:
                current_size = path.stat().st_size
            except FileNotFoundError:
                return False

            if current_size == previous_size:
                stable_count += 1
            else:
                stable_count = 0

            if stable_count >= stable_seconds:
                return True

            previous_size = current_size
            time.sleep(1)

