#!/bin/bash
echo "Scheduler:"
systemctl is-active radio-scheduler

echo "Watchdog:"
systemctl is-active radio-watchdog

echo "Procesos FFmpeg:"
pgrep -a ffmpeg

echo "Últimos archivos:"
find /opt/radio_dvr/data -name "*.wav" | tail -5