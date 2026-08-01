import logging
from logging.handlers import RotatingFileHandler

from app.settings import LOG_DIR

def get_logger(name):

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(
        LOG_DIR / f"{name}.log",
        maxBytes=50 * 1024 * 1024,
        backupCount=30,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger