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
        # Crear un nuevo loop de eventos para este hilo
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self._running:
            try:
                # core/stats devuelve las transferencias activas y completadas de la sesión del daemon
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

        # Conectar señales de logs de sincronización (muy importante para DELETIONS y BISYNC)
        self._sync_vm.logReceived.connect(self._process_log)

        # Iniciar worker de estadísticas (para barras de progreso en tiempo real)
        self._worker = StatsWorker(self._client)
        self._worker.stats_ready.connect(self._update_live_transfers)
        self._worker.start()

    @pyqtProperty(list, notify=activityChanged)
    def activity_model(self):
        # Devolvemos una copia invertida para que lo más nuevo esté arriba
        return list(reversed(self._activity))

    @pyqtSlot()
    def clear_history(self):
        self._activity = []
        self.activityChanged.emit()

    def _update_live_transfers(self, stats):
        if not stats: return
            
        changed = False
        seen_active_names = set()
            
        # 1. Transferencias Activas (Uploads/Downloads en curso)
        current_transfers = stats.get("transferring", [])
        for t in current_transfers:
            name = t.get("name", "Unknown")
            seen_active_names.add(name)
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("bytes", 0), "syncing", is_active=True)
        
        # 2. Transferencias Completadas (Historial de la sesión rcd)
        completed_transfers = stats.get("transferred", [])
        for t in completed_transfers:
            name = t.get("name", "Unknown")
            changed |= self._add_or_update_item(name, t.get("size", 0), t.get("size", 0), "success", is_active=False)
        
        # 3. Limpieza de items que terminaron o desaparecieron de la cola activa
        for item in self._activity:
            if item["status"] == "syncing" and item["name"] not in seen_active_names:
                item["status"] = "success"
                item["progress"] = 100
                changed = True
                    
        if changed:
            self.activityChanged.emit()

    def _add_or_update_item(self, name, size, bytes_done, status, is_active):
        percentage = 100 if not is_active else (int((bytes_done / size) * 100) if size > 0 else 0)
        
        # Buscar item existente para actualizar
        for item in self._activity:
            if item["name"] == name:
                # Si ya terminó con éxito, no lo volvemos a poner en "syncing"
                if item["status"] in ["success", "deleted"] and status == "syncing":
                    return False
                
                updated = False
                if item["status"] != status:
                    item["status"] = status
                    updated = True
                if is_active and item["progress"] != percentage:
                    item["progress"] = percentage
                    updated = True
                return updated

        # Si es nuevo, lo agregamos
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
        # Limpiar prefijos de sistema y timestamps de rclone
        # Ejemplo: <6>INFO  : file.txt: Deleted -> file.txt: Deleted
        clean_line = re.sub(r'<\d+>|^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} ', '', line).strip()
        
        changed = False
        # Buscamos patrones de éxito, eliminación o error
        if "Deleted" in clean_line:
            filename = self._extract_filename(clean_line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "deleted", is_active=False)
        
        elif any(x in clean_line for x in ["Copied", "Updated", "Moved", "Synchronized"]):
            filename = self._extract_filename(clean_line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "success", is_active=False)
        
        elif "Failed to" in clean_line or "ERROR" in clean_line:
            filename = self._extract_filename(clean_line)
            if filename:
                changed = self._add_or_update_item(filename, 0, 0, "error", is_active=False)
                
        if changed:
            self.activityChanged.emit()

    def _extract_filename(self, line):
        # Expresión regular robusta para capturar el nombre del archivo en logs de rclone
        # Soporta: "INFO  : Mi Archivo.svg: Deleted" o "NOTICE: file.txt: Copied"
        match = re.search(r'(?:INFO|NOTICE|ERROR)\s+:\s+(.*?):', line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Fallback para líneas sin prefijo claro
        if ":" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                return parts[0].strip()
        return None

    def _guess_type(self, filename):
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in ["jpg", "png", "jpeg", "gif", "bmp", "webp", "svg"]: return "image-x-generic"
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
