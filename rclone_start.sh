#!/bin/bash
cd /home/ciex/Rclone-GUI/rclone-kde
# Usamos uv run para mayor consistencia y velocidad
uv run python src/main.py "$@"
