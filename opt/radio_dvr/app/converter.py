import subprocess
from pathlib import Path
from app.logger import get_logger
from app.utils import sha256_file

logger = get_logger("converter")

class AudioConverter:

    def convert_to_mp3(self, wav_file):

        wav_file = Path(wav_file)

        mp3_dir = wav_file.parent.parent / "mp3"
        mp3_dir.mkdir(parents=True, exist_ok=True)

        mp3_file = mp3_dir / (wav_file.stem + ".mp3")

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(wav_file),
            "-codec:a", "libmp3lame",
            "-b:a", "128k",
            str(mp3_file)
        ]

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        metadata = {
            "wav_file": wav_file.name,
            "mp3_file": mp3_file.name,
            "wav_sha256": sha256_file(wav_file),
            "mp3_sha256": sha256_file(mp3_file),
            "wav_size": wav_file.stat().st_size,
            "mp3_size": mp3_file.stat().st_size
        }

        logger.info(f"Convertido: {wav_file.name}")

        return metadata