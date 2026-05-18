import subprocess
import shutil

class NotificationManager:
    @staticmethod
    def send(title, message, urgency="normal"):
        """
        Envía una notificación al sistema usando `notify-send`.
        No requiere librerías Python extra, solo el binario del sistema (común en KDE/Gnome).
        """
        if shutil.which("notify-send"):
            try:
                subprocess.Popen([
                    "notify-send", 
                    "--app-name=RcloneKDE", 
                    f"--urgency={urgency}",
                    "--expire-time=5000", # 5 segundos
                    title, 
                    message
                ])
            except Exception:
                pass # Fail silently si no se puede notificar
