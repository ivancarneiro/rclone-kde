import subprocess
import time
import logging
import shutil

class RcloneProcessManager:
    """
    Gestiona el ciclo de vida del proceso 'rclone rcd'.
    Se encarga de iniciarlo al arrancar la app y detenerlo al cerrar.
    """
    def __init__(self, rc_addr="localhost:5572", rc_user="admin", rc_pass="admin", rc_conf=None):
        self.rc_addr = rc_addr
        self.rc_user = rc_user
        self.rc_pass = rc_pass
        self.rc_conf = rc_conf
        self.process = None
        self.logger = logging.getLogger(__name__)

    def is_installed(self):
        return shutil.which("rclone") is not None

    def start_daemon(self):
        """Inicia el proceso rclone rcd en segundo plano."""
        if not self.is_installed():
            self.logger.error("Rclone binary not found in PATH")
            return False

        # TODO: Verificar si el puerto ya está en uso
        
        cmd = [
            "rclone", "rcd",
            f"--rc-addr={self.rc_addr}",
            f"--rc-user={self.rc_user}",
            f"--rc-pass={self.rc_pass}",
            f"--config={self.rc_conf}", # Usar config aislado
            "--rc-no-auth" 
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.logger.info(f"Rclone daemon started (PID: {self.process.pid})")
            time.sleep(1) # Dar tiempo para arrancar
            return True
        except Exception as e:
            self.logger.exception("Failed to start rclone daemon")
            return False

    def stop_daemon(self):
        """Detiene el proceso si fue iniciado por esta instancia."""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.logger.info("Rclone daemon stopped")
            self.process = None
