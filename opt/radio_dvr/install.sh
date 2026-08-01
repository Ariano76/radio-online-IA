#!/bin/bash

set -e

echo "========================================="
echo "Radio DVR LLM - Instalación"
echo "Ubuntu 22.04"
echo "========================================="

# Verificar que estamos en la raíz del proyecto

if [ ! -f "requirements.txt" ]; then
echo "ERROR: Ejecuta este script desde la raíz del repositorio."
exit 1
fi

echo "Actualizando paquetes del sistema..."
sudo apt update

echo "Instalando dependencias del sistema..."
sudo apt install -y 
ffmpeg 
sqlite3 
python3 
python3-pip 
python3-venv 
git 
curl 
build-essential

echo "Creando entorno virtual..."
if [ ! -d "venv" ]; then
python3 -m venv venv
fi

echo "Activando entorno virtual..."
source venv/bin/activate

echo "Actualizando pip..."
python -m pip install --upgrade pip

echo "Instalando dependencias de Python..."
pip install -r requirements.txt

echo "Verificando FFmpeg..."
ffmpeg -version >/dev/null 2>&1 || {
echo "ERROR: FFmpeg no se instaló correctamente."
exit 1
}

echo "Verificando SQLite..."
sqlite3 --version >/dev/null 2>&1 || {
echo "ERROR: SQLite no está disponible."
exit 1
}

echo "========================================="
echo "Instalación completada correctamente."
echo "========================================="
echo "Para activar el entorno virtual:"
echo "source venv/bin/activate"
echo "========================================="
