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
        self.log_file = None
        self.logger = logging.getLogger(__name__)

    def is_installed(self):
        return shutil.which("rclone") is not None

    def _cleanup_port_hogs(self):
        """Mata procesos rclone antiguos que ocupen el puerto configurado."""
        try:
            port = self.rc_addr.split(":")[-1]
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

        self._cleanup_port_hogs()

        env = os.environ.copy()
        env["RCLONE_RC_PASS"] = self.rc_pass

        cmd = [
            "rclone", "rcd",
            "--rc-addr", self.rc_addr,
            "--rc-user", self.rc_user,
            "--config", self.rc_conf,
            "--drive-acknowledge-abuse",
            "-vv",
        ]

        if not self.rc_pass:
            cmd.append("--rc-no-auth")

        self.logger.info(f"Starting Rclone Daemon on {self.rc_addr}")

        try:
            log_path = os.path.expanduser("~/.cache/rclone-kde.log")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            self.log_file = open(log_path, "a")
            self.process = subprocess.Popen(
                cmd,
                stdout=self.log_file,
                stderr=subprocess.STDOUT,
                env=env
            )
            self.logger.info(f"Rclone daemon started (PID: {self.process.pid}). Logs at {log_path}")
            time.sleep(3)
            return True
        except Exception as e:
            self.logger.exception("Failed to start rclone daemon")
            return False

    def stop_daemon(self):
        """Detiene el proceso si fue iniciado por esta instancia."""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.logger.info("Rclone daemon stopped")
            self.process = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None
