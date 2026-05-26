import os
import subprocess
import logging
import asyncio
from core.config import Config
from core.notifications import NotificationManager

class MountManager:
    """
    Encapsulates all logic related to mounting, unmounting, and mount status monitoring.
    Decouples low-level Rclone/OS operations from the ViewModel.
    """
    def __init__(self, client):
        self._client = client
        self.logger = logging.getLogger(__name__)

    def get_mount_point(self, remote_name):
        return os.path.join(Config.mount_dir, remote_name)

    def is_mounted_system(self, mount_point):
        """Checks if the path is a mountpoint from OS perspective"""
        return os.path.exists(mount_point) and os.path.ismount(mount_point)

    async def get_active_mounts(self):
        """
        Fetches active mount points from Rclone RC.
        Returns a list of fs strings (e.g. ['gdrive:', 'remote:'])
        """
        try:
            mounts_resp = await self._client.rc_call("mount/listmounts")
            # mountPoints: [{"Fs": "remote:", "MountPoint": "..."}]
            return [m['Fs'] for m in mounts_resp.get('mountPoints', [])]
        except Exception:
            self.logger.warning("Failed to fetch listmounts from RC")
            return []

    def cleanup_zombie(self, mount_point):
        """Attempts to remove a stale mount using fusermount -uz and cleans the directory."""
        try:
            # Forzar desmontaje aunque esté roto
            self.logger.info(f"Forcing unmount for potential zombie at {mount_point}...")
            subprocess.run(["fusermount", "-uz", mount_point], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Si después del desmontaje el directorio sigue existiendo y está vacío, lo borramos para asegurar limpieza
            if os.path.exists(mount_point):
                if not os.path.ismount(mount_point):
                    self.logger.info(f"Removing stale directory {mount_point}...")
                    import shutil
                    shutil.rmtree(mount_point, ignore_errors=True)
        except Exception as e:
            self.logger.warning(f"Cleanup zombie failed for {mount_point}: {e}")

    def cleanup_all(self):
        """Force unmounts everything in the Config.mount_dir"""
        mount_dir = Config.mount_dir
        if not os.path.exists(mount_dir):
            return
            
        self.logger.info(f"Performing global mount cleanup in {mount_dir}...")
        try:
            for item in os.listdir(mount_dir):
                path = os.path.join(mount_dir, item)
                if os.path.isdir(path):
                    self.logger.info(f"Cleaning up {path}...")
                    subprocess.run(["fusermount", "-uz", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.logger.error(f"Global cleanup failed: {e}")

    async def mount_remote(self, remote_name, read_only=False, network_mode=False):
        """
        Mounts a remote using direct subprocess with exclusions for heavy files.
        This bypasses RC API timeouts and ensures .img/.iso are never processed.
        """
        mount_point = self.get_mount_point(remote_name)
        
        # 1. System Check
        if self.is_mounted_system(mount_point):
            self.logger.info(f"Skipping mount for {remote_name}: Already mounted (System).")
            return {"success": True, "already_mounted": True, "mount_point": mount_point, "remote_name": remote_name}

        # 2. Cleanup Zombie
        self.cleanup_zombie(mount_point)
        os.makedirs(mount_point, exist_ok=True)

        # 3. Build Command
        cache_dir = os.path.join(Config.base_dir, "data", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        cmd = [
            "rclone", "mount", f"{remote_name}:", mount_point,
            "--vfs-cache-mode", "full",
            "--vfs-cache-max-age", "4h",
            "--vfs-cache-max-size", "5G",
            "--cache-dir", cache_dir,
            "--volname", remote_name,
            "--no-modtime",
            "--max-size", "1G",
            "--daemon",
            "--config", Config.RCLONE_CONF
        ]
        
        if read_only:
            cmd.append("--read-only")

        self.logger.info(f"Executing direct mount: {' '.join(cmd)}")
        try:
            # Usamos Popen para lanzar rclone al fondo
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Verificación por polling (máximo 30 segundos)
            for i in range(30):
                await asyncio.sleep(1.0) # Uso asyncio.sleep porque estamos en un método async
                if self.is_mounted_system(mount_point):
                    self.logger.info(f"Mount confirmed for {remote_name} after {i+1}s")
                    return {"success": True, "mount_point": mount_point, "remote_name": remote_name}
                
                # Si el proceso murió rápido, hubo un error de rclone
                if process.poll() is not None:
                    _, stderr = process.communicate()
                    self.logger.error(f"Rclone mount process exited early: {stderr}")
                    return {"success": False, "error": stderr}

            return {"success": False, "error": "El montaje se lanzó pero no aparece en el sistema (Timeout 30s)"}
        except Exception as e:
            self.logger.exception(f"Direct mount exception for {remote_name}")
            return {"success": False, "error": str(e)}

    async def unmount_remote(self, remote_name):
        """Unmounts a remote cleanly."""
        mount_point = self.get_mount_point(remote_name)
        self.logger.info(f"Unmounting {remote_name}...")
        
        try:
             # Force unmount (lazy)
             subprocess.run(["fusermount", "-uz", mount_point], check=True)
             return True
        except subprocess.CalledProcessError as e:
             self.logger.error(f"Fusermount failed: {e}")
             return False
        except Exception as e:
             self.logger.exception(f"Unmount error for {remote_name}")
             return False

    async def _wait_for_job(self, job_id, timeout_sec=30):
        """Polls job status until finished."""
        import time
        steps = int(timeout_sec / 1.0)
        for i in range(steps):
            job_status = await self._client.job_status(job_id)
            if job_status.get("finished"):
                if job_status.get("error"):
                    return False, job_status["error"]
                return True, None
            # Async sleep
            self.logger.debug(f"Waiting for mount job {job_id}... (step {i}/{steps})")
            await asyncio.sleep(1.0)
        return False, f"Timeout waiting for mount job after {timeout_sec}s"
