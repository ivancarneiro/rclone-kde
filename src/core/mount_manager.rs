use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command as StdCommand, Stdio};
use std::time::Duration;

use anyhow::{Context, Result};
use tokio::io::AsyncReadExt;
use tokio::process::{Child, Command};
use tokio::time::{sleep, timeout};
use tracing::{error, info, warn};

use super::config::{augmented_path_env, resolve_binary, resolve_fusermount_binary};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct MountOptions {
    pub read_only: bool,
    pub network_mode: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MountResult {
    pub success: bool,
    pub already_mounted: bool,
    pub mount_point: PathBuf,
    pub remote_name: String,
    pub error: Option<String>,
}

/// Manages FUSE mounts (`rclone mount`), zombie detection, and `fusermount -uz` cleanup.
#[derive(Debug)]
pub struct MountManager {
    mount_root: PathBuf,
    vfs_cache_dir: PathBuf,
    rclone_conf: PathBuf,
    processes: HashMap<String, Child>,
}

impl MountManager {
    pub fn new(mount_root: PathBuf, vfs_cache_dir: PathBuf, rclone_conf: PathBuf) -> Self {
        Self {
            mount_root,
            vfs_cache_dir,
            rclone_conf,
            processes: HashMap::new(),
        }
    }

    pub fn set_mount_root(&mut self, mount_root: PathBuf) {
        self.mount_root = mount_root;
    }

    pub fn mount_root(&self) -> &Path {
        &self.mount_root
    }

    pub fn get_mount_point(&self, remote_name: &str) -> PathBuf {
        self.mount_root.join(remote_name)
    }

    /// Checks whether `mount_point` appears in `/proc/mounts` content (unescaping `\040` spaces).
    pub fn is_mounted_in_proc_mounts(mount_point: &Path, proc_mounts_content: &str) -> bool {
        let target = mount_point.to_string_lossy();
        for line in proc_mounts_content.lines() {
            let mut parts = line.split_whitespace();
            let _source = parts.next();
            if let Some(raw_target) = parts.next() {
                let unescaped = raw_target.replace("\\040", " ");
                if unescaped == target.as_ref() {
                    return true;
                }
            }
        }
        false
    }

    /// Checks if `mount_point` is actively mounted and readable (not a broken `ENOTCONN` zombie).
    pub fn is_mounted_system(mount_point: &Path) -> bool {
        let Ok(content) = fs::read_to_string("/proc/mounts") else {
            return false;
        };
        if !Self::is_mounted_in_proc_mounts(mount_point, &content) {
            return false;
        }
        fs::read_dir(mount_point).is_ok()
    }

    /// Builds the `rclone mount` CLI arguments.
    pub fn build_mount_args(
        &self,
        remote_name: &str,
        mount_point: &Path,
        opts: MountOptions,
    ) -> Vec<String> {
        let vfs_mode = if opts.network_mode { "minimal" } else { "full" };
        let mut args = vec![
            "mount".to_string(),
            format!("{remote_name}:"),
            mount_point.to_string_lossy().into_owned(),
            "--vfs-cache-mode".to_string(),
            vfs_mode.to_string(),
            "--vfs-cache-max-age".to_string(),
            "4h".to_string(),
            "--vfs-cache-max-size".to_string(),
            "5G".to_string(),
            "--cache-dir".to_string(),
            self.vfs_cache_dir.to_string_lossy().into_owned(),
            "--volname".to_string(),
            remote_name.to_string(),
            "--no-modtime".to_string(),
            "--max-size".to_string(),
            "1G".to_string(),
            "--drive-acknowledge-abuse".to_string(),
            "--allow-non-empty".to_string(),
            "--config".to_string(),
            self.rclone_conf.to_string_lossy().into_owned(),
        ];

        if opts.read_only {
            args.push("--read-only".to_string());
        }

        args
    }

    /// Forces a lazy unmount (`fusermount -uz`) and removes the directory only if empty.
    pub fn cleanup_zombie(&self, mount_point: &Path) {
        let fusermount = resolve_fusermount_binary();
        info!(
            "Cleaning up potential zombie mount at {}",
            mount_point.display()
        );

        let _ = StdCommand::new(fusermount)
            .args(["-uz"])
            .arg(mount_point)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();

        if mount_point.exists() && !Self::is_mounted_system(mount_point) {
            if Self::remove_empty_dirs_bottom_up(mount_point) {
                info!(
                    "Removed stale empty mount directory {}",
                    mount_point.display()
                );
            } else {
                warn!(
                    "Could not remove stale mount directory {} (contains files)",
                    mount_point.display()
                );
            }
        }
    }

    /// Recursively removes empty directories bottom-up without following symlinks or deleting files.
    fn remove_empty_dirs_bottom_up(dir: &Path) -> bool {
        let Ok(meta) = fs::symlink_metadata(dir) else {
            return false;
        };
        if meta.file_type().is_symlink() || !meta.is_dir() {
            return false;
        }

        let Ok(entries) = fs::read_dir(dir) else {
            return false;
        };

        let mut all_empty = true;
        for entry in entries.flatten() {
            let path = entry.path();
            match fs::symlink_metadata(&path) {
                Ok(child_meta) if !child_meta.file_type().is_symlink() && child_meta.is_dir() => {
                    if !Self::remove_empty_dirs_bottom_up(&path) {
                        all_empty = false;
                    }
                }
                _ => {
                    all_empty = false;
                }
            }
        }

        all_empty && fs::remove_dir(dir).is_ok()
    }

    /// Terminates all managed mount processes and sweeps the mount root with `fusermount -uz`.
    pub fn cleanup_all(&mut self) {
        info!("Performing global mount cleanup...");

        for (remote, mut child) in self.processes.drain() {
            info!("Terminating managed rclone mount for {remote}...");
            let _ = child.start_kill();
            let _ = child.try_wait();
        }

        if !self.mount_root.exists() {
            return;
        }

        match fs::read_dir(&self.mount_root) {
            Ok(entries) => {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_dir() {
                        self.cleanup_zombie(&path);
                    }
                }
            }
            Err(err) => {
                error!(
                    "Global mount cleanup failed reading {}: {err}",
                    self.mount_root.display()
                );
            }
        }
    }

    /// Launches a supervised `rclone mount` process and waits up to 30s for confirmation.
    pub async fn mount_remote(
        &mut self,
        remote_name: &str,
        opts: MountOptions,
    ) -> Result<MountResult> {
        let mount_point = self.get_mount_point(remote_name);

        if Self::is_mounted_system(&mount_point) {
            info!("Skipping mount for {remote_name}: already mounted.");
            return Ok(MountResult {
                success: true,
                already_mounted: true,
                mount_point,
                remote_name: remote_name.to_string(),
                error: None,
            });
        }

        self.cleanup_zombie(&mount_point);
        fs::create_dir_all(&mount_point)
            .with_context(|| format!("Failed to create mount point {}", mount_point.display()))?;
        fs::create_dir_all(&self.vfs_cache_dir).with_context(|| {
            format!(
                "Failed to create VFS cache dir {}",
                self.vfs_cache_dir.display()
            )
        })?;

        let rclone_bin = resolve_binary("rclone");
        let args = self.build_mount_args(remote_name, &mount_point, opts);
        info!("Executing managed mount for {remote_name}");

        let mut child = Command::new(rclone_bin)
            .args(&args)
            .env("PATH", augmented_path_env())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .with_context(|| format!("Failed to spawn rclone mount for {remote_name}"))?;

        let mut stderr_pipe = child.stderr.take();
        self.processes.insert(remote_name.to_string(), child);

        for step in 1..=30 {
            sleep(Duration::from_secs(1)).await;

            if Self::is_mounted_system(&mount_point) {
                info!("Mount confirmed for {remote_name} after {step}s");
                return Ok(MountResult {
                    success: true,
                    already_mounted: false,
                    mount_point,
                    remote_name: remote_name.to_string(),
                    error: None,
                });
            }

            let exited = {
                let proc_ref = self.processes.get_mut(remote_name);
                match proc_ref {
                    Some(c) => c.try_wait()?,
                    None => None,
                }
            };

            if let Some(status) = exited {
                self.processes.remove(remote_name);
                let mut err_buf = String::new();
                if let Some(mut pipe) = stderr_pipe.take() {
                    let _ = pipe.read_to_string(&mut err_buf).await;
                }
                let err_msg = if err_buf.trim().is_empty() {
                    format!("Process exited early with status {status}")
                } else {
                    err_buf.trim().to_string()
                };
                error!("Rclone mount failed for {remote_name}: {err_msg}");
                return Ok(MountResult {
                    success: false,
                    already_mounted: false,
                    mount_point,
                    remote_name: remote_name.to_string(),
                    error: Some(err_msg),
                });
            }
        }

        Ok(MountResult {
            success: false,
            already_mounted: false,
            mount_point,
            remote_name: remote_name.to_string(),
            error: Some("Mount launched but did not appear within 30s timeout".to_string()),
        })
    }

    /// Cleanly terminates the managed process for `remote_name` and runs `fusermount -uz`.
    pub async fn unmount_remote(&mut self, remote_name: &str) -> bool {
        let mount_point = self.get_mount_point(remote_name);
        info!("Unmounting {remote_name}...");

        if let Some(mut child) = self.processes.remove(remote_name) {
            let _ = child.start_kill();
            let _ = timeout(Duration::from_secs(5), child.wait()).await;
        }

        let fusermount = resolve_fusermount_binary();
        match Command::new(fusermount)
            .args(["-uz"])
            .arg(&mount_point)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await
        {
            Ok(status) => status.success(),
            Err(err) => {
                error!("fusermount failed for {remote_name}: {err}");
                false
            }
        }
    }
}

