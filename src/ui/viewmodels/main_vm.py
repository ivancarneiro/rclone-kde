from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication
import logging
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

    def __init__(self, client, settings_manager, sync_manager):
        super().__init__()
        self._client = client
        self._settings_manager = settings_manager
        self._sync_manager = sync_manager
        
        from core.mount_manager import MountManager
        self._mount_manager = MountManager(client)
        
        self._remotes = []
        self._mounting_remotes = set() 
        self.logger = logging.getLogger(__name__)
        
        # Workers Activos
        self._status_worker = None
        self._mount_workers = {} # remote_name -> worker

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

    @pyqtSlot()
    def hide_window(self):
        if self._window: self._window.hide()
    
    @pyqtSlot()
    def show_window(self):
        if self._window:
            self._window.show()
            self._window.raise_()
            self._window.requestActivate()

    @pyqtProperty(list, notify=remotesChanged)
    def remotes_model(self):
        return self._remotes

    @pyqtSlot()
    def refresh_remotes(self):
        """Inicia la actualización de estados en segundo plano."""
        if self._status_worker and self._status_worker.isRunning():
            return
            
        self._status_worker = StatusWorker(self._client, self._mount_manager, self._sync_manager)
        self._status_worker.data_received.connect(self._on_status_data_received)
        self._status_worker.start()

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

    @pyqtSlot(str, bool, bool)
    def mount_remote(self, remote_name, read_only=False, network_mode=False):
        try:
            if remote_name in self._mounting_remotes: return
            
            self.logger.info(f"Mounting {remote_name}...")
            self._mounting_remotes.add(remote_name)
            self.refresh_remotes() # Update UI state
            
            worker = MountWorker(self._mount_manager, remote_name, read_only, network_mode)
            worker.finished_success.connect(self._on_mount_success)
            worker.finished_error.connect(lambda err: self._on_mount_error(remote_name, err))
            
            self._mount_workers[remote_name] = worker
            worker.start()
        except Exception as e:
            self.logger.exception(f"Error initiating mount: {e}")
            self._on_mount_error(remote_name, str(e))

    def _on_mount_success(self, result):
        remote_name = result.get("remote_name")
        self.logger.info(f"Mount success: {remote_name}")
        
        if remote_name in self._mounting_remotes:
            self._mounting_remotes.remove(remote_name)
        
        if result.get("action") != "unmount":
            NotificationManager.send("Drive Ready", f"{remote_name} is mounted.")
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
        worker = MountWorker(self._mount_manager, remote_name, is_unmount=True)
        worker.finished_success.connect(self._on_mount_success)
        worker.finished_error.connect(lambda err: self._on_mount_error(remote_name, err))
        worker.start()

    @pyqtSlot(str)
    def delete_remote(self, remote_name):
        # Para evitar bloquear la UI, se podría mover a un ConfigWorker,
        # pero para el borrado (acción poco frecuente) usaremos una llamada limpia.
        # Por ahora lo simplificamos para evitar el crash de loops anidados.
        self.logger.info(f"Deleting remote {remote_name}...")
        import subprocess
        from core.config import Config
        
        # Cleanup local
        mount_point = self._mount_manager.get_mount_point(remote_name)
        subprocess.run(["fusermount", "-uz", mount_point], check=False)
        self._settings_manager.remove_auto_mount(remote_name)
        
        # Borrado en rclone (vía shell para no liar loops aquí)
        subprocess.run(["rclone", "config", "delete", remote_name], check=False)
        self.refresh_remotes()
