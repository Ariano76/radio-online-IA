import logging
from logging.handlers import RotatingFileHandler
from app.settings import LOG_DIR

# =========================================================
# Configuración global
# =========================================================

LOG_LEVEL = logging.INFO
LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MAX_LOG_SIZE = 50 * 1024 * 1024  # 50 MB
BACKUP_COUNT = 30

# =========================================================
# Cache de loggers
# =========================================================

_LOGGERS = {}

# =========================================================
# Logger principal
# =========================================================

def get_logger(name: str) -> logging.Logger:

    """
    Devuelve un logger configurado para el proyecto.
    Cada logger:
    - Es singleton por nombre.
    - Escribe en logs/<name>.log.
    - Tiene rotación automática.
    - También escribe en consola.
    - Evita handlers duplicados.
    """

    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    logger.propagate = False

    formatter = logging.Formatter(
        LOG_FORMAT,
        DATE_FORMAT,
    )

    # -----------------------------------------------------
    # Archivo con rotación
    # -----------------------------------------------------

    file_handler = RotatingFileHandler(
        LOG_DIR / f"{name}.log",
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )

    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)

    # -----------------------------------------------------
    # Consola
    # -----------------------------------------------------

    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)

    # -----------------------------------------------------
    # Registrar handlers
    # -----------------------------------------------------

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _LOGGERS[name] = logger

    return logger

