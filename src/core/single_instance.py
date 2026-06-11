import socket
import logging

class SingleInstanceCheck:
    """
    Usa un socket local para asegurar que solo una instancia de la aplicación esté corriendo.
    Si otra instancia intenta abrirse, el socket fallará al bindearse.
    """
    def __init__(self, app_id="rclone_manager_gna"):
        self.logger = logging.getLogger(__name__)
        # Ruta del socket en /tmp (o similar en Linux)
        self.lock_path = f"\0{app_id}_lock" # El \0 lo hace un abstract socket en Linux (sin archivo físico)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def is_running(self):
        try:
            # Intentamos bindear el socket. Si falla, es porque ya hay una instancia.
            self.socket.bind(self.lock_path)
            return False
        except socket.error:
            self.logger.warning("Otra instancia de Rclone Manager ya está en ejecución.")
            return True

    def cleanup(self):
        try:
            self.socket.close()
        except Exception:
            pass
