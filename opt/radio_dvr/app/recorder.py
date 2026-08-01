import json
import subprocess
import signal
import time
from pathlib import Path
from datetime import datetime
from app.logger import get_logger
from app.database import Database
from app.timezone import now_peru

from app.settings import DATA_DIR

logger = get_logger("recorder")

class RadioRecorder:

    def __init__(self, station):
        self.station = station
        self.process = None
        self.db = Database()
        self.session_id = None
        self.manifest = {
            "station": station["nombre"],
            "url": station["url"],
            "started_at": None,
            "ended_at": None,
            "segments": [],
            "reconnects": 0
        }

    def build_output_directory(self):
        now = now_peru()
        output_dir = (
            DATA_DIR /
            self.station["nombre"] /
            now.strftime("%Y/%m/%d")
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def build_ffmpeg_command(self):
        output_dir = self.build_output_directory()
        output_pattern = output_dir / "%H%M%S.wav"
        segment_seconds = self.station.get("segmento_minutos", 30) * 60

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
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            "-f", "segment",
            "-segment_time", str(segment_seconds),
            "-segment_atclocktime", "1",
            "-strftime", "1",
            "-reset_timestamps", "1",
            str(output_pattern)
        ]

    def start(self, scheduled_start, scheduled_end):
        logger.info(f"Iniciando grabación: {self.station['nombre']}")

        self.session_id = self.db.create_session(
            self.station["nombre"],
            scheduled_start,
            scheduled_end
        )

        self.manifest["started_at"] = now_peru().isoformat()

        cmd = self.build_ffmpeg_command()

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        logger.info(f"FFmpeg PID: {self.process.pid}")

    def stop(self):
        logger.info(f"Deteniendo grabación: {self.station['nombre']}")

        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)

            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()

        self.manifest["ended_at"] = now_peru().isoformat()

        self.save_manifest()

        logger.info("Grabación finalizada correctamente")

    def is_running(self):
        return self.process and self.process.poll() is None

    def save_manifest(self):
        output_dir = self.build_output_directory()

        wav_files = sorted(output_dir.glob("*.wav"))

        for f in wav_files:
            self.manifest["segments"].append({
                "file": f.name,
                "size_bytes": f.stat().st_size
            })

        with open(output_dir / "manifest.json", "w") as fp:
            json.dump(self.manifest, fp, indent=4)

    def monitor(self):
        while self.is_running():
            line = self.process.stderr.readline()

            if not line:
                time.sleep(1)
                continue

            if "Reconnecting" in line:
                self.manifest["reconnects"] += 1
                logger.warning("Reconexión detectada")

        logger.info("Proceso FFmpeg terminado")

    def current_wav_directory(self):
        return self.build_output_directory()

    def start(self):
        cmd = self.build_ffmpeg_command()

        logger.info("Iniciando FFmpeg")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        self.start_time = now_peru()