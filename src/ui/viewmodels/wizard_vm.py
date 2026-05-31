from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal
import subprocess
import json
import logging
from core.config import Config
from core.secret_manager import SecretManager

class WizardViewModel(QObject):
    """
    ViewModel para el Wizard de creación de nuevo remoto (Google Drive).
    Soporta carga automática de credenciales Google OAuth desde el keyring del sistema.
    """
    # Signals
    authStateChanged = pyqtSignal(str) # "idle", "loading", "success", "error"
    statusMessageChanged = pyqtSignal(str)
    finished = pyqtSignal()
    credentialsFoundChanged = pyqtSignal(bool)

    def __init__(self, client, settings_manager, autostart_manager):
        super().__init__()
        self._client = client
        self._settings_manager = settings_manager
        self._autostart_manager = autostart_manager
        self._status_message = ""
        self._stored_client_id = ""
        self._stored_client_secret = ""
        self._has_stored_credentials = False
        self.logger = logging.getLogger(__name__)
        self._statusMessage = ""

        # Load stored credentials from keyring on init
        self._load_stored_credentials()

    # ------------------------------------------------------------------
    # Keyring integration
    # ------------------------------------------------------------------

    def _load_stored_credentials(self):
        """Carga credenciales desde el keyring del sistema."""
        creds = SecretManager.get_google_credentials()
        if creds:
            self._stored_client_id = creds.client_id
            self._stored_client_secret = creds.client_secret
            self._has_stored_credentials = True
            self.logger.info("Google OAuth credentials loaded from system keyring.")
        else:
            self._stored_client_id = ""
            self._stored_client_secret = ""
            self._has_stored_credentials = False
        self.credentialsFoundChanged.emit(self._has_stored_credentials)

    @pyqtProperty(str, notify=credentialsFoundChanged)
    def storedClientId(self):
        return self._stored_client_id

    @pyqtProperty(str, notify=credentialsFoundChanged)
    def storedClientSecret(self):
        return self._stored_client_secret

    @pyqtProperty(bool, notify=credentialsFoundChanged)
    def hasStoredCredentials(self):
        return self._has_stored_credentials

    @pyqtSlot(str, str)
    def save_credentials_to_keyring(self, client_id, client_secret):
        """Guarda las credenciales ingresadas en el keyring."""
        if client_id and client_secret:
            success = SecretManager.save_google_credentials(client_id, client_secret)
            if success:
                self._load_stored_credentials()
                self.setStatus("✅ Credentials saved to system keyring.")
            else:
                self.setStatus("⚠️ Could not save to keyring.")
        else:
            self.setStatus("⚠️ Both Client ID and Secret are required to save.")

    @pyqtSlot()
    def delete_stored_credentials(self):
        """Elimina las credenciales almacenadas en el keyring."""
        success = SecretManager.delete_google_credentials()
        if success:
            self._load_stored_credentials()
            self.setStatus("🗑️ Credentials removed from keyring.")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @pyqtProperty(str, notify=statusMessageChanged)
    def statusMessage(self):
        return self._status_message

    def setStatus(self, msg):
        self._status_message = msg
        self.statusMessageChanged.emit(msg)

    # ------------------------------------------------------------------
    # Auth flow
    # ------------------------------------------------------------------

    @pyqtSlot(str, str, str, bool)
    def createDriveRemote(self, name, client_id, client_secret, auto_mount):
        """
        Paso 1: Configurar remote tipo 'drive'
        Paso 2: Obtener url de auth
        """
        self.logger.info(f"Creating Drive remote: {name}, AutoMount: {auto_mount}")

        # Save Auto-Mount pref
        if auto_mount:
            self._settings_manager.add_auto_mount(name)
            if not self._autostart_manager.is_enabled():
                self._autostart_manager.enable_autostart()

        if not name:
            self.authStateChanged.emit("error")
            self.setStatus("Name is required")
            return

        self.authStateChanged.emit("loading")
        self.setStatus("Launching browser for authentication...")
        self.logger.info(f"Starting auth flow for {name}")

        try:
            cmd = ["rclone", "authorize", "drive"]
            if client_id:
                cmd.append(client_id)
            if client_secret:
                cmd.append(client_secret)

            self.logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.error(f"Auth failed: {result.stderr}")
                self.authStateChanged.emit("error")
                self.setStatus("Authentication failed or cancelled.")
                return

            token_json = result.stdout.strip()
            try:
                json.loads(token_json)
            except json.JSONDecodeError:
                start = token_json.find('{')
                end = token_json.rfind('}') + 1
                if start != -1 and end != -1:
                    token_json = token_json[start:end]
                else:
                    raise Exception("Invalid token output from rclone")

            self.setStatus("Authentication successful. Saving configuration...")

            params = {
                "name": name,
                "type": "drive",
                "token": token_json
            }
            if client_id:
                params["client_id"] = client_id
            if client_secret:
                params["client_secret"] = client_secret

            backend_params = {
                "token": token_json
            }
            if client_id:
                backend_params["client_id"] = client_id
            if client_secret:
                backend_params["client_secret"] = client_secret

            parameters_json = json.dumps(backend_params)

            create_cmd = [
                "rclone", "rc", "config/create",
                f"name={name}",
                "type=drive",
                f"parameters={parameters_json}",
                "--rc-addr=localhost:5572",
                "--rc-user=rclone",
                f"--rc-pass={Config.get_rc_pass()}"
            ]

            subprocess.run(create_cmd, check=True)

            # --- Save credentials to keyring after successful auth ---
            if client_id and client_secret:
                self.logger.info("Saving Google credentials to system keyring...")
                SecretManager.save_google_credentials(client_id, client_secret)
                self._load_stored_credentials()

            self.authStateChanged.emit("success")
            self.setStatus("Drive created successfully!")
            self.finished.emit()

        except Exception as e:
            self.logger.exception("Error creating remote")
            self.authStateChanged.emit("error")
            self.setStatus(f"Error: {str(e)}")
