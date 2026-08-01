import hashlib
import shutil
import time
from pathlib import Path
from datetime import datetime

# =========================================================
# Directorios
# =========================================================

def ensure_directory(path: Path):
    """
    Crea un directorio si no existe.
    """
    path.mkdir(parents=True, exist_ok=True)

    return path

# =========================================================
# Hash de archivos
# =========================================================

def file_sha256(path: Path, chunk_size=1024 * 1024):
    """
    Calcula el hash SHA256 de un archivo.
    """

    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha.update(chunk)

    return sha.hexdigest()

# =========================================================
# Tamaño de archivos
# =========================================================

def file_size(path: Path):
    """
    Devuelve el tamaño del archivo en bytes.
    """

    return path.stat().st_size

# =========================================================
# Espera de estabilización
# =========================================================

def wait_for_file_stable(
    path: Path,
    stable_seconds=3,
    timeout=300,
    ):
    """
    Espera hasta que el archivo deje de crecer.

    Retorna True cuando el archivo permanece estable
    durante stable_seconds.

    Retorna False si se supera el timeout.
    """

    previous_size = -1
    stable_count = 0
    start = time.time()

    while True:
        if time.time() - start > timeout:
            return False
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            time.sleep(1)
            continue

        if current_size == previous_size:
            stable_count += 1
        else:
            stable_count = 0
        if stable_count >= stable_seconds:
            return True
        previous_size = current_size
        time.sleep(1)

# =========================================================
# Copia segura
# =========================================================

def safe_copy(src: Path, dst: Path):
    """
    Copia un archivo preservando metadatos.
    """

    ensure_directory(dst.parent)
    shutil.copy2(src, dst)
    return dst

# =========================================================
# Movimiento seguro
# =========================================================

def safe_move(src: Path, dst: Path):
    """
    Mueve un archivo creando el directorio destino
    si es necesario.
    """

    ensure_directory(dst.parent)
    shutil.move(str(src), str(dst))
    return dst

# =========================================================
# Formato de tamaño
# =========================================================

def human_size(size):
    """
    Convierte bytes a una representación legible.
    """

    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)

    for unit in units:
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PB"

# =========================================================
# Timestamp
# =========================================================

def timestamp():
    """
    Devuelve un timestamp compacto.
    Ejemplo:
        20260801_221530
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")

# =========================================================
# Listado ordenado
# =========================================================

def list_files(directory: Path, pattern="*"):
    """
    Lista archivos ordenados por nombre.
    """

    return sorted(directory.glob(pattern))

# =========================================================
# Último archivo
# =========================================================

def latest_file(directory: Path, pattern="*"):
    """
    Devuelve el archivo más reciente según el nombre.
    """
    
    files = list_files(directory, pattern)

    if not files:
        return None

    return files[-1]
