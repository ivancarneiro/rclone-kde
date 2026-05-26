from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal
import logging
from core.settings_manager import SettingsManager
from core.rclone_client import RcloneClient
from core.secret_manager import SecretManager

class SettingsViewModel(QObject):
    settingsChanged = pyqtSignal()
    credentialStatusChanged = pyqtSignal()

    def __init__(self, settings_manager, rclone_client, autostart_manager):
        super().__init__()
        self._settings_manager = settings_manager
        self._client = rclone_client
        self._autostart_manager = autostart_manager
        self._remotes_cache = []
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Google Credential Management
    # ------------------------------------------------------------------

    @pyqtProperty(bool, notify=credentialStatusChanged)
    def hasGoogleCredentials(self):
        """True if Google OAuth credentials are stored in system keyring."""
        return SecretManager.has_google_credentials()

    @pyqtSlot(str, str)
    def save_google_credentials(self, client_id, client_secret):
        """Store Google Client ID/Secret to system keyring."""
        if client_id and client_secret:
            ok = SecretManager.save_google_credentials(client_id, client_secret)
            if ok:
                self.credentialStatusChanged.emit()
                self.logger.info("Google credentials saved via Settings.")
        else:
            self.logger.warning("Both client_id and client_secret are required.")

    @pyqtSlot()
    def delete_google_credentials(self):
        """Remove Google credentials from system keyring."""
        ok = SecretManager.delete_google_credentials()
        if ok:
            self.credentialStatusChanged.emit()
            self.logger.info("Google credentials deleted via Settings.")

    # ------------------------------------------------------------------
    # Autostart
    # ------------------------------------------------------------------

    @pyqtProperty(bool, notify=settingsChanged)
    def run_on_startup(self):
        return self._autostart_manager.is_enabled()

    @pyqtSlot(bool)
    def set_run_on_startup(self, enabled):
        if enabled:
            self._autostart_manager.enable_autostart()
        else:
            self._autostart_manager.disable_autostart()
        self.settingsChanged.emit()
        self._remotes_cache = []

    # ------------------------------------------------------------------
    # Remotes
    # ------------------------------------------------------------------

    @pyqtProperty(list, notify=settingsChanged)
    def remotes_settings_model(self):
        return self._remotes_cache

    @pyqtSlot()
    def load_remotes(self):
        """Carga los remotos y mezcla con la config de auto-mount"""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._refresh_data())
            loop.close()
        except Exception as e:
            self.logger.error(f"Error in load_remotes loop: {e}")

    async def _refresh_data(self):
        try:
            response = await self._client.list_remotes()
            remotes = response.get("remotes", []) if response else []

            enriched = []
            for r in remotes:
                name = r.rstrip(':')
                enabled = self._settings_manager.is_auto_mount_enabled(name)
                enriched.append({
                    "name": name,
                    "auto_mount": enabled
                })
            self._remotes_cache = enriched
            self.settingsChanged.emit()
            self.logger.info("Settings remotes refreshed")
        except Exception as e:
            self.logger.error(f"Error loading remotes for settings: {e}")

    # ------------------------------------------------------------------
    # Start minimized
    # ------------------------------------------------------------------

    @pyqtProperty(bool, notify=settingsChanged)
    def start_minimized(self):
        return self._settings_manager.get_start_minimized()

    @pyqtSlot(bool)
    def set_start_minimized(self, enabled):
        self._settings_manager.set_start_minimized(enabled)
        self.settingsChanged.emit()

    # ------------------------------------------------------------------
    # Auto-mount toggle
    # ------------------------------------------------------------------

    @pyqtSlot(str, bool)
    def toggle_auto_mount(self, remote_name, enabled):
        self.logger.info(f"Toggle auto-mount {remote_name}: {enabled}")
        self._settings_manager.set_auto_mount(remote_name, enabled)
        for r in self._remotes_cache:
            if r["name"] == remote_name:
                r["auto_mount"] = enabled
        self.settingsChanged.emit()
