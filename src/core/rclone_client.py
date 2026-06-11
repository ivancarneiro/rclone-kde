import aiohttp
import asyncio
import logging

class RcloneClient:
    """
    Cliente asíncrono para la API RC de Rclone.
    Maneja la comunicación HTTP con el daemon 'rclone rcd'.
    """
    def __init__(self, url="http://localhost:5572", user="", password=""):
        self.url = url.rstrip('/')
        self.auth = aiohttp.BasicAuth(user, password) if user and password else None
        self.logger = logging.getLogger(__name__)

    async def _post(self, endpoint, data=None, timeout=30):
        url = f"{self.url}/{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, auth=self.auth, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    else:
                        text = await resp.text()
                        self.logger.error(f"Rclone API Error ({resp.status}): {text}")
                        return {"error": text, "status": resp.status}
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError):
            # Silently log connection failures without traceback, as they are expected during startup
            self.logger.debug(f"Daemon not reachable yet at {url}")
            return {"error": "connection_failed"}
        except Exception as e:
            self.logger.exception(f"Unexpected connection error to {url}")
            return {"error": str(e)}

    async def version(self):
        """Obtiene la versión de Rclone."""
        return await self._post("core/version")

    async def list_remotes(self):
        """Lista los remotos configurados."""
        return await self._post("config/listremotes")

    async def noop(self):
        """Verifica conectividad (No Operation)."""
        return await self._post("rc/noop")

    async def mount(self, fs, mount_point, vfs_cache_mode="full"):
        """
        Inicia un montaje.
        NOTA: 'mount/mount' puede ser bloqueante o fallar si no se lanza con _async=true.
        """
        data = {
            "fs": fs,
            "mountPoint": mount_point,
            "vfsOpt": {"cacheMode": vfs_cache_mode},
            "_async": "true" 
        }
        return await self._post("mount/mount", data)

    async def operations_list(self, fs, remote, opt=None):
        """Lista archivos en un remoto (lsjson)."""
        data = {
            "fs": fs,
            "remote": remote,
            "opt": opt or {}
        }
        return await self._post("operations/list", data)

    async def job_status(self, job_id):
        """Consulta el estado de un trabajo asíncrono."""
        return await self._post("job/status", {"jobid": job_id})

    async def core_stats(self):
        """Devuelve estadísticas globales de transferencia (core/stats)."""
        return await self._post("core/stats")

    async def rc_call(self, method, params=None):
        """Wrapper genérico para llamadas RC."""
        return await self._post(method, params)
