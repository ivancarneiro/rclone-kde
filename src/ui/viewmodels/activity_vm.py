import asyncio
import logging
import datetime
import time
import re
import os
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, QTimer, pyqtSlot, QThread

class StatsWorker(QThread):
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
                stats = loop.run_until_complete(self._client.core_stats())
                if stats and isinstance(stats, dict) and "error" not in stats:
                    self.stats_ready.emit(stats)
            except Exception as e:
                logging.debug(f"Stats worker error: {e}")
            loop.run_until_complete(asyncio.sleep(1.0))
        loop.close()

class LogTailWorker(QThread):
    """
    Worker que hace 'tail -f' del log de rclone para detectar actividad de monturas (FUSE)
    que no pasan por las tareas de sincronización explícitas.
    """
    log_received = pyqtSignal(str)

    def __init__(self, log_path):
        super().__init__()
        self.log_path = log_path
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        if not os.path.exists(self.log_path):
            # Crear archivo vacío si no existe
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            open(self.log_path, 'a').close()

        with open(self.log_path, 'r') as f:
            # Ir al final del archivo para no procesar historia vieja
            f.seek(0, os.SEEK_END)
            
            while self._running:
                line = f.readline()
                if not line:
                    time.sleep(0.5) # Esperar nuevas lineas
                    continue
                
                clean_line = line.strip()
                if clean_line:
                    self.log_received.emit(clean_line)

class ActivityViewModel(QObject):
    activityChanged = pyqtSignal()

    def __init__(self, rclone_client, sync_vm):
        super().__init__()
        self._client = rclone_client
        self._sync_vm = sync_vm
        self._activity = []
        self.logger = logging.getLogger(__name__)

        # 1. Escuchar logs de tareas de sincronización (Bisync/Sync de la app)
        self._sync_vm.logReceived.connect(self._process_log)

        # 2. Escuchar logs del demonio global (Actividad de Monturas FUSE / Dolphin)
        log_path = os.path.expanduser("~/.cache/rclone-kde.log")
        self._log_worker = LogTailWorker(log_path)
        self._log_worker.log_received.connect(self._process_daemon_log)
        self._log_worker.start()

        # 3. Worker para estadísticas de red (Barras de progreso)
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
        current_transfers = stats.get("transferring", [])
        for t in current_transfers:
            name = t.get("name", "Unknown")
            seen_active_names.add(name)
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("bytes", 0), "syncing", is_active=True)
        completed_transfers = stats.get("transferred", [])
        for t in completed_transfers:
            name = t.get("name", "Unknown")
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("size", 0), "success", is_active=False)
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
                if item["status"] in ["success", "deleted", "error"] and status == "syncing":
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
            "type": self._guess_icon_by_extension(name),
            "size": self._sizeof_fmt(size),
            "status": status,
            "progress": percentage,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
        }
        self._activity.append(new_item)
        return True

    def _process_daemon_log(self, line):
        """Procesa logs que vienen del demonio global (FUSE)."""
        # Evitar procesar logs de DEBUG del demonio que ensucian
        if "DEBUG :" in line or "core/stats" in line: return
        self._process_log(0, line)

    def _process_log(self, task_id, line):
        # Limpieza de prefijos rclone
        clean_line = re.sub(r'<\d+>|^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} ', '', line).strip()
        
        # Mapeo universal agnóstico
        parts = clean_line.split(":")
        if len(parts) < 3: return
        
        filename = parts[-2].strip()
        action = parts[-1].strip().lower()
        
        changed = False
        if "deleted" in action:
            changed = self._add_or_update_item(filename, 0, 0, "deleted", False)
        elif any(kw in action for kw in ["copied", "updated", "moved", "synchronized", "replaced", "vfs cache: successfully uploaded"]):
            changed = self._add_or_update_item(filename, 0, 0, "success", False)
        elif "failed" in action or "error" in action:
            changed = self._add_or_update_item(filename, 0, 0, "error", False)
                
        if changed:
            self.activityChanged.emit()

    def _guess_icon_by_extension(self, filename):
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        icon_map = {
            "image": ["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp", "ico"],
            "video": ["mp4", "mkv", "avi", "mov", "wmv", "flv"],
            "audio": ["mp3", "wav", "flac", "ogg", "m4a"],
            "doc": ["pdf", "doc", "docx", "txt", "md", "odt", "rtf", "xls", "xlsx", "ppt", "pptx"],
            "archive": ["zip", "rar", "tar", "gz", "7z", "deb", "rpm", "iso"]
        }
        if ext in icon_map["image"]: return "image-x-generic"
        if ext in icon_map["video"]: return "video-x-generic"
        if ext in icon_map["audio"]: return "audio-x-generic"
        if ext in icon_map["doc"]: return "application-pdf"
        if ext in icon_map["archive"]: return "package-x-generic"
        return "text-plain"

    def _sizeof_fmt(self, num, suffix="B"):
        if num == 0: return "-"
        for unit in ["", "Ki", "Mi", "Gi", "Ti"]:
            if abs(num) < 1024.0: return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Pi{suffix}"
