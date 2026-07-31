#!/bin/bash
set -e

echo "========================================="
echo "RADIO DVR - Instalación Fase 1"
echo "========================================="

sudo apt update
sudo apt upgrade -y

sudo apt install -y 
ffmpeg 
sqlite3 
python3-venv 
python3-pip 
git 
curl

sudo mkdir -p /opt/radio_dvr

sudo chown -R $USER:$USER /opt/radio_dvr

cd /opt/radio_dvr

mkdir -p config app data logs db services

python3 -m venv venv

source venv/bin/activate

pip install --upgrade pip

pip install -r requirements.txt

echo "Instalación completada correctamente."
echo "Proyecto instalado en /opt/radio_dvr"
