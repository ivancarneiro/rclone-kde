#!/bin/bash

# Detectar el directorio donde se encuentra este script para hacerlo portable
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configurar logs en ~/.cache
LOG_DIR="$HOME/.cache"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/rclone-kde-start.log"

echo "--- Launching Rclone Manager at $(date) ---" >> "$LOGFILE"

# Verificar y activar el entorno virtual
if [ -d ".venv" ]; then
    source .venv/bin/activate
    # Ejecutar la aplicación redirigiendo salida al log
    python3 src/main.py >> "$LOGFILE" 2>&1
else
    echo "Error: .venv no encontrado en $SCRIPT_DIR. Por favor, ejecuta setup.sh primero." | tee -a "$LOGFILE"
    exit 1
fi