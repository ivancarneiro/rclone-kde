import asyncio
import logging
import datetime
import time
import re
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, QTimer, pyqtSlot, QThread

class StatsWorker(QThread):
    """
    Worker en segundo plano para consultar estadísticas sin bloquear la UI.
    """
    stats_ready = pyqtSignal(dict)

    def __init__(self, client):
        super().__init__()
        self._client = client
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self._running:
            try:
                # Usar un timeout para no quedar bloqueado si la red cae
                stats = loop.run_until_complete(self._client.core_stats())
                if stats and "error" not in stats:
                    self.stats_ready.emit(stats)
            except Exception as e:
                logging.debug(f"Stats worker error: {e}")
            
            # Esperar 1 segundo antes de la siguiente consulta
            loop.run_until_complete(asyncio.sleep(1.0))
        
        loop.close()

class ActivityViewModel(QObject):
    activityChanged = pyqtSignal()

    def __init__(self, rclone_client, sync_vm):
        super().__init__()
        self._client = rclone_client
        self._sync_vm = sync_vm
        self._activity = []
        self.logger = logging.getLogger(__name__)

        # Conectar señales de logs de sincronización
        self._sync_vm.logReceived.connect(self._process_log)

        # Iniciar worker de estadísticas
        self._worker = StatsWorker(self._client)
        self._worker.stats_ready.connect(self._update_live_transfers)
        self._worker.start()

    @pyqtProperty(list, notify=activityChanged)
    def activity_model(self):
        return list(reversed(self._activity))

    @pyqtSlot()
    def clear_history(self):
        self._activity = []
        self.activityChanged.emit()

    def _update_live_transfers(self, stats):
        if not stats: return
            
        changed = False
        seen_active_names = set()
            
        # 1. Transferencias Activas
        current_transfers = stats.get("transferring", [])
        for t in current_transfers:
            name = t.get("name", "Unknown")
            seen_active_names.add(name)
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("bytes", 0), "syncing", is_active=True)
        
        # 2. Transferencias Completadas
        completed_transfers = stats.get("transferred", [])
        for t in completed_transfers:
            name = t.get("name", "Unknown")
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("size", 0), "success", is_active=False)
        
        # 3. Limpieza de items que ya no están activos
        for item in self._activity:
            if item["status"] == "syncing" and item["name"] not in seen_active_names:
                item["status"] = "success"
                item["progress"] = 100
                changed = True
                    
        if changed:
            self.activityChanged.emit()

    def _add_or_update_item(self, name, size, bytes_done, status, is_active):
        percentage = 100 if not is_active else (int((bytes_done / size) * 100) if size > 0 else 0)
        
        for item in self._activity:
            if item["name"] == name:
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
        # Limpiar prefijos de sistema <6>INFO o timestamps
        clean_line = re.sub(r'<\d+>|^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} ', '', line)
        
        changed = False
        if "Deleted" in clean_line:
            filename = self._extract_filename(clean_line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "deleted", is_active=False)
        elif "Copied" in clean_line or "Updated modification time" in clean_line:
            filename = self._extract_filename(clean_line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "success", is_active=False)
        elif "Failed to" in clean_line:
            filename = self._extract_filename(clean_line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "error", is_active=False)
                
        if changed:
            self.activityChanged.emit()

    def _extract_filename(self, line):
        # Busca patrones tipo "INFO  : filename: status"
        match = re.search(r'INFO\s+:\s+(.*?):', line)
        if match:
            return match.group(1).strip()
        # Fallback a split si el regex falla
        parts = line.split(":")
        return parts[-2].strip() if len(parts) >= 3 else None

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
