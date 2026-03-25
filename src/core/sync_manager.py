import json
import os
import logging
from .config import Config

class SyncManager:
    """
    Gestiona la persistencia de las tareas de sincronización.
    Guarda pares (Local Path <-> Remote Path) en un JSON.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Guardar en el directorio base de la app
        self.tasks_file = os.path.join(Config.base_dir, "sync_tasks.json")
        self._tasks = []
        self.load_tasks()

    def load_tasks(self):
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, 'r') as f:
                    self._tasks = json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading sync tasks: {e}")
                self._tasks = []
        else:
            self._tasks = []

    def save_tasks(self):
        try:
            with open(self.tasks_file, 'w') as f:
                json.dump(self._tasks, f, indent=4)
        except Exception as e:
            self.logger.error(f"Error saving sync tasks: {e}")

    def get_tasks(self):
        return self._tasks

    def add_task(self, name, local_path, remote_path, remote_name, strategy="bisync"):
        task = {
            "id": len(self._tasks) + 1, # Simple ID generation
            "name": name,
            "local_path": local_path,
            "remote_path": remote_path,
            "remote_name": remote_name,
            "strategy": strategy,
            "last_sync": "Never",
            "status": "Idle"
        }
        self._tasks.append(task)
        self.save_tasks()
        return task

    def remove_task(self, task_id):
        self._tasks = [t for t in self._tasks if t.get("id") != task_id]
        self.save_tasks()
    
    def update_task_status(self, task_id, status, last_sync=None):
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = status
                if last_sync:
                    t["last_sync"] = last_sync
        self.save_tasks()

    def update_task(self, task_id, name, local_path, remote_path, remote_name, strategy="bisync"):
        for t in self._tasks:
            if t["id"] == task_id:
                t["name"] = name
                t["local_path"] = local_path
                t["remote_path"] = remote_path
                t["remote_name"] = remote_name
                t["strategy"] = strategy
                # Reset status if changed
                t["status"] = "Idle" 
                break
        self.save_tasks()

    def get_strategy_for_remote(self, remote_name):
        """Returns the sync strategy (bisync/sync/copy) for a given remote, or None."""
        for t in self._tasks:
            if t.get("remote_name") == remote_name:
                return t.get("strategy", "bisync") # Default to bisync for old tasks
        return None
