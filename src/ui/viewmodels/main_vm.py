import os
from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication
import logging
import os
from core.config import Config
from core.mount_worker import MountWorker
from core.status_worker import StatusWorker
from core.notifications import NotificationManager

class MainViewModel(QObject):
    """
    ViewModel principal refactorizado (v2.0).
    Usa QThreads para todas las operaciones de red/IO para garantizar estabilidad.
    """
    remotesChanged = pyqtSignal()

    def __init__(self, client, settings_manager, sync_manager, mount_manager):
        super().__init__()
        self._client = client
        self._settings_manager = settings_manager
        self._sync_manager = sync_manager
        self._mount_manager = mount_manager
        
        self._remotes = []
        self._mounting_remotes = set() 
        self.logger = logging.getLogger(__name__)
        
        # Workers Activos
        self._status_worker = None
        self._mount_workers = {} # remote_name/action -> worker
        self._dead_workers = []

        # Monitor Timer (Lanza el StatusWorker)
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self.refresh_remotes)
        self._monitor_timer.start(5000) 

        self._window = None
        self._is_quitting = False
        self._initial_load_done = False

    def set_window(self, window):
        self._window = window

    @pyqtProperty(bool)
    def is_quitting(self):
        return self._is_quitting

    def quit_app(self):
        self._is_quitting = True
        self.logger.info("Quitting application...")
        if self._window:
            self._window.close()
        QApplication.quit()

    def stop(self):
        """Detiene timers y workers para un cierre limpio."""
        self.logger.info("Stopping MainViewModel background tasks...")
        if hasattr(self, '_monitor_timer'):
            self._monitor_timer.stop()
        
        # No usamos terminate() ya que puede causar ABRT si ocurre en un momento crítico.
        try:
            if self._status_worker and self._status_worker.isRunning():
                self.logger.debug("Waiting for status worker to finish...")
                self._status_worker.wait(1000)
        except RuntimeError:
            self._status_worker = None
        
        for name, worker in list(self._mount_workers.items()):
            try:
                if worker.isRunning():
                    self.logger.debug(f"Waiting for mount worker {name} to finish...")
                    worker.wait(1000)
            except RuntimeError:
                pass
        
        # Clean up dead workers
        self._cleanup_dead_workers()

    @pyqtProperty(str, constant=True)
    def mount_dir(self):
        return Config.mount_dir

    @pyqtProperty(bool, notify=remotesChanged)
    def hasGoogleCredentials(self):
        from core.secret_manager import SecretManager
        return SecretManager.has_google_credentials()

    @pyqtSlot()
    def hide_window(self):
        if self._window:
            self._window.hide()
    
    @pyqtSlot()
    def show_window(self):
        if self._window:
            self._window.show()
            self._window.raise_()
            self._window.requestActivate()

    @pyqtSlot()
    def alert_window(self):
        """
        Flash the window in the taskbar to draw user attention.
        Works on both X11 and Wayland (unlike raise_/requestActivate).
        Use this before blocking operations that may show system dialogs (KDE Wallet).
        """
        if self._window:
            try:
                # QQuickWindow inherits QWindow which has alert(int msec)
                self._window.alert(5000)
            except AttributeError:
                self.logger.debug("alert() not available on this window")
            try:
                from PyQt6.QtWidgets import QApplication
                # Also try QApplication.alert() as fallback
                QApplication.alert(self._window, 5000)
            except Exception:
                pass

    @pyqtProperty(list, notify=remotesChanged)
    def remotes_model(self):
        return self._remotes

    @pyqtSlot()
    def refresh_remotes(self):
        """Inicia la actualización de estados en segundo plano."""
        self._cleanup_dead_workers()
        try:
            if self._status_worker and self._status_worker.isRunning():
                return
        except RuntimeError:
            self._status_worker = None
            
        self._status_worker = StatusWorker(self._client, self._mount_manager, self._sync_manager, self)
        self._status_worker.data_received.connect(self._on_status_data_received)
        self._status_worker.finished.connect(self._on_status_worker_finished)
        self._status_worker.start()

    def _on_status_worker_finished(self):
        if self._status_worker:
            self._dead_workers.append(self._status_worker)
            self._status_worker = None

    def _cleanup_dead_workers(self):
        """Reaps dead QThread workers to prevent GC while OS threads are winding down."""
        still_alive = []
        for w in self._dead_workers:
            try:
                if w.isRunning():
                    still_alive.append(w)
                else:
                    w.deleteLater()
            except RuntimeError:
                pass
        self._dead_workers = still_alive

    def _on_status_data_received(self, data):
        """Recibe los datos del worker y actualiza el modelo."""
        try:
            self._remotes = data
            
            # Manejo de estados de carga locales
            for remote in self._remotes:
                remote['is_loading'] = remote['name'] in self._mounting_remotes
                
            self.remotesChanged.emit()
            
            # Procesar auto-montaje una sola vez
            if not self._initial_load_done:
                self._initial_load_done = True
                self._process_auto_mounts()
        except Exception as e:
            self.logger.exception(f"Error processing status data: {e}")

    def _process_auto_mounts(self):
        auto_mounts = self._settings_manager.get_auto_mounts()
        for remote in self._remotes:
            name = remote['name']
            if name in auto_mounts and not remote['is_mounted']:
                self.mount_remote(name)

    @pyqtSlot(str, bool, bool)
    def mount_remote(self, remote_name, read_only=False, network_mode=False):
        try:
            if remote_name in self._mounting_remotes:
                return
            
            self.logger.info(f"Mounting {remote_name}...")
            self._mounting_remotes.add(remote_name)
            self.refresh_remotes() # Update UI state
            
            worker = MountWorker(self._mount_manager, remote_name, read_only, network_mode, parent=self)
            worker.finished_success.connect(self._on_mount_success)
            worker.finished_error.connect(lambda err: self._on_mount_error(remote_name, err))
            
            # Cleanup on finish
            worker.finished.connect(lambda: self._cleanup_mount_worker(remote_name))
            
            self._mount_workers[remote_name] = worker
            worker.start()
        except Exception as e:
            self.logger.exception(f"Error initiating mount: {e}")
            self._on_mount_error(remote_name, str(e))

    def _cleanup_mount_worker(self, key):
        """Remueve el worker del diccionario una vez finalizado y lo deriva a reap."""
        if key in self._mount_workers:
            worker = self._mount_workers.pop(key)
            self._dead_workers.append(worker)

    def _on_mount_success(self, result):
        remote_name = result.get("remote_name")
        self.logger.info(f"Mount success: {remote_name}")
        
        if remote_name in self._mounting_remotes:
            self._mounting_remotes.remove(remote_name)
        
        if result.get("action") != "unmount":
            NotificationManager.send("Drive Ready", f"{remote_name} is mounted.")
            
            # Lanzar KeePassXC si está configurado para este remoto
            kp_config = self._settings_manager.get_keepassxc_config()
            if kp_config["remote"] == remote_name:
                mount_point = result.get("mount_point")
                db_path = os.path.join(mount_point, kp_config["db_path"])
                
                if os.path.exists(db_path):
                    self.logger.info(f"Launching KeePassXC with DB: {db_path}")
                    import subprocess
                    subprocess.Popen(["keepassxc", db_path])
                    NotificationManager.send("KeePassXC", "Database loaded automatically.")
                else:
                    self.logger.warning(f"KeePassXC DB not found at {db_path}")

            # Abrir Dolphin
            import subprocess
            subprocess.Popen(["xdg-open", result.get("mount_point")])
        
        self.refresh_remotes()

    def _on_mount_error(self, remote_name, error_msg):
        self.logger.error(f"Mount error for {remote_name}: {error_msg}")
        if remote_name in self._mounting_remotes:
            self._mounting_remotes.remove(remote_name)
        
        NotificationManager.send("Mount Failed", error_msg, urgency="critical")
        self.refresh_remotes()

    @pyqtSlot(str)
    def unmount_remote(self, remote_name):
        self.logger.info(f"Unmounting {remote_name}...")
        worker = MountWorker(self._mount_manager, remote_name, is_unmount=True, parent=self)
        worker.finished_success.connect(self._on_mount_success)
        worker.finished_error.connect(lambda err: self._on_mount_error(remote_name, err))
        
        key = f"unmount_{remote_name}"
        worker.finished.connect(lambda: self._cleanup_mount_worker(key))
        
        # Guardamos referencia para evitar GC y ABRT
        self._mount_workers[key] = worker
        worker.start()

    # ------------------------------------------------------------------
    # Reconnect Remote
    # ------------------------------------------------------------------

    reconnectStateChanged = pyqtSignal(str, str)  # remote_name, state: "idle"|"reconnecting"|"success"|"error"
    reconnectStatusMessageChanged = pyqtSignal(str, str)  # remote_name, message

    @pyqtSlot(str)
    def reconnect_remote(self, remote_name):
        """
        Reautoriza un remote Google Drive usando las credenciales almacenadas en el keyring.
        Paso 1: Actualiza client_id/client_secret en el remote
        Paso 2: Abre el navegador para reautorizar
        Paso 3: Actualiza el token en el remote
        """
        from core.secret_manager import SecretManager
        import subprocess
        import json

        self.logger.info(f"Reconnecting remote: {remote_name}")
        self.reconnectStateChanged.emit(remote_name, "reconnecting")
        self.reconnectStatusMessageChanged.emit(remote_name, "Checking stored credentials...")

        # 1. Obtener credenciales del keyring
        creds = SecretManager.get_google_credentials()
        if not creds:
            self.logger.error(f"No stored credentials found for reconnecting {remote_name}")
            self.reconnectStateChanged.emit(remote_name, "error")
            self.reconnectStatusMessageChanged.emit(remote_name, "❌ No credentials in keyring. Save them in Settings first.")
            return

        try:
            # 2. Actualizar client_id y client_secret (sin refrescar token aún)
            self.reconnectStatusMessageChanged.emit(remote_name, "Updating credentials...")
            update_cmd = [
                "rclone", "config", "update", remote_name,
                f"client_id={creds.client_id}",
                f"client_secret={creds.client_secret}",
                "config_refresh_token=false"
            ]
            result = subprocess.run(update_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                raise Exception(f"Config update failed: {result.stderr}")
            self.logger.info(f"Updated client_id/secret for {remote_name}")

            # 3. Reautorizar (abre navegador)
            self.reconnectStatusMessageChanged.emit(remote_name, "🔐 Opening browser for Google authorization...")
            auth_cmd = ["rclone", "authorize", "drive", creds.client_id]
            if creds.client_secret:
                auth_cmd.append(creds.client_secret)

            self.logger.info(f"Running: {' '.join(auth_cmd)}")
            auth_result = subprocess.run(auth_cmd, capture_output=True, text=True, timeout=120)

            if auth_result.returncode != 0:
                raise Exception(f"Authorization failed: {auth_result.stderr}")

            # 4. Parsear token del stdout
            token_json = auth_result.stdout.strip()
            try:
                json.loads(token_json)
            except json.JSONDecodeError:
                start = token_json.find('{')
                end = token_json.rfind('}') + 1
                if start != -1 and end != -1:
                    token_json = token_json[start:end]
                else:
                    raise Exception("Invalid token output from rclone authorize")

            # 5. Actualizar token en el remote
            self.reconnectStatusMessageChanged.emit(remote_name, "Saving new token...")
            token_cmd = ["rclone", "config", "update", remote_name, f"token={token_json}"]
            result = subprocess.run(token_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                raise Exception(f"Token update failed: {result.stderr}")

            self.logger.info(f"Reconnect successful for {remote_name}")
            self.reconnectStateChanged.emit(remote_name, "success")
            self.reconnectStatusMessageChanged.emit(remote_name, "✅ Reconnected successfully!")
            self.refresh_remotes()

        except subprocess.TimeoutExpired:
            self.logger.error(f"Reconnect timed out for {remote_name}")
            self.reconnectStateChanged.emit(remote_name, "error")
            self.reconnectStatusMessageChanged.emit(remote_name, "⏱️ Authorization timed out. Try again.")
        except Exception as e:
            self.logger.exception(f"Reconnect failed for {remote_name}")
            self.reconnectStateChanged.emit(remote_name, "error")
            self.reconnectStatusMessageChanged.emit(remote_name, f"❌ Error: {str(e)}")

    @pyqtSlot(str)
    def delete_remote(self, remote_name):
        # Para evitar bloquear la UI, se podría mover a un ConfigWorker,
        # pero para el borrado (acción poco frecuente) usaremos una llamada limpia.
        # Por ahora lo simplificamos para evitar el crash de loops anidados.
        self.logger.info(f"Deleting remote {remote_name}...")
        import subprocess
        
        # Cleanup local
        mount_point = self._mount_manager.get_mount_point(remote_name)
        subprocess.run(["fusermount", "-uz", mount_point], check=False)
        self._settings_manager.remove_auto_mount(remote_name)
        
        # Borrado en rclone (vía shell para no liar loops aquí)
        subprocess.run(["rclone", "config", "delete", remote_name], check=False)
        self.refresh_remotes()
