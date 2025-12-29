from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal
import subprocess
import json
import logging

class WizardViewModel(QObject):
    """
    ViewModel para el Wizard de creación de nuevo remoto (Google Drive).
    """
    # Signals
    authStateChanged = pyqtSignal(str) # "idle", "loading", "success", "error"
    statusMessageChanged = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, client, settings_manager, autostart_manager):
        super().__init__()
        self._client = client
        self._settings_manager = settings_manager
        self._autostart_manager = autostart_manager
        self._status_message = ""
        self.logger = logging.getLogger(__name__)
        self._statusMessage = ""

    @pyqtProperty(str, notify=statusMessageChanged)
    def statusMessage(self):
        return self._status_message

    def setStatus(self, msg):
        self._status_message = msg
        self.statusMessageChanged.emit(msg)

    @pyqtSlot(str, str, str, bool)
    def createDriveRemote(self, name, client_id, client_secret, auto_mount):
        """
        Paso 1: Configurar remote tipo 'drive'
        Paso 2: Obtener url de auth
        """
        self.logger.info(f"Creating Drive remote: {name}, AutoMount: {auto_mount}")
        
        # Save Auto-Mount pref
        if auto_mount:
            self._settings_manager.add_auto_mount(name)
            # Ensure system autostart is enabled if we have at least one auto-mount
            if not self._autostart_manager.is_enabled():
                self._autostart_manager.enable_autostart()
                
        # ... logic continues ...RC.
        """
        1. Ejecuta `rclone authorize` para obtener token.
        2. Crea el config via API RC.
        """
        if not name:
            self.authStateChanged.emit("error")
            self.setStatus("Name is required")
            return

        self.authStateChanged.emit("loading")
        self.setStatus("Launching browser for authentication...")
        self.logger.info(f"Starting auth flow for {name}")

        # Ejecutar rclone authorize en un hilo separado o procesar eventos para no congelar UI
        # Para simplificar en este paso MVP, lo haremos bloqueante (idealmente usar QThread o asyncio)
        # pero como rclone authorize abre navegador y espera, bloqueará la GUI si no tenemos cuidado.
        # Vamos a usar subprocess pero necesitamos no bloquear el MainLoop de Qt.
        # Por ahora, usaré una estructura simple, sabiendo que puede congelar brevemente hasta que se abra el browser.
        
        try:
            # Construir comando
            cmd = ["rclone", "authorize", "drive"]
            if client_id:
                cmd.append(client_id)
            if client_secret:
                cmd.append(client_secret)

            self.logger.info(f"Running: {' '.join(cmd)}")
            
            # NOTA: Esto bloqueará hasta que el usuario termine el auth en el navegador.
            # En producción esto debe ir en un Worker Thread.
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.error(f"Auth failed: {result.stderr}")
                self.authStateChanged.emit("error")
                self.setStatus("Authentication failed or cancelled.")
                return

            # El output es un JSON con el token (ver estructura rclone authorize)
            # Ejemplo: {"access_token":"...","token_type":"Bearer",...}
            # A veces rclone pone texto antes del JSON ("Paste the following..."), authorize suele dar JSON limpio si es headless?
            # rclone authorize abre un servidor local. El output stdout es el token JSON.

            token_json = result.stdout.strip()
            # Validar que sea JSON
            try:
                # Intentar parsear para asegurar validez
                json.loads(token_json) 
            except json.JSONDecodeError:
                 # A veces rclone authorize devuelve info extra. Buscar la primera { y ultima }
                start = token_json.find('{')
                end = token_json.rfind('}') + 1
                if start != -1 and end != -1:
                    token_json = token_json[start:end]
                else:
                    raise Exception("Invalid token output from rclone")

            self.setStatus("Authentication successful. Saving configuration...")
            
            # Crear config via API RC
            # rclone rc config/create name=remote type=drive token=...
            # IMPORTANTE: token debe pasarse como string JSON
            
            # Construir parámetros
            params = {
                "name": name,
                "type": "drive",
                "token": token_json
            }
            if client_id:
                params["client_id"] = client_id
            if client_secret:
                params["client_secret"] = client_secret

            # Llamar API (necesitamos hacerlo sincrono o via wait loop, aquí usaremos ensure_future si estuviéramos en loop asyncio)
            # Como estamos en Qt Main Thread, usaremos 'requests' o una llamada bloqueante al aiohttp wrapper si lo adaptamos.
            # ERROR: RcloneClient es async. No podemos llamarlo directo con 'await' aquí sin un loop.
            # SOLUCIÓN MVP: Usamos requests directo aquí para simplificar, o lanzamos tarea al event loop si PyQt tuviera integración.
            # Alternativa: Usar subprocess para llamar a `rclone rc` CLI para crear el config. Es más robusto que mezclar loops.
            
            # Construir dict de parámetros específicos del backend
            backend_params = {
                "token": token_json
            }
            if client_id:
                backend_params["client_id"] = client_id
            if client_secret:
                backend_params["client_secret"] = client_secret
            
            # Serializar a JSON para pasar como argumento 'parameters'
            parameters_json = json.dumps(backend_params)

            create_cmd = [
                "rclone", "rc", "config/create",
                f"name={name}", 
                f"type=drive", 
                f"parameters={parameters_json}",
                "--rc-addr=localhost:5572",
                "--rc-user=rclone",
                "--rc-pass=password"
            ]
            # client_id y secret ya van en parameters_json, no los añadimos al array cmd
            
            subprocess.run(create_cmd, check=True)
            
            self.authStateChanged.emit("success")
            self.setStatus("Drive created successfully!")
            self.finished.emit()

        except Exception as e:
            self.logger.exception("Error creating remote")
            self.authStateChanged.emit("error")
            self.setStatus(f"Error: {str(e)}")
