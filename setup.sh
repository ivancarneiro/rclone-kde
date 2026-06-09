#!/bin/bash

echo "🚀 Installing Rclone Manager (UV Mode)..."

# Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install it first: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# 1. Sync environment
echo "Syncing environment with uv..."
uv sync

# 2. Create Desktop Entry
echo "Creating Desktop Shortcut..."
mkdir -p ~/.local/share/applications

# Get absolute path to this dir
BASE_DIR=$(pwd)
ICON_PATH="$BASE_DIR/src/ui/assets/rclone_isologo.png"
EXEC_PATH="$BASE_DIR/start.sh"

cat > ~/.local/share/applications/rclone-gui-final.desktop <<EOF
[Desktop Entry]
Name=Rclone Manager
Comment=Manage your Cloud Drive mounts with ease
Exec=$EXEC_PATH
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Utility;Network;
EOF

echo "✅ Installation Complete!"
echo "You can find 'Rclone Manager' in your Application Menu."
echo "Or run it manually: ./start.sh"

# Ensure start.sh is correct and executable
if [ ! -f "start.sh" ]; then
    cat > start.sh <<EOF
#!/bin/bash
SCRIPT_DIR="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" && pwd )"
cd "\$SCRIPT_DIR"
uv run python3 src/main.py "\$@"
EOF
    chmod +x start.sh
fi
