from datetime import datetime, timezone

from app.settings import TIMEZONE

# =========================================================
# Hora oficial de Perú
# =========================================================

def now_peru():
    """
    Devuelve la fecha y hora actual en la zona horaria de Perú.
    Todos los módulos operativos del sistema (Scheduler,
    Recorder, Watchdog, nombres de carpetas, etc.) deben
    utilizar esta función.
    """

    return datetime.now(TIMEZONE)

# =========================================================
# Hora UTC

# =========================================================

def now_utc():
    """
    Devuelve la fecha y hora actual en UTC.
    Se utiliza para almacenamiento y sincronización.
    """

    return datetime.now(timezone.utc)

# =========================================================
# Conversión
# =========================================================

def to_peru(dt):
    """
    Convierte un datetime a la zona horaria de Perú.
    """

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(TIMEZONE)

def to_utc(dt):
    """
    Convierte un datetime a UTC.
    """

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE)

    return dt.astimezone(timezone.utc)

# =========================================================
# Formateo
# =========================================================

def format_peru(dt=None, fmt="%Y-%m-%d %H:%M:%S"):
    """
    Formatea una fecha en hora de Perú.
    """

    if dt is None:
        dt = now_peru()
    else:
        dt = to_peru(dt)

    return dt.strftime(fmt)

def format_utc(dt=None, fmt="%Y-%m-%d %H:%M:%S UTC"):
    """
    Formatea una fecha en UTC.
    """

    if dt is None:
        dt = now_utc()
    else:
        dt = to_utc(dt)

    return dt.strftime(fmt)
