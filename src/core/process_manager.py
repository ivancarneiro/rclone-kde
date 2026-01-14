import subprocess
import time
import logging
import shutil
import os

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

    def _cleanup_port_hogs(self):
        """Mata procesos rclone antiguos que ocupen el puerto configurado."""
        try:
            # Extraer puerto (asumiendo localhost:PORT)
            port = self.rc_addr.split(":")[-1] 
            # pkill -f "rc-addr=.*:PORT" es arriesgado si no es exacto
            # Mejor usar fuser o lsof si existen, o pkill con patrón preciso.
            # Usaremos pkill con el patrón completo de addr para ser precisos.
            pattern = f"rc-addr={self.rc_addr}"
            self.logger.info(f"Cleaning up old processes on {self.rc_addr}...")
            subprocess.run(["pkill", "-f", pattern], check=False)
            time.sleep(0.5)
        except Exception as e:
            self.logger.warning(f"Cleanup failed: {e}")

    def start_daemon(self):
        """Inicia el proceso rclone rcd en segundo plano."""
        if not self.is_installed():
            self.logger.error("Rclone binary not found in PATH")
            return False

        # Kill existing instances on this port
        self._cleanup_port_hogs()

        # TODO: Verificar si el puerto ya está en uso
        
        # Prepare environment with password
        # Prepare environment with password
        env = os.environ.copy()
        env["RCLONE_RC_PASS"] = self.rc_pass

        cmd = [
            "rclone", "rcd",
            f"--rc-addr={self.rc_addr}",
            "--rc-user=rclone",
            # "--rc-pass" removed for security (passed via env)
            "--rc-no-auth" if not self.rc_pass else "", # Fallback logic if pass is empty
            "--config", self.rc_conf
        ]
        
        # Remove empty strings from cmd
        cmd = [c for c in cmd if c]

        self.logger.info(f"Starting Rclone Daemon on {self.rc_addr}")
        # Log command without environment to avoid leaking? standard log doesn't show env usually.
        
        try:
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                env=env # Pass secure env
            )
            self.logger.info(f"Rclone daemon started (PID: {self.process.pid})")
            time.sleep(3) # Dar tiempo extra para inicializar API y Config
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
