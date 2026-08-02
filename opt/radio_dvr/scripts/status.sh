#!/bin/bash

echo "===================================="
echo "Estado del servicio"
echo "===================================="

sudo systemctl status radio_scheduler.service --no-pager

echo

echo "===================================="
echo "Procesos FFmpeg"
echo "===================================="

ps aux | grep ffmpeg | grep -v grep || echo "No hay grabaciones activas."

echo

echo "===================================="
echo "Archivos PID"
echo "===================================="

ls -la run

echo

echo "===================================="
echo "Últimos archivos WAV"
echo "===================================="

find data -name "*.wav" | sort | tail -5

echo

echo "===================================="
echo "Espacio disponible"
echo "===================================="

df -h .