impl Drop for MountManager {
    fn drop(&mut self) {
        self.cleanup_all();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn builds_mount_args_for_default_read_only_and_network_modes() {
        let mgr = MountManager::new(
            PathBuf::from("/tmp/RcloneMounts"),
            PathBuf::from("/tmp/vfs"),
            PathBuf::from("/tmp/rclone.conf"),
        );
        let mp = mgr.get_mount_point("gdrive");

        let default_args = mgr.build_mount_args("gdrive", &mp, MountOptions::default());
        assert!(
            default_args
                .windows(2)
                .any(|w| w == ["--vfs-cache-mode", "full"])
        );
        assert!(default_args.windows(2).any(|w| w == ["--max-size", "1G"]));
        assert!(default_args.contains(&"--allow-non-empty".to_string()));
        assert!(!default_args.contains(&"--read-only".to_string()));

        let safe_args = mgr.build_mount_args(
            "gdrive",
            &mp,
            MountOptions {
                read_only: true,
                network_mode: true,
            },
        );
        assert!(
            safe_args
                .windows(2)
                .any(|w| w == ["--vfs-cache-mode", "minimal"])
        );
        assert!(safe_args.contains(&"--read-only".to_string()));
    }

    #[test]
    fn detects_mount_points_in_proc_mounts_including_spaces() {
        let proc_mounts = "\
/dev/nvme0n1p2 / ext4 rw,relatime 0 0\n\
gdrive: /home/user/RcloneMounts/My\\040Drive fuse.rclone rw,nosuid,nodev 0 0\n";

        assert!(MountManager::is_mounted_in_proc_mounts(
            Path::new("/home/user/RcloneMounts/My Drive"),
            proc_mounts
        ));
        assert!(!MountManager::is_mounted_in_proc_mounts(
            Path::new("/home/user/RcloneMounts/Other"),
            proc_mounts
        ));
    }

    #[test]
    fn cleanup_zombie_removes_only_empty_stale_directory() {
        let root = tempdir().expect("tempdir");
        let mgr = MountManager::new(
            root.path().to_path_buf(),
            root.path().join("vfs"),
            root.path().join("rclone.conf"),
        );

        let empty_dir = mgr.get_mount_point("stale_empty");
        fs::create_dir_all(empty_dir.join("a/b/c")).expect("create nested empty dirs");
        mgr.cleanup_zombie(&empty_dir);
        assert!(
            !empty_dir.exists(),
            "stale mount dir with only empty subdirectories should be pruned"
        );

        let non_empty_dir = mgr.get_mount_point("non_empty");
        fs::create_dir_all(&non_empty_dir).expect("create non-empty dir");
        fs::write(non_empty_dir.join("keep.txt"), "data").expect("write file");
        mgr.cleanup_zombie(&non_empty_dir);
        assert!(non_empty_dir.exists(), "non-empty dir must never be wiped");
    }
}
