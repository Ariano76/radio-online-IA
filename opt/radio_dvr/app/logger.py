import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("/opt/radio_dvr/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

def get_logger(name):
    logger = logging.getLogger(name)

    if logger.handlers:
          return logger
          
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(
             LOG_DIR / f"{name}.log",
                     maxBytes=50 * 1024 * 1024,
                             backupCount=30
                             )

    formatter = logging.Formatter(
             "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
             )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger

