from zoneinfo import ZoneInfo
from datetime import datetime

PERU_TZ = ZoneInfo("America/Lima")

def now_peru():
    return datetime.now(PERU_TZ)

def format_peru(dt=None):
    if dt is None:
        dt = now_peru()

    return dt.strftime("%Y-%m-%d %H:%M:%S")
