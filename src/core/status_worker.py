import asyncio
import logging
import aiohttp
from PyQt6.QtCore import QThread, pyqtSignal

class StatusWorker(QThread):
    """
    Hilo encargado de consultar la lista de remotos y su estado (mount/quota/email)
    de forma asincrónica pero contenida en su propio hilo.
    """
    data_received = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, rclone_client, mount_manager, sync_manager):
        super().__init__()
        self.client = rclone_client
        self.mount_manager = mount_manager
        self.sync_manager = sync_manager
        self.logger = logging.getLogger(__name__)

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            data = loop.run_until_complete(self._fetch_all_data())
            self.data_received.emit(data)
            
            loop.close()
        except Exception as e:
            self.logger.exception("StatusWorker failed")
            self.error_occurred.emit(str(e))

    async def _fetch_all_data(self):
        # 1. List Remotes
        remotes_resp = await self.client.list_remotes()
        if not remotes_resp or "remotes" not in remotes_resp:
            return []
            
        remote_names = remotes_resp["remotes"]
        
        # 2. Get Active Mounts
        mounts_resp = await self.client._post("mount/listmounts")
        active_mounts = [m['Fs'] for m in mounts_resp.get('mountPoints', [])]
        
        # 3. Get Config Dump (for emails/types)
        config_dump = await self.client._post("config/dump", {"long": "true"})
        
        enriched_remotes = []
        for name in remote_names:
            fs_string = f"{name}:"
            mount_point = self.mount_manager.get_mount_point(name)
            
            # Mount Status
            is_mounted_api = any(fs_string in m for m in active_mounts) or any(name in m for m in active_mounts)
            is_mounted_sys = self.mount_manager.is_mounted_system(mount_point)
            is_mounted = is_mounted_api or is_mounted_sys
            
            detail_text = "Google Drive"
            status_color = "#4CAF50" if is_mounted else "#808080"
            quota_text = ""
            storage_percent = 0
            
            # Enrich with Config Data
            if name in config_dump:
                remote_type = config_dump[name].get('type', 'drive')
                detail_text = f"{remote_type} ({'Active' if is_mounted else 'Idle'})"
                
                # Try fetch Email
                if remote_type == "drive":
                    email = await self._try_fetch_email(config_dump[name].get('token', '{}'))
                    if email:
                        detail_text = email

            # Quota
            try:
                about_resp = await self.client._post("operations/about", {"fs": fs_string})
                if about_resp and "total" in about_resp:
                    total = about_resp.get("total", 0)
                    used = about_resp.get("used", 0)
                    quota_text = self._sizeof_fmt(used) + " / " + self._sizeof_fmt(total)
                    storage_percent = (used / total) if total > 0 else 0
            except:
                pass

            enriched_remotes.append({
                "name": name,
                "display": f"{name} ({config_dump.get(name, {}).get('type', 'Remote')})",
                "is_mounted": is_mounted,
                "status_color": status_color,
                "detail": detail_text,
                "quota": quota_text,
                "storage_percent": storage_percent,
                "sync_strategy": self.sync_manager.get_strategy_for_remote(name)
            })
            
        return enriched_remotes

    async def _try_fetch_email(self, token_str):
        try:
            import json
            token_data = json.loads(token_str)
            access_token = token_data.get('access_token')
            if not access_token: return None
            
            headers = {"Authorization": f"Bearer {access_token}"}
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.googleapis.com/drive/v3/about?fields=user", headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("user", {}).get("emailAddress")
        except:
            pass
        return None

    def _sizeof_fmt(self, num, suffix="B"):
        for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Xi{suffix}"
