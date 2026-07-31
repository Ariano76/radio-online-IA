from pathlib import Path
import hashlib

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def sha256_file(path):
    h = hashlib.sha256()


    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()

