from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal, QThread
import logging
from core.settings_manager import SettingsManager
from core.rclone_client import RcloneClient
from core.secret_manager import SecretManager


class _KeyringWorker(QObject):
    """
    Runs blocking keyring operations in a background thread
    so the Qt event loop stays responsive (critical for Wayland compatibility).
    The KDE Wallet dialog (shown by kwalletd via DBUS) will appear alongside
    our responsive application window instead of behind a frozen UI.
    """

    finished = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, action, client_id=None, client_secret=None):
        super().__init__()
        self._action = action
        self._client_id = client_id
        self._client_secret = client_secret

    @pyqtSlot()
    def run(self):
        """Execute the keyring operation (runs in background thread)."""
        try:
            if self._action == "save":
                ok = SecretManager.save_google_credentials(self._client_id, self._client_secret)
            elif self._action == "delete":
                ok = SecretManager.delete_google_credentials()
            else:
                ok = False
            self.finished.emit(ok)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)


class SettingsViewModel(QObject):
    settingsChanged = pyqtSignal()
    credentialStatusChanged = pyqtSignal()
    keyringBusyChanged = pyqtSignal(bool)

    def __init__(self, settings_manager, rclone_client, autostart_manager):
        super().__init__()
        self._settings_manager = settings_manager
        self._client = rclone_client
        self._autostart_manager = autostart_manager
        self._remotes_cache = []
        self._keyring_busy = False
        self._keyring_thread = None
        self._keyring_worker = None
        self._pending_auto_push = None
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Keyring threading helpers
    # ------------------------------------------------------------------

    @pyqtProperty(bool, notify=keyringBusyChanged)
    def keyring_busy(self):
        return self._keyring_busy

    def _run_keyring_thread(self, action, client_id=None, client_secret=None):
        """
        Start a background thread for a blocking keyring operation.
        The Qt event loop remains responsive so window alert/raise events
        are processed, and the KDE Wallet dialog appears in front.
        """
        if self._keyring_busy:
            self.logger.warning("Keyring operation already in progress, ignoring.")
            return

        self._keyring_busy = True
        self.keyringBusyChanged.emit(True)

        self._keyring_thread = QThread()
        self._keyring_worker = _KeyringWorker(action, client_id, client_secret)
        self._keyring_worker.moveToThread(self._keyring_thread)

        self._keyring_thread.started.connect(self._keyring_worker.run)
        self._keyring_worker.finished.connect(self._on_keyring_finished)
        self._keyring_worker.error.connect(self._on_keyring_error)
        self._keyring_worker.finished.connect(self._keyring_thread.quit)
        self._keyring_thread.finished.connect(self._cleanup_keyring_thread)

        self._keyring_thread.start()

    def _on_keyring_finished(self, ok):
        """Callback when the background keyring operation completes."""
        if ok:
            if hasattr(self, '_pending_auto_push') and self._pending_auto_push:
                self._apply_credentials_to_existing_remotes(
                    self._pending_auto_push[0],
                    self._pending_auto_push[1]
                )
                self._pending_auto_push = None
            self.credentialStatusChanged.emit()
            self.logger.info("Keyring operation completed successfully.")
        else:
            self.logger.warning("Keyring operation returned failure.")

    def _on_keyring_error(self, error_msg):
        """Callback when the background keyring operation raises an exception."""
        self.logger.error(f"Keyring operation error: {error_msg}")

    def _cleanup_keyring_thread(self):
        """Clean up thread and worker objects."""
        self._keyring_busy = False
        self.keyringBusyChanged.emit(False)
        if self._keyring_thread:
            self._keyring_thread.deleteLater()
            self._keyring_thread = None
        if self._keyring_worker:
            self._keyring_worker.deleteLater()
            self._keyring_worker = None

    # ------------------------------------------------------------------
    # Google Credential Management
    # ------------------------------------------------------------------

    @pyqtProperty(bool, notify=credentialStatusChanged)
    def hasGoogleCredentials(self):
        """True if Google OAuth credentials are stored in system keyring."""
        return SecretManager.has_google_credentials()

    @pyqtSlot(str, str)
    def save_google_credentials(self, client_id, client_secret):
        """
        Store Google Client ID/Secret to system keyring.
        Uses a background thread so the Qt event loop stays responsive,
        allowing window raise/alert events to process before the
        KDE Wallet dialog appears.
        """
        if not client_id or not client_secret:
            self.logger.warning("Both client_id and client_secret are required.")
            return
        self._pending_auto_push = (client_id, client_secret)
        self._run_keyring_thread("save", client_id, client_secret)

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
        """
        Remove Google credentials from system keyring.
        Uses a background thread so the Qt event loop stays responsive,
        allowing window raise/alert events to process before the
        KDE Wallet dialog appears.
        """
        self._run_keyring_thread("delete")

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
