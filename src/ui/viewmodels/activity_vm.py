import asyncio
import logging
import datetime
import time
import re
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, QTimer, pyqtSlot, QThread

class StatsWorker(QThread):
    """Worker para estadísticas de transferencia pesada (barra de progreso)."""
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

class ActivityViewModel(QObject):
    activityChanged = pyqtSignal()

    def __init__(self, rclone_client, sync_vm):
        super().__init__()
        self._client = rclone_client
        self._sync_vm = sync_vm
        self._activity = [] # Lista de diccionarios con eventos
        self.logger = logging.getLogger(__name__)

        # Conectar al flujo de logs crudos de las tareas
        self._sync_vm.logReceived.connect(self._process_log)

        # Worker para transferencias activas (basado en API)
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
        """Procesa datos de la API core/stats (transferencias pesadas)."""
        if not stats: return
        changed = False
        seen_active_names = set()
        
        # 1. Items transfiriéndose AHORA
        current_transfers = stats.get("transferring", [])
        for t in current_transfers:
            name = t.get("name", "Unknown")
            seen_active_names.add(name)
            changed |= self._add_or_update_item(
                name=name, 
                size=t.get("size", 0), 
                bytes_done=t.get("bytes", 0), 
                status="syncing", 
                is_active=True
            )
        
        # 2. Items terminados reportados por rclone
        completed_transfers = stats.get("transferred", [])
        for t in completed_transfers:
            name = t.get("name", "Unknown")
            changed |= self._add_or_update_item(
                name=name, 
                size=t.get("size", 0), 
                bytes_done=t.get("size", 0), 
                status="success", 
                is_active=False
            )
            
        # 3. Limpieza de items que terminaron entre encuestas
        for item in self._activity:
            if item["status"] == "syncing" and item["name"] not in seen_active_names:
                item["status"] = "success"
                item["progress"] = 100
                changed = True
                    
        if changed:
            self.activityChanged.emit()

    def _process_log(self, task_id, line):
        """
        MOTOR UNIVERSAL DE CAPTURA: Captura CUALQUIER archivo reportado en los logs.
        Estructura típica de rclone: "INFO : <archivo>: <accion>"
        """
        # 1. Limpiar prefijos de sistema
        clean_line = re.sub(r'<\d+>|^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} ', '', line).strip()
        
        # 2. Extraer archivo y acción basándonos en la estructura : <archivo>: <accion>
        # Buscamos el patrón: [NIVEL] : [ARCHIVO] : [ACCIÓN]
        parts = clean_line.split(":")
        if len(parts) < 3: return # No es un log de operación de archivo
        
        # El nombre suele ser la penúltima parte, la acción la última
        filename = parts[-2].strip()
        action = parts[-1].strip().lower()
        
        changed = False
        # Mapeo de estados agnóstico a la extensión
        if "deleted" in action:
            changed = self._add_or_update_item(filename, 0, 0, "deleted", False)
        elif any(kw in action for kw in ["copied", "updated", "moved", "synchronized", "replaced"]):
            changed = self._add_or_update_item(filename, 0, 0, "success", False)
        elif "failed" in action or "error" in action:
            changed = self._add_or_update_item(filename, 0, 0, "error", False)
                
        if changed:
            self.activityChanged.emit()

    def _add_or_update_item(self, name, size, bytes_done, status, is_active):
        """Gestiona la lista interna evitando duplicados y manteniendo estados."""
        percentage = 100 if not is_active else (int((bytes_done / size) * 100) if size > 0 else 0)
        
        for item in self._activity:
            if item["name"] == name:
                # Si ya tenemos un estado final (exito/borrado/error), no volvemos a 'syncing'
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

        # Si el monitor no lo conoce, se agrega
        new_item = {
            "name": name,
            "type": self._guess_icon_by_extension(name), # Solo para el icono visual
            "size": self._sizeof_fmt(size),
            "status": status,
            "progress": percentage,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
        }
        self._activity.append(new_item)
        return True

    def _guess_icon_by_extension(self, filename):
        """Asigna un icono basado en extensiones comunes, con un fallback genérico."""
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        icon_map = {
            "image": ["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp", "ico"],
            "video": ["mp4", "mkv", "avi", "mov", "wmv", "flv"],
            "audio": ["mp3", "wav", "flac", "ogg", "m4a"],
            "doc": ["pdf", "doc", "docx", "txt", "md", "odt", "rtf"],
            "archive": ["zip", "rar", "tar", "gz", "7z", "deb", "rpm", "iso"]
        }
        
        if ext in icon_map["image"]: return "image-x-generic"
        if ext in icon_map["video"]: return "video-x-generic"
        if ext in icon_map["audio"]: return "audio-x-generic"
        if ext in icon_map["doc"]: return "application-pdf"
        if ext in icon_map["archive"]: return "package-x-generic"
        return "text-plain" # Icono por defecto para cualquier otro tipo

    def _sizeof_fmt(self, num, suffix="B"):
        if num == 0: return "-"
        for unit in ["", "Ki", "Mi", "Gi", "Ti"]:
            if abs(num) < 1024.0: return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Pi{suffix}"
