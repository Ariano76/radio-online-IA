import time
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from app.logger import get_logger
from app.timezone import now_peru

logger = get_logger("watchdog")

class ProcessWatchdog:

    def __init__(self, recorder, timeout_seconds=60):
        self.recorder = recorder
        self.timeout_seconds = timeout_seconds
        self.last_size = 0
        self.last_growth = now_peru()
        self.restarts = 0

    def get_active_wav(self):
        wav_dir = self.recorder.current_wav_directory()

        files = sorted(wav_dir.glob("*.wav"))

        if not files:
            return None

        return files[-1]

    def check_file_growth(self):
        wav = self.get_active_wav()

        if wav is None:
            return True

        size = wav.stat().st_size

        if size > self.last_size:
            self.last_size = size
            self.last_growth = now_peru()
            return True

        elapsed = (now_peru() - self.last_growth).total_seconds()

        if elapsed > self.timeout_seconds:
            logger.error(
                f"Archivo congelado durante {elapsed:.0f} segundos"
            )
            return False

        return True

    def check_process(self):
        if self.recorder.process is None:
            return False

        return self.recorder.process.poll() is None

    def restart(self):
        self.restarts += 1

        logger.warning(
            f"Reiniciando FFmpeg (reinicio #{self.restarts})"
        )

        self.recorder.stop()

        time.sleep(5)

        self.recorder.start()

        self.last_size = 0
        self.last_growth = now_peru()

    def monitor(self):
        logger.info("Watchdog activo")

        while True:

            process_ok = self.check_process()
            growth_ok = self.check_file_growth()

            if not process_ok or not growth_ok:
                self.restart()

            time.sleep(10)