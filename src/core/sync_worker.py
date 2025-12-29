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

    def __init__(self, command):
        super().__init__()
        self.command = command
        self.logger = logging.getLogger(__name__)

    def run(self):
        self.logger.info(f"Worker starting cmd: {self.command}")
        try:
            # Usar Popen para leer streaming
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
            
        except Exception as e:
            self.logger.exception("Worker exception")
            self.finished_error.emit(str(e))
