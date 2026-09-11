from PyQt6.QtCore import QThread, pyqtSignal
import subprocess
import logging

class SyncWorker(QThread):
    """
    Ejecuta el comando de sincronización (rclone bisync) en un hilo separado
    para no congelar la UI.
    """
    finished_success = pyqtSignal()
    finished_error = pyqtSignal(str) # mensaje de error
    output_log = pyqtSignal(str)     # para logs en tiempo real (stdout/stderr)

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self.logger = logging.getLogger(__name__)

    def run(self):
        self.logger.info(f"Worker starting cmd: {self.command}")
        try:
            # 1. Esperar a que la ruta local exista (útil para monturas recién lanzadas)
            # Extraer ruta local del comando (asumimos rclone bisync/sync/copy local remote)
            # Para simplificar, buscamos si alguna de las rutas en el comando existe
            import os
            import time
            
            path_to_wait = None
            for arg in self.command:
                if "/" in arg and not arg.startswith("-"):
                    path_to_wait = arg
                    break
            
            if path_to_wait and not path_to_wait.startswith("http"):
                self.logger.info(f"Worker waiting for path: {path_to_wait}")
                found = False
                for _ in range(15):
                    if os.path.exists(path_to_wait):
                        found = True
                        break
                    time.sleep(1)
                if not found:
                    self.finished_error.emit(f"Local path {path_to_wait} did not appear after 15s")
                    return

            # 2. Ejecutar comando rclone
            process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Merge stderr into stdout
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Leer línea a línea
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    clean_line = line.strip()
                    if clean_line:
                        self.output_log.emit(clean_line)
                        # self.logger.debug(f"LOG: {clean_line}") 
            
            return_code = process.poll()
            
            if return_code == 0:
                self.finished_success.emit()
            else:
                err_msg = f"Process finished with exit code {return_code}"
                self.logger.error(f"Worker failed: {err_msg}")
                self.finished_error.emit(err_msg)
            
        except Exception as e:
            self.logger.exception("Worker exception")
            self.finished_error.emit(str(e))
