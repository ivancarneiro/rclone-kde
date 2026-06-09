import os
import sys
import logging
from pathlib import Path

class AutostartManager:
    """
    Gestiona la creación del archivo .desktop en ~/.config/autostart
    para iniciar la aplicación con el sistema.
    """
    APP_NAME = "rclone-gui-manager"
    DESKTOP_ENTRY_TEMPLATE = """[Desktop Entry]
Type=Application
Name=Rclone GUI Manager
Comment=Manage and mount Rclone remotes
Exec={exec_cmd}
Icon=utilities-terminal
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.autostart_dir = os.path.expanduser("~/.config/autostart")
        self.desktop_file = os.path.join(self.autostart_dir, f"{self.APP_NAME}.desktop")

    def enable_autostart(self):
        """Crea el archivo .desktop para iniciar la app."""
        try:
            if not os.path.exists(self.autostart_dir):
                os.makedirs(self.autostart_dir)

            # Preferimos usar start.sh si existe, ya que centraliza la lógica de uv/venv
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            start_script = os.path.join(base_dir, "start.sh")
            
            if os.path.exists(start_script):
                exec_cmd = f"{start_script} --minimized"
            else:
                # Fallback al ejecutable actual
                python_exe = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                exec_cmd = f"{python_exe} {script_path} --minimized"
            
            content = self.DESKTOP_ENTRY_TEMPLATE.format(exec_cmd=exec_cmd)
            
            with open(self.desktop_file, 'w') as f:
                f.write(content)
            
            self.logger.info(f"Autostart enabled: {self.desktop_file}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable autostart: {e}")
            return False

    def disable_autostart(self):
        """Elimina el archivo .desktop."""
        try:
            if os.path.exists(self.desktop_file):
                os.remove(self.desktop_file)
                self.logger.info("Autostart disabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable autostart: {e}")
            return False

    def is_enabled(self):
        return os.path.exists(self.desktop_file)
