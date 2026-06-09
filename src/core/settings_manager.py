import json
import os
import logging
from .config import Config

class SettingsManager:
    """
    Gestiona la configuración global de la aplicación.
    Guarda preferencias en 'settings.json'.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.settings_file = os.path.join(Config.base_dir, "settings.json")
        self._settings = {
            "auto_mounts": [],
            "start_minimized": False,
            "keepassxc_remote": "",
            "keepassxc_db_path": ""
        }
        self.load_settings()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    self._settings.update(data)
            except Exception as e:
                self.logger.error(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self._settings, f, indent=4)
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")

    def get_auto_mounts(self):
        return self._settings.get("auto_mounts", [])

    def add_auto_mount(self, remote_name):
        current = self.get_auto_mounts()
        if remote_name not in current:
            current.append(remote_name)
            self._settings["auto_mounts"] = current
            self.save_settings()

    def remove_auto_mount(self, remote_name):
        current = self.get_auto_mounts()
        if remote_name in current:
            current.remove(remote_name)
            self._settings["auto_mounts"] = current
            self.save_settings()
            
    def is_auto_mount_enabled(self, remote_name):
        return remote_name in self.get_auto_mounts()

    def set_auto_mount(self, remote_name, enabled):
        if enabled:
            self.add_auto_mount(remote_name)
        else:
            self.remove_auto_mount(remote_name)

    def get_start_minimized(self):
        return self._settings.get("start_minimized", False)

    def set_start_minimized(self, enabled):
        self._settings["start_minimized"] = enabled
        self.save_settings()

    def get_keepassxc_config(self):
        return {
            "remote": self._settings.get("keepassxc_remote", ""),
            "db_path": self._settings.get("keepassxc_db_path", "")
        }

    def set_keepassxc_config(self, remote, db_path):
        self._settings["keepassxc_remote"] = remote
        self._settings["keepassxc_db_path"] = db_path
        self.save_settings()

    def get_keepassxc_config(self):
        return {
            "remote": self._settings.get("keepassxc_remote", ""),
            "db_path": self._settings.get("keepassxc_db_path", "")
        }

    def set_keepassxc_config(self, remote, db_path):
        self._settings["keepassxc_remote"] = remote
        self._settings["keepassxc_db_path"] = db_path
        self.save_settings()
