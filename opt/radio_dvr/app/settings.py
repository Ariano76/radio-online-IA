from pathlib import Path
from zoneinfo import ZoneInfo

# =========================================================
# Rutas principales del proyecto
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

APP_DIR = BASE_DIR / "app"
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_DIR = BASE_DIR / "db"
RUN_DIR = BASE_DIR / "run"
SCRIPTS_DIR = BASE_DIR / "scripts"
SERVICES_DIR = BASE_DIR / "services"

# =========================================================
# Creación automática de directorios
# =========================================================

for directory in [
    CONFIG_DIR,
    DATA_DIR,
    LOG_DIR,
    DB_DIR,
    RUN_DIR,
    ]:
    directory.mkdir(parents=True, exist_ok=True)

# =========================================================
# Base de datos
# =========================================================

DB_PATH = DB_DIR / "recordings.db"

# =========================================================
# Zona horaria
# =========================================================

TIMEZONE_NAME = "America/Lima"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

# =========================================================
# Configuración global del DVR
# =========================================================

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_SEGMENT_MINUTES = 30

FFMPEG_RECONNECT_DELAY = 15
FFMPEG_RW_TIMEOUT = 15000000
FFMPEG_THREAD_QUEUE_SIZE = 1024

# =========================================================
# Watchdog
# =========================================================

WATCHDOG_CHECK_INTERVAL = 10
WATCHDOG_FREEZE_TIMEOUT = 60

# =========================================================
# Conversión
# =========================================================

MP3_BITRATE = "128k"

# =========================================================
# Transcripción
# =========================================================

TRANSCRIPTION_QUEUE_DIR = BASE_DIR / "transcription_queue"
TRANSCRIPTION_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# Utilidades
# =========================================================

def project_path(*parts):
    
    """
    Devuelve una ruta absoluta dentro del proyecto.
    """
    return BASE_DIR.joinpath(*parts)    

