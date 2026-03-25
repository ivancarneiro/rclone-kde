from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal
from PyQt6.QtWidgets import QFileDialog
import logging
import datetime
from core.sync_manager import SyncManager
from core.rclone_client import RcloneClient
from core.sync_worker import SyncWorker
from core.config import Config
from core.notifications import NotificationManager

class SyncViewModel(QObject):
    tasksChanged = pyqtSignal()
    logReceived = pyqtSignal(int, str, arguments=['taskId', 'logLine']) # Signal for QML: taskId, line
    
    def __init__(self, sync_manager: SyncManager, rclone_client: RcloneClient):
        super().__init__()
        self._manager = sync_manager
        self._client = rclone_client
        self.logger = logging.getLogger(__name__)
        self._active_workers = {} # task_id -> worker
        self._task_logs = {} # task_id -> list of strings

    @pyqtSlot(int, result=str)
    def get_task_logs(self, task_id):
        """Devuelve todos los logs acumulados para una tarea como un solo string."""
        return "\n".join(self._task_logs.get(task_id, []))

    def _on_sync_log(self, task_id, line):
        """Slot interno para recibir logs del worker."""
        if task_id not in self._task_logs:
            self._task_logs[task_id] = []
        
        # Guardar en memoria
        self._task_logs[task_id].append(line)
        # Emitir a QML
        self.logReceived.emit(task_id, line)

    @pyqtProperty(list, notify=tasksChanged)
    def tasks_model(self):
        return self._manager.get_tasks()

    @pyqtSlot(str, str, str, str)
    def add_task(self, name, local_path, remote_name, remote_path):
        """
        Crea una nueva tarea de sincronización.
        remote_path debe ser relativo al remote_name, ej: "Backup/Fotos"
        """
        self.logger.info(f"Adding task: {name}")
        self._manager.add_task(name, local_path, remote_path, remote_name)
        self.tasksChanged.emit()

    @pyqtSlot(int)
    def remove_task(self, task_id):
        self._manager.remove_task(task_id)
        self.tasksChanged.emit()

    @pyqtSlot(int, str, str, str, str)
    def edit_task(self, task_id, name, local_path, remote_name, remote_path):
        """Edita una tarea existente."""
        self.logger.info(f"Editing task {task_id}: {name}")
        self._manager.update_task(task_id, name, local_path, remote_path, remote_name)
        self.tasksChanged.emit()

    @pyqtSlot(int)
    def run_sync(self, task_id, force_resync=False):
        # Allow retry if force_resync is True even if "active" (technically we should cleanup first)
        if task_id in self._active_workers and not force_resync:
            return
            
        # Cleanup if we are forcing resync
        if force_resync and task_id in self._active_workers:
            self._cleanup_worker(task_id)

        task = next((t for t in self._manager.get_tasks() if t["id"] == task_id), None)
        if not task:
            return

        self.logger.info(f"Starting Sync Thread for {task['name']} (Resync: {force_resync})")
        
        # Actualizar estado
        status_msg = "Resyncing..." if force_resync else "Syncing..."
        self._manager.update_task_status(task_id, status_msg)
        self.tasksChanged.emit()
        
        # Construir rutas
        local = task["local_path"]
        remote = f"{task['remote_name']}:{task['remote_path']}"
        
        # Determinar si necesitamos resync (Primera vez o Forzado)
        cmd = [
            "rclone", "bisync", 
            local, remote, 
            "--verbose",
            "--config", Config.RCLONE_CONF,
            "--drive-acknowledge-abuse",
            "--max-delete", "5" # SAFETY BELT: Prevent massive deletions
        ]
        
        # Si nunca se ha sincronizado O es forzado, añadir --resync
        if force_resync or not task.get("last_sync"):
            self.logger.info("Adding --resync flag to recovery/init.")
            cmd.append("--resync")
        
        # Limpiar logs anteriores SI NO es un retry automático inmediato (para que se vea el error previo? No, mejor limpiar)
        if not force_resync: 
             self._task_logs[task_id] = []
        else:
             self._task_logs[task_id].append("--- AUTO-RECOVERY: Resyncing... ---")
        
        worker = SyncWorker(cmd)
        
        # Conectar señales
        worker.finished_success.connect(lambda t_id=task_id: self._on_sync_success(t_id))
        worker.finished_error.connect(lambda msg, t_id=task_id: self._on_sync_error(t_id, msg))
        worker.output_log.connect(lambda line, t_id=task_id: self._on_sync_log(t_id, line))
        
        self._active_workers[task_id] = worker
        worker.start()

    def _on_sync_log(self, task_id, line):
        """Slot interno para recibir logs del worker."""
        if task_id not in self._task_logs:
            self._task_logs[task_id] = []
        
        # Guardar en memoria
        self._task_logs[task_id].append(line)
        # Emitir a QML
        self.logReceived.emit(task_id, line)

            # CRITICAL ERROR DETECTION & AUTO-RECOVERY
        if "Must run --resync to recover" in line or "cannot find prior" in line:
            self.logger.warning(f"Task {task_id} corrupted. Triggering Auto-Resync...")
            
            # Implementation Strategy: 
            # Mark task as 'needs_resync'
            if self._active_workers.get(task_id):
                 self._active_workers[task_id].needs_resync = True

    def sync_all_on_startup(self):
        """Lanza todas las tareas de sync secuencial o paralelamente."""
        self.logger.info("Auto-syncing all tasks on startup...")
        for task in self._manager.get_tasks():
            self.run_sync(task["id"])

    @pyqtSlot(result=str)
    def select_local_folder(self):
        """Abre un diálogo nativo Qt para seleccionar carpeta."""
        folder = QFileDialog.getExistingDirectory(None, "Select Local Folder")
        return folder if folder else ""

    def _on_sync_success(self, task_id):
        self.logger.info(f"Sync success for task {task_id}")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._manager.update_task_status(task_id, "Idle", last_sync=now)
        self.tasksChanged.emit()
        self._cleanup_worker(task_id)

    def _on_sync_error(self, task_id, error_msg):
        # Check if this error triggered a resync need
        worker = self._active_workers.get(task_id)
        should_resync = getattr(worker, 'needs_resync', False) if worker else False
        
        self._cleanup_worker(task_id) # Cleanup OLD worker first
        
        if should_resync:
            self.logger.warning(f"Auto-Recovering task {task_id} with --resync...")
            # Schedule restart immediately (now that worker is gone)
            self.run_sync(task_id, force_resync=True)
            return

        self.logger.error(f"Sync error for task {task_id}: {error_msg}")
        self._manager.update_task_status(task_id, "Error")
        self.tasksChanged.emit()
        
        # Notificar al usuario (Tray Notification)
        task = next((t for t in self._manager.get_tasks() if t["id"] == task_id), None)
        task_name = task['name'] if task else f"Task {task_id}"
        
        NotificationManager.send(
            "Sync Warning ⚠️", 
            f"Conflicts/Errors in '{task_name}'. Check Logs.", 
            urgency="critical"
        )
    
    def _cleanup_worker(self, task_id):
        if task_id in self._active_workers:
            w = self._active_workers.pop(task_id)
            w.quit()
            w.wait()
            w.deleteLater()
