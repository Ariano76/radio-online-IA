#!/bin/bash
set -e

sudo systemctl stop radio_scheduler.service || true

sudo systemctl disable radio_scheduler.service || true

sudo rm -f /etc/systemd/system/radio_scheduler.service

sudo systemctl daemon-reload

echo "Servicio desinstalado correctamente."