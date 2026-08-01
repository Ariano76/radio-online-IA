from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_DIR = BASE_DIR / "db"
SERVICES_DIR = BASE_DIR / "services"

for directory in [
    CONFIG_DIR,
    DATA_DIR,
    LOG_DIR,
    DB_DIR,
    SERVICES_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

DB_PATH = DB_DIR / "recordings.db"