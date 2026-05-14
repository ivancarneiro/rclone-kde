import asyncio
import logging
from PyQt6.QtCore import QThread, pyqtSignal

class MountWorker(QThread):
    """
    Hilo dedicado para realizar operaciones de montaje/desmontaje
    sin bloquear el hilo principal de Qt.
    """
    finished_success = pyqtSignal(dict)
    finished_error = pyqtSignal(str)

    def __init__(self, mount_manager, remote_name, read_only=False, network_mode=False, is_unmount=False):
        super().__init__()
        self.mount_manager = mount_manager
        self.remote_name = remote_name
        self.read_only = read_only
        self.network_mode = network_mode
        self.is_unmount = is_unmount
        self.logger = logging.getLogger(__name__)

    def run(self):
        try:
            # Creamos un loop de asyncio dedicado para este hilo
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if self.is_unmount:
                self.logger.info(f"Worker: Unmounting {self.remote_name}")
                success = loop.run_until_complete(self.mount_manager.unmount_remote(self.remote_name))
                if success:
                    self.finished_success.emit({"remote_name": self.remote_name, "action": "unmount"})
                else:
                    self.finished_error.emit("Unmount failed or was busy.")
            else:
                self.logger.info(f"Worker: Mounting {self.remote_name}")
                result = loop.run_until_complete(
                    self.mount_manager.mount_remote(self.remote_name, self.read_only, self.network_mode)
                )
                if result.get("success"):
                    self.finished_success.emit(result)
                else:
                    self.finished_error.emit(result.get("error", "Unknown error"))
            
            loop.close()
        except Exception as e:
            self.logger.exception("MountWorker exception")
            self.finished_error.emit(str(e))
