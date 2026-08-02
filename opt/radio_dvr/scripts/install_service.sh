#!/bin/bash
set -e

echo "===================================="
echo "Instalando Radio DVR Scheduler"
echo "===================================="

sudo cp services/radio_scheduler.service /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable radio_scheduler.service

sudo systemctl start radio_scheduler.service

echo
echo "Servicio instalado correctamente."
echo

sudo systemctl status radio_scheduler.service --no-pager