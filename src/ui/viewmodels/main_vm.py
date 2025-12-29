from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtWidgets import QApplication
import logging
import aiohttp
import asyncio
import json

class MainViewModel(QObject):
    """
    ViewModel principal.
    Expone listas de remotos y acciones principales a QML.
    """
    remotesChanged = pyqtSignal()

    def __init__(self, client, settings_manager):
        super().__init__()
        self._client = client
        self._settings_manager = settings_manager
        self._remotes = []
        self.logger = logging.getLogger(__name__)

        # Inicializar vacío al principio
        self._remotes = []
        self._window = None
        self._is_quitting = False
        
    def set_window(self, window):
        self._window = window

    @pyqtProperty(bool)
    def is_quitting(self):
        return self._is_quitting

    @pyqtSlot()
    def hide_window(self):
        if self._window:
            self._window.hide()
    
    @pyqtSlot()
    def show_window(self):
        if self._window:
            self._window.show()
            self._window.raise_()
            self._window.requestActivate()

    def quit_app(self):
        self._is_quitting = True
        if self._window:
            self._window.close()
        QApplication.quit()
        
        # Trigger inicial
        # Nota: Como client es async, idealmente deberíamos tener un mecanismo para llamar async desde __init__
        # Por simplicidad MVP, usamos el slot refresh_remotes que llamaremos desde QML al cargar o con un Timer

    @pyqtProperty(list, notify=remotesChanged)
    def remotes_model(self):
        return self._remotes

    @pyqtSlot()
    def add_new_drive(self):
        self.logger.info("Solicitud de añadir nuevo drive")
        # El cambio a QStackView maneja la UI, aquí solo lógica si fuera necesaria
        pass

    @pyqtSlot()
    def refresh_remotes(self):
        import asyncio
        from PyQt6.QtWidgets import QApplication
        
        try:
            # Single Loop execution for the whole refresh sequence
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            loop.run_until_complete(self._do_full_refresh())
            loop.close()
                
        except Exception as e:
            self.logger.exception("Error refreshing remotes")

    async def _do_full_refresh(self):
        """Orchestrates the full refresh: List -> Filter -> Enrich"""
        try:
            response = await self._client.list_remotes()
            if response and "remotes" in response:
                new_remotes = []
                for name in response["remotes"]:
                    new_remotes.append({
                        "name": name, 
                        "display": f"{name} (Google Drive)" 
                    })
                self._remotes = new_remotes
                self.logger.info(f"Remotes listed: {len(self._remotes)}")
                
                # Now enrich
                await self._enrich_remotes_data()
                
                # Auto-Mount on First Load
                if not hasattr(self, '_initial_load_done') or not self._initial_load_done:
                    await self._process_auto_mounts()
                    self._initial_load_done = True
                    
            else:
                self.logger.warning("Empty response from list_remotes")
                self._remotes = []
                self.remotesChanged.emit() # Ensure UI clears if empty
                
        except Exception as e:
            self.logger.exception("Refres sequence failed")

    async def _process_auto_mounts(self):
        """Check settings and mount remotes that should be mounted"""
        auto_mounts = self._settings_manager.get_auto_mounts()
        if not auto_mounts:
            return

        self.logger.info(f"Processing Auto-Mounts: {auto_mounts}")
        
        # Necesitamos saber cuáles ya están montados
        # Podemos reusar la info que acabamos de enriquecer en self._remotes
        for remote in self._remotes:
            name = remote['name']
            clean_name = name.rstrip(':')
            is_enabled = (name in auto_mounts) or (clean_name in auto_mounts)
            
            if is_enabled and not remote.get('is_mounted', False):
                self.logger.info(f"Auto-mounting {name}...")
                await self._mount_remote_async(name)
                # Since we are already in a loop (refresh_remotes -> _do_full_refresh), 
                # we should use the SAME loop/client.
                # mount_remote creates a NEW loop. That's bad here.
                # I should extract the mount logic to an async method `_mount_remote_async` 
                # and call it here.
                await self._mount_remote_async(name)
    
    async def _mount_remote_async(self, remote_name):
        try:
            from core.config import Config
            mount_point = f"{Config.mount_dir}/{remote_name}"
            import os
            if not os.path.exists(mount_point):
                os.makedirs(mount_point)
            
            fs_string = f"{remote_name}:"
            # Using _client directly (which is async)
            await self._client.mount(fs_string, mount_point)
            
            # Update local state manually to reflect success without full refresh loop
            for r in self._remotes:
                if r['name'] == remote_name:
                    r['is_mounted'] = True
                    r['status_color'] = "#4CAF50"
                    r['detail'] = "Mounted"
            self.remotesChanged.emit()
            
        except Exception as e:
            self.logger.error(f"Auto-mount failed for {remote_name}: {e}")

    @pyqtSlot(str)
    def delete_remote(self, remote_name):
        """Elimina un remoto (y lo desmonta si es necesario)."""
        self.logger.info(f"Request to delete remote: {remote_name}")
        
        # 1. Unmount if currently mounted
        # We need to find the remote in our list to check status or just try unmount forcefully?
        # Better to check if we think it is mounted.
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Check local status
            is_mounted = False
            for r in self._remotes:
                if r['name'] == remote_name and r.get('is_mounted'):
                    is_mounted = True
                    break
            
            if is_mounted:
                self.logger.info(f"Unmounting {remote_name} before deletion...")
                # We can call internal async unmount logic or just run command
                # Since we don't have a dedicated unmount method exposed yet besides subprocess or mount logic...
                # Let's use fusermount -u via subprocess for safety or rclone rc mount/unmount (if supported).
                # Rclone RC 'mount/unmount' exists? No, only 'mount/unmountall' or valid mount control.
                # Standard way is `fusermount -u /path/to/mount`.
                # Construct path
                from core.config import Config
                import subprocess
                mount_point = f"{Config.mount_dir}/{remote_name}"
                subprocess.run(["fusermount", "-u", mount_point], check=False)
            
            # 2. Remove from Auto-Mounts
            if self._settings_manager.is_auto_mount_enabled(remote_name):
                self._settings_manager.remove_auto_mount(remote_name)
            
            # 3. Delete Config via RC
            # We need to run async task
            loop.run_until_complete(self._client.rc_call("config/delete", {"name": remote_name}))
            
            self.logger.info(f"Remote {remote_name} deleted.")
            
            # 4. Refresh List
            self.refresh_remotes()

        except Exception as e:
            self.logger.error(f"Error deleting remote {remote_name}: {e}")
            # Could emit error signal if needed

    async def _enrich_remotes_data(self):
        """Bloque enriquecedor: Obtiene estado de montura y metadatos (email)"""
        try:
            self.logger.info("Enriching remotes data...")
            # 1. Get Active Mounts
            mounts_resp = await self._client._post("mount/listmounts")
            active_mounts = [m['Fs'] for m in mounts_resp.get('mountPoints', [])]
            
            # 2. Get Config Dump to parse tokens (Email)
            config_dump = await self._client._post("config/dump", {"long": "true"})
            
            updated_remotes = []
            for remote in self._remotes:
                name = remote['name']
                fs_string = f"{name}:"
                
                # Check Mount Status
                is_mounted = any(fs_string in m for m in active_mounts) or any(name in m for m in active_mounts)
                
                # Fallback Email/Detail
                detail_text = "Google Drive"
                status_color = "#808080"
                
                if is_mounted:
                    status_color = "#4CAF50"
                    detail_text = "Mounted"

                # Intentar obtener email del config dump si existe
                if name in config_dump:
                    remote_type = config_dump[name].get('type', 'drive')
                    detail_text = f"{remote_type} ({'Active' if is_mounted else 'Idle'})"
                    
                    # Try to fetch real email from Google API using the token
                    if remote_type == "drive":
                        try:
                            token_str = config_dump[name].get('token', '{}')
                            import json
                            token_data = json.loads(token_str)
                            access_token = token_data.get('access_token')
                            
                            if access_token:
                                self.logger.info(f"Fetching email for {name} via Drive API...")
                                # Call Google Drive About API instead of UserInfo (avoid 401 scope issues)
                                headers = {"Authorization": f"Bearer {access_token}"}
                                async with aiohttp.ClientSession() as session:
                                    # fields=user gets user display name and email
                                    async with session.get("https://www.googleapis.com/drive/v3/about?fields=user", headers=headers, timeout=5) as resp:
                                        if resp.status == 200:
                                            about_data = await resp.json()
                                            user_data = about_data.get("user", {})
                                            email = user_data.get("emailAddress")
                                            displayName = user_data.get("displayName")
                                            
                                            if email:
                                                self.logger.info(f"Email found: {email}")
                                                detail_text = email 
                                        else:
                                            self.logger.warning(f"Drive About API failed: {resp.status} {await resp.text()}")
                        except Exception as e:
                            self.logger.warning(f"Could not fetch email for {name}: {e}")

                # Obtener Quota (About)
                quota_text = ""
                try:
                    # operations/about devuelve {total, used, free, trashed} en bytes
                    about_resp = await self._client._post("operations/about", {"fs": fs_string})
                    if about_resp and "total" in about_resp:
                        total = about_resp.get("total", 0)
                        used = about_resp.get("used", 0)
                        
                        # Helper formato bytes
                        def sizeof_fmt(num, suffix="B"):
                            for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi"]:
                                if abs(num) < 1024.0:
                                    return f"{num:3.1f}{unit}{suffix}"
                                num /= 1024.0
                            return f"{num:.1f}Xi{suffix}"

                        quota_text = f"{sizeof_fmt(used)} / {sizeof_fmt(total)}"
                        remote['storage_percent'] = (used / total) if total > 0 else 0
                except:
                    pass # Algunos remotos no soportan about o fallan si no están configurados

                # Update dictionary
                remote['is_mounted'] = is_mounted
                remote['status_color'] = status_color
                remote['detail'] = detail_text
                remote['quota'] = quota_text
                
                updated_remotes.append(remote)
            
            self._remotes = updated_remotes
            self.remotesChanged.emit()
            
        except Exception as e:
            self.logger.exception(f"Failed to enrich remote data")

    @pyqtSlot(str)
    def mount_remote(self, remote_name):
        import os
        import subprocess
        from core.config import Config
        from core.notifications import NotificationManager

        self.logger.info(f"Mounting {remote_name}...")
        
        # 1. Definir punto de montaje
        mount_point = os.path.join(Config.MOUNT_BASE_DIR, remote_name)
        
        try:
            # Crear directorio si no existe
            os.makedirs(mount_point, exist_ok=True)
            
            # 2. Llamar a Rclone Mount (Async via loop helper)
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            fs_string = f"{remote_name}:"
            # Verificar si ya está montado antes de intentar
            # (Opcional, pero rclone fallará si ya está montado)
            
            response = loop.run_until_complete(self._client.mount(fs_string, mount_point))
            
            # Refrescar lista para actualizar UI (punto verde)
            # (Usamos el mismo loop antes de cerrar)
            loop.run_until_complete(self._enrich_remotes_data())
            loop.close()
            
            self.logger.info(f"Mount response: {response}")
            
            # 3. Abrir en Dolphin (Explorer)
            if response and "err" not in response:
                 self.logger.info(f"Opening Dolphin at {mount_point}")
                 subprocess.Popen(["xdg-open", mount_point])
                 NotificationManager.send("Drive Mounted", f"{remote_name} is now available.")
            else:
                 self.logger.error("Mount failed")
                 NotificationManager.send("Mount Failed", f"Could not mount {remote_name}", urgency="critical")

        except Exception as e:
            self.logger.exception(f"Error mounting {remote_name}")
            NotificationManager.send("Mount Error", str(e), urgency="critical")
