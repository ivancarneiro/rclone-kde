import asyncio
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, QTimer, pyqtSlot
import logging
import datetime

class ActivityViewModel(QObject):
    activityChanged = pyqtSignal()

    def __init__(self, rclone_client, sync_vm):
        super().__init__()
        self._client = rclone_client
        self._sync_vm = sync_vm
        self._activity = []
        self.logger = logging.getLogger(__name__)

        # Connect log signal from SyncViewModel
        self._sync_vm.logReceived.connect(self._process_log)

        # Polling Timer (1.0s para mayor respuesta)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_stats)
        self._timer.start(1000)

    @pyqtProperty(list, notify=activityChanged)
    def activity_model(self):
        # Return reversed list to show newest on top
        return list(reversed(self._activity))

    @pyqtSlot()
    def clear_history(self):
        self._activity = []
        self.activityChanged.emit()

    def _poll_stats(self):
        try:
             # Ejecutamos la llamada asíncrona de forma segura para Qt
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             stats = loop.run_until_complete(self._client.core_stats())
             loop.close()
             self._update_live_transfers(stats)
        except Exception as e:
             self.logger.debug(f"Stats poll error: {e}") 

    def _update_live_transfers(self, stats):
        if not stats: 
            return
            
        changed = False
        seen_active_names = set()
            
        # 1. Active Transfers (Lo que rclone está haciendo AHORA)
        current_transfers = stats.get("transferring", [])
        for t in current_transfers:
            name = t.get("name", "Unknown")
            seen_active_names.add(name)
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("bytes", 0), "syncing", is_active=True)
        
        # 2. Completed Transfers (Historial de la sesión de rclone)
        completed_transfers = stats.get("transferred", [])
        for t in completed_transfers:
            name = t.get("name", "Unknown")
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("size", 0), "success", is_active=False)
        
        # 3. Cleanup Ghosts (Items que desaparecieron de 'transferring' sin ir a 'transferred')
        for item in self._activity:
            if item["status"] == "syncing" and item["name"] not in seen_active_names:
                # Si ya no está transfiriendo, asumimos que terminó o se movió al historial
                item["status"] = "success"
                item["progress"] = 100
                changed = True
                    
        if changed:
            self.activityChanged.emit()

    def _add_or_update_item(self, name, size, bytes_done, status, is_active):
        percentage = 100 if not is_active else (int((bytes_done / size) * 100) if size > 0 else 0)
        
        # Buscar duplicado para actualizar
        for item in self._activity:
            if item["name"] == name:
                # No bajamos de status (si ya es success, no vuelve a syncing)
                if item["status"] == "success" and status == "syncing":
                    return False
                
                updated = False
                if item["status"] != status:
                    item["status"] = status
                    updated = True
                if is_active and item["progress"] != percentage:
                    item["progress"] = percentage
                    updated = True
                return updated

        # Si no existe, lo agregamos
        new_item = {
            "name": name,
            "type": self._guess_type(name),
            "size": self._sizeof_fmt(size),
            "status": status,
            "progress": percentage,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
        }
        self._activity.append(new_item)
        return True

    def _process_log(self, task_id, line):
        # El Activity Monitor también escucha los logs crudos para detectar DELETIONS
        # que rclone core/stats NO reporta como transferencias.
        changed = False
        
        if "Deleted" in line:
            filename = self._extract_filename(line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "deleted", is_active=False)
        
        elif "Copied" in line:
            filename = self._extract_filename(line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "success", is_active=False)
                
        if changed:
            self.activityChanged.emit()

    def _extract_filename(self, line):
        # Espera formato: "INFO  : folder/file.txt: Deleted"
        parts = line.split(":")
        if len(parts) >= 3:
            return parts[-2].strip()
        return None

    def _guess_type(self, filename):
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in ["jpg", "png", "jpeg", "gif", "bmp", "webp"]: return "image-x-generic"
        if ext in ["mp4", "mkv", "avi", "mov"]: return "video-x-generic"
        if ext in ["mp3", "wav", "flac"]: return "audio-x-generic"
        if ext in ["pdf", "doc", "docx", "txt", "md"]: return "application-pdf"
        if ext in ["zip", "rar", "tar", "gz", "7z"]: return "package-x-generic"
        return "text-plain"

    def _sizeof_fmt(self, num, suffix="B"):
        if num == 0: return "0.0B"
        for unit in ["", "Ki", "Mi", "Gi", "Ti"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Pi{suffix}"
