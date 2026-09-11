import subprocess
import time
import logging
from logging.handlers import TimedRotatingFileHandler
import shutil
import os
import threading

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
        self._rclone_logger = None
        self._log_thread = None

    def _setup_rclone_logger(self):
        """Configura un logger con rotación para la salida de rclone."""
        log_path = os.path.expanduser("~/.cache/rclone-kde.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        
        self._rclone_logger = logging.getLogger("rclone_daemon")
        self._rclone_logger.propagate = False  # Don't send to root logger
        
        # Rotación de 30 días
        handler = TimedRotatingFileHandler(
            log_path,
            when='D',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Limpiar handlers previos si existen
        self._rclone_logger.handlers = []
        self._rclone_logger.addHandler(handler)
        self._rclone_logger.setLevel(logging.DEBUG)

    def _log_reader_task(self):
        """Lee la salida del proceso rclone y la envía al logger."""
        try:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self._rclone_logger.debug(line.strip())
        except Exception as e:
            self.logger.error(f"Error reading rclone logs: {e}")

    def is_installed(self):
        return shutil.which("rclone") is not None

    def _cleanup_port_hogs(self):
        """Mata procesos rclone antiguos que ocupen el puerto configurado."""
        try:
            pattern = f"rc-addr.*{self.rc_addr}"
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
        self._setup_rclone_logger()

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
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Iniciar hilo para capturar logs
            self._log_thread = threading.Thread(target=self._log_reader_task, daemon=True)
            self._log_thread.start()
            
            self.logger.info(f"Rclone daemon started (PID: {self.process.pid}). Output piped to rotating logger.")
            time.sleep(2)
            return True
        except Exception:
            self.logger.exception("Failed to start rclone daemon")
            return False

    def stop_daemon(self):
        """Detiene el proceso si fue iniciado por esta instancia."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.logger.info("Rclone daemon stopped")
            self.process = None
