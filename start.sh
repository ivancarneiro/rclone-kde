#!/bin/bash
# Debug Logging (Enabled for troubleshooting)
LOGFILE="/home/ciex/Rclone-GUI/LiveApp/debug.log"
exec > >(tee -i "$LOGFILE") 2>&1

echo "--- Launching Rclone Manager at $(date) ---"

cd "/home/ciex/Rclone-GUI/LiveApp"
source .venv/bin/activate
python3 src/main.py
