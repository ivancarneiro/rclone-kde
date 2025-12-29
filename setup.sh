#!/bin/bash

echo "🚀 Installing Rclone Manager..."

# 1. Create Virtual Env
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

# Check for Rclone
if ! command -v rclone &> /dev/null; then
    echo "Rclone not found. Installing..."
    # Check if we have sudo
    if command -v sudo &> /dev/null; then
        sudo -v
        curl https://rclone.org/install.sh | sudo bash
    else
        echo "Error: sudo not found. Please install rclone manually: curl https://rclone.org/install.sh | bash"
    fi
else
    echo "Rclone is already installed."
fi

# 2. Activate
source .venv/bin/activate

# 3. Install Requirements
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create Desktop Entry
echo "Creating Desktop Shortcut..."
mkdir -p ~/.local/share/applications

# Get absolute path to this dir
BASE_DIR=$(pwd)
ICON_PATH="$BASE_DIR/src/ui/assets/rclone_logo.png"
EXEC_PATH="$BASE_DIR/.venv/bin/python3 $BASE_DIR/src/main.py"

cat > ~/.local/share/applications/rclone-manager.desktop <<EOF
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

# Create start script
echo "#!/bin/bash" > start.sh
echo "cd \"$BASE_DIR\"" >> start.sh
echo "source .venv/bin/activate" >> start.sh
echo "python3 src/main.py" >> start.sh
chmod +x start.sh
