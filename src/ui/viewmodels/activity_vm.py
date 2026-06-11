import asyncio
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, QTimer
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

        # Polling Timer (1.5s to avoid spamming process creation)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_stats)
        self._timer.start(1500)

    @pyqtProperty(list, notify=activityChanged)
    def activity_model(self):
        # Return reversed list to show newest on top
        return list(reversed(self._activity))

    def _poll_stats(self):
        try:
             # Run async call in a fresh loop (MVP style)
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             stats = loop.run_until_complete(self._client.core_stats())
             loop.close()
             self._update_live_transfers(stats)
        except Exception:
             # Just logging debug to avoid flooding if rclone is busy/off
             # self.logger.debug(f"Stats poll error: {e}") 
             pass

    def _update_live_transfers(self, stats):
        if not stats: 
            return
            
        # Track names seen in this poll to detect stalled items
        seen_active_names = set()
            
        # 1. Active Transfers
        current_transfers = stats.get("transferring", [])
        if current_transfers:
            for t in current_transfers:
                seen_active_names.add(t.get("name"))
        
        self._process_stats_list(current_transfers, is_active=True)
        
        # 2. Completed Transfers (Rich metadata for history)
        completed_transfers = stats.get("transferred", [])
        self._process_stats_list(completed_transfers, is_active=False)
        
        # 3. Cleanup Ghosts (Stale "syncing" items)
        # If an item is "syncing" locally but NOT in "transferring" anymore,
        # it means it finished (or errored) between polls and we missed the event in "transferred" buffer.
        # We assume success to clear the UI.
        transferring_count = 0
        for item in self._activity:
            if item["status"] == "syncing":
                if item["name"] not in seen_active_names:
                    # It disappeared from active list -> Mark as success
                    item["status"] = "success"
                    item["progress"] = 100
                    # self.logger.debug(f"Marking ghost item as success: {item['name']}")
                else:
                    transferring_count += 1
                    
        # Debug summary
        # self.logger.debug(f"Active: {len(seen_active_names)}, Syncing in UI: {transferring_count}")

    def _process_stats_list(self, items_list, is_active):
        if not items_list:
            return
        
        changed = False
        for t in items_list:
            name = t.get("name", "Unknown")
            size = t.get("size", 0)
            bytes_done = t.get("bytes", 0)
            # For completed items, ensure we show 100%
            percentage = 100 if not is_active else (int((bytes_done / size) * 100) if size > 0 else 0)
            
            # Status mapping
            status = "syncing"
            if not is_active:
                 # Check 'success' field if available, or assume success for 'transferred' list
                 # Rclone 'transferred' usually means success.
                 status = "success" 
                 if not t.get("checked", False) and not t.get("success", True):
                     status = "error" # Just in case

            # Find in current list to update
            found = False
            for item in self._activity:
                # We match by name. 
                # Be careful not to overwrite a "success" state with "syncing" if order is mixed,
                # but "transferred" list should be authoritative for final state.
                if item["name"] == name:
                    # Update info
                    if item["size"] == "-" or item["size"] == "0.0B": # Update size if missing
                        item["size"] = self._sizeof_fmt(size)
                    
                    # Update progress/status if we found a "better" state (e.g. transitioning syncing -> success)
                    if item["status"] == "syncing" and status == "success":
                        item["status"] = status
                        item["progress"] = 100
                    elif item["status"] == "syncing" and is_active:
                        item["progress"] = percentage
                    
                    found = True
                    changed = True
                    break
            
            if not found:
                # Add new item
                new_item = {
                    "name": name,
                    "type": self._guess_type(name),
                    "size": self._sizeof_fmt(size),
                    "status": status,
                    "progress": percentage,
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
                }
                # Insert at TOP if using list view (but here we append, QML reverses)
                self._activity.append(new_item)
                changed = True
        
        if changed:
            self.activityChanged.emit()

    def _process_log(self, task_id, line):
        # Parse Rclone Logs
        # Examples:
        # "INFO  : filename.ext: Copied (new)"
        # "INFO  : filename.ext: Deleted"
        # "ERROR : filename.ext: Failed to copy: ..."
        
        if "Copied (new)" in line or "Copied (replaced)" in line:
            self._add_or_update_history(line, "success")
        elif "Deleted" in line:
            self._add_or_update_history(line, "deleted")
        elif "Failed to" in line or "Error:" in line:
            self._add_or_update_history(line, "error")

    def _add_or_update_history(self, line, status):
        # Extract filename (Approximate)
        # Format: "2023/01/01 ... INFO : filename: Status"
        filename = None
        
        parts = line.split(":")
        if len(parts) >= 3:
            # Standard file log: "INFO : filename: Status"
            # parts[-1] = " Copied (new)"
            # parts[-2] = " folder/file.txt"
            filename = parts[-2].strip()
        elif "Transferred" in line and "ETA" in line:
            # Summary line: Transferred: 1.2M / 1.2M, 100%, ...
            # We treat this as a generic "Sync Completed" event if we missed individual files
            filename = "Batch Transfer"
            status = "success"
        else:
             return # Skip unparseable

        # Check if we have this file in "syncing" state to update it
        found = False
        for item in self._activity:
            if item["name"] == filename and item["status"] == "syncing":
                item["status"] = status
                item["progress"] = 100
                found = True
                break
        
        if not found:
            # Add new history item
            new_item = {
                "name": filename,
                "type": self._guess_type(filename),
                "size": "-", # size unknown from log line often
                "status": status,
                "progress": 100,
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
            }
            self._activity.append(new_item)
        
        self.activityChanged.emit()


    def _guess_type(self, filename):
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in ["jpg", "png", "jpeg", "gif", "bmp"]:
            return "image-x-generic"
        if ext in ["mp4", "mkv", "avi", "mov"]:
            return "video-x-generic"
        if ext in ["mp3", "wav", "flac"]:
            return "audio-x-generic"
        if ext in ["pdf", "doc", "docx", "txt", "md"]:
            return "application-pdf"  # Generic doc
        if ext in ["zip", "rar", "tar", "gz"]:
            return "package-x-generic"
        return "text-plain"

    def _sizeof_fmt(self, num, suffix="B"):
        for unit in ["", "Ki", "Mi", "Gi", "Ti"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Pi{suffix}"
