#!/bin/bash

# Asegurar que las rutas de binarios de usuario estén disponibles (especialmente para entornos de systemd/KDE)
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# Detectar el directorio del script para hacerlo portable
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Verificar que uv esté instalado
if ! command -v uv &> /dev/null; then
    echo "Error: uv no está instalado. Por favor, instálalo para continuar."
    exit 1
fi

# Log simple de intento de lanzamiento en .cache
LOGFILE="$HOME/.cache/rclone-kde-launch.log"
mkdir -p "$(dirname "$LOGFILE")"
echo "[$(date)] Launching Rclone Manager with uv run..." >> "$LOGFILE"

# Ejecutar la aplicación usando uv run
# Esto gestiona automáticamente el entorno virtual y las dependencias
uv run python3 src/main.py "$@" >> "$LOGFILE" 2>&1
