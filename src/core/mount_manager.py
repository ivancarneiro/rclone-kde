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

    async def mount_remote(self, remote_name, read_only=False, network_mode=False):
        """
        Mounts a remote with specified options. 
        Handles Cleanup -> Command -> Wait Job -> Verify.
        """
        mount_point = self.get_mount_point(remote_name)
        fs_string = f"{remote_name}:"

        # 1. System Check
        if self.is_mounted_system(mount_point):
            self.logger.info(f"Skipping mount for {remote_name}: Already mounted (System).")
            return {"success": True, "already_mounted": True, "mount_point": mount_point}

        # 2. Cleanup Zombie
        self.cleanup_zombie(mount_point)
        os.makedirs(mount_point, exist_ok=True)

        # 3. Prepare Options
        mount_opt = {
            "readOnly": read_only
        }
        
        vfs_opt = {
            "cacheMode": "off" if network_mode else "full"
        }
        
        if not network_mode:
            vfs_opt["cacheMaxAge"] = 86400000000000 # 24h in ns

        params = {
            "fs": fs_string,
            "mountPoint": mount_point,
            "mountOpt": mount_opt,
            "vfsOpt": vfs_opt,
            "_async": "true" 
        }

        # 4. Execute RC Call
        self.logger.info(f"Sending mount command for {remote_name}...")
        try:
            response = await self._client.rc_call("mount/mount", params)
            
            # 5. Wait for Job
            if response and "jobid" in response:
                job_id = response["jobid"]
                self.logger.info(f"Mount job {job_id} started. Waiting...")
                
                success, error = await self._wait_for_job(job_id)
                if success:
                    return {"success": True, "mount_point": mount_point}
                else:
                    return {"success": False, "error": error}
            
            # Fallback if no jobid (unexpected)
            if response and "err" not in response:
                 return {"success": True, "mount_point": mount_point}
            else:
                 return {"success": False, "error": response.get("error", "Unknown error")}

        except Exception as e:
            self.logger.exception(f"Mount exception for {remote_name}")
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

    async def _wait_for_job(self, job_id, timeout_sec=5):
        """Polls job status until finished."""
        import time
        steps = int(timeout_sec / 0.5)
        for _ in range(steps):
            job_status = await self._client.job_status(job_id)
            if job_status.get("finished"):
                if job_status.get("error"):
                    return False, job_status["error"]
                return True, None
            # Async sleep
            await asyncio.sleep(0.5)
        return False, "Timeout waiting for mount job"
