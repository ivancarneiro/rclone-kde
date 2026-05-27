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
        """Store Google Client ID/Secret to system keyring and auto-push to existing remotes."""
        if client_id and client_secret:
            ok = SecretManager.save_google_credentials(client_id, client_secret)
            if ok:
                # Auto-push credentials to existing remotes (transparent update)
                self._apply_credentials_to_existing_remotes(client_id, client_secret)
                self.credentialStatusChanged.emit()
                self.logger.info("Google credentials saved and pushed to existing remotes.")
        else:
            self.logger.warning("Both client_id and client_secret are required.")

    def _apply_credentials_to_existing_remotes(self, client_id, client_secret):
        """
        Automatically update client_id/client_secret in all existing remotes
        so the user doesn't have to manually update each one.
        This just updates the config, it doesn't reauthorize (token stays the same).
        """
        import subprocess
        import asyncio

        try:
            # Get existing remotes
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self._client.list_remotes())
            loop.close()

            remotes = response.get("remotes", []) if response else []
            updated_count = 0

            for r in remotes:
                name = r.rstrip(':')
                try:
                    # Silently update client_id/secret without triggering reauth
                    cmd = [
                        "rclone", "config", "update", name,
                        f"client_id={client_id}",
                        f"client_secret={client_secret}",
                        "config_refresh_token=false"
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        updated_count += 1
                        self.logger.info(f"Auto-pushed credentials to remote: {name}")
                    else:
                        self.logger.debug(f"Could not update {name}: {result.stderr[:100]}")
                except Exception as e:
                    self.logger.debug(f"Error updating remote {name}: {e}")

            if updated_count > 0:
                self.logger.info(f"Auto-pushed credentials to {updated_count} remote(s)")
        except Exception as e:
            self.logger.debug(f"Auto-push credentials failed: {e}")

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
    # Reconnect Remote
    # ------------------------------------------------------------------

    reconnectStateChanged = pyqtSignal(str, str)  # remote_name, state
    reconnectStatusMessageChanged = pyqtSignal(str, str)  # remote_name, message

    @pyqtSlot(str)
    def reconnect_remote(self, remote_name):
        """Reautoriza un remote usando credenciales del keyring."""
        import subprocess
        import json
        from core.secret_manager import SecretManager

        self.logger.info(f"Settings: Reconnecting remote {remote_name}")
        self.reconnectStateChanged.emit(remote_name, "reconnecting")
        self.reconnectStatusMessageChanged.emit(remote_name, "Reconnecting...")

        creds = SecretManager.get_google_credentials()
        if not creds:
            self.reconnectStateChanged.emit(remote_name, "error")
            self.reconnectStatusMessageChanged.emit(remote_name, "❌ No credentials in keyring")
            return

        try:
            # Update client_id/secret
            update_cmd = [
                "rclone", "config", "update", remote_name,
                f"client_id={creds.client_id}",
                f"client_secret={creds.client_secret}",
                "config_refresh_token=false"
            ]
            result = subprocess.run(update_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                raise Exception(f"Config update failed: {result.stderr}")

            # Authorize
            self.reconnectStatusMessageChanged.emit(remote_name, "🔐 Opening browser...")
            auth_cmd = ["rclone", "authorize", "drive", creds.client_id]
            if creds.client_secret:
                auth_cmd.append(creds.client_secret)

            auth_result = subprocess.run(auth_cmd, capture_output=True, text=True, timeout=120)
            if auth_result.returncode != 0:
                raise Exception(f"Authorization failed: {auth_result.stderr}")

            # Parse token
            token_json = auth_result.stdout.strip()
            try:
                json.loads(token_json)
            except json.JSONDecodeError:
                start = token_json.find('{')
                end = token_json.rfind('}') + 1
                if start != -1 and end != -1:
                    token_json = token_json[start:end]
                else:
                    raise Exception("Invalid token")

            # Update token
            token_cmd = ["rclone", "config", "update", remote_name, f"token={token_json}"]
            result = subprocess.run(token_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                raise Exception(f"Token update failed: {result.stderr}")

            self.reconnectStateChanged.emit(remote_name, "success")
            self.reconnectStatusMessageChanged.emit(remote_name, "✅ Reconnected!")
            self.logger.info(f"Reconnect successful for {remote_name}")

        except subprocess.TimeoutExpired:
            self.reconnectStateChanged.emit(remote_name, "error")
            self.reconnectStatusMessageChanged.emit(remote_name, "⏱️ Timed out")
        except Exception as e:
            self.logger.exception(f"Reconnect failed for {remote_name}")
            self.reconnectStateChanged.emit(remote_name, "error")
            self.reconnectStatusMessageChanged.emit(remote_name, f"❌ {str(e)}")

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
