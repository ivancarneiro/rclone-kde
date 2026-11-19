use std::env;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

pub const APP_NAME: &str = "rclone-manager";
pub const KEYRING_SERVICE: &str = "RcloneKDE";
pub const RC_DEFAULT_ADDR: &str = "127.0.0.1:5572";
pub const RC_DEFAULT_USER: &str = "rclone";
pub const SINGLE_INSTANCE_ID: &str = "rclone_manager_gna_lock";

/// Resolved XDG and user paths for Rclone Manager.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AppPaths {
    pub config_dir: PathBuf,
    pub cache_dir: PathBuf,
    pub vfs_cache_dir: PathBuf,
    pub logs_dir: PathBuf,
    pub default_mount_dir: PathBuf,
    pub rclone_conf: PathBuf,
}

impl AppPaths {
    /// Builds `AppPaths` from explicit root directories (useful for tests).
    pub fn with_roots(home: PathBuf, config_home: PathBuf, cache_home: PathBuf) -> Self {
        let config_dir = config_home.join(APP_NAME);
        let cache_dir = cache_home.join(APP_NAME);
        let vfs_cache_dir = cache_dir.join("vfs");
        let logs_dir = cache_dir.join("logs");
        let default_mount_dir = home.join("RcloneMounts");
        let rclone_conf = config_home.join("rclone").join("rclone.conf");

        Self {
            config_dir,
            cache_dir,
            vfs_cache_dir,
            logs_dir,
            default_mount_dir,
            rclone_conf,
        }
    }

    /// Resolves paths using standard XDG directories from the environment.
    pub fn from_env() -> Result<Self> {
        let home = dirs::home_dir().context("Could not determine user home directory")?;
        let config_home = dirs::config_dir().unwrap_or_else(|| home.join(".config"));
        let cache_home = dirs::cache_dir().unwrap_or_else(|| home.join(".cache"));
        Ok(Self::with_roots(home, config_home, cache_home))
    }

    pub fn settings_file(&self) -> PathBuf {
        self.config_dir.join("settings.json")
    }

    pub fn sync_tasks_file(&self) -> PathBuf {
        self.config_dir.join("sync_tasks.json")
    }

    /// Creates the managed XDG and default mount directories if missing.
    pub fn ensure_dirs(&self) -> Result<()> {
        for dir in [
            &self.config_dir,
            &self.cache_dir,
            &self.vfs_cache_dir,
            &self.logs_dir,
            &self.default_mount_dir,
        ] {
            fs::create_dir_all(dir)
                .with_context(|| format!("Failed to create directory: {}", dir.display()))?;
        }
        Ok(())
    }
}

/// Generates 16 cryptographic random bytes from `/dev/urandom` as a 32-char lowercase hex string.
pub fn generate_random_hex_16() -> Result<String> {
    let mut bytes = [0u8; 16];
    let mut file = File::open("/dev/urandom").context("Failed to open /dev/urandom")?;
    file.read_exact(&mut bytes)
        .context("Failed to read random bytes from /dev/urandom")?;

    let mut hex = String::with_capacity(32);
    for b in bytes {
        use std::fmt::Write;
        let _ = write!(&mut hex, "{b:02x}");
    }
    Ok(hex)
}

fn is_executable_file(path: &Path) -> bool {
    let Ok(meta) = fs::metadata(path) else {
        return false;
    };
    meta.is_file() && (meta.permissions().mode() & 0o111 != 0)
}

/// Builds a `PATH` `OsString` combining user local/cargo bins and standard system
/// paths with the current process `PATH`, ensuring compatibility under `systemd --user`.
pub fn augmented_path_env() -> OsString {
    let mut dirs_list: Vec<PathBuf> = Vec::new();
    if let Some(home) = dirs::home_dir() {
        dirs_list.push(home.join(".local/bin"));
        dirs_list.push(home.join(".cargo/bin"));
    }
    dirs_list.push(PathBuf::from("/usr/local/bin"));
    dirs_list.push(PathBuf::from("/usr/bin"));
    dirs_list.push(PathBuf::from("/bin"));

    if let Some(current) = env::var_os("PATH") {
        for p in env::split_paths(&current) {
            if !dirs_list.contains(&p) {
                dirs_list.push(p);
            }
        }
    }

    env::join_paths(dirs_list).unwrap_or_else(|_| OsString::from("/usr/local/bin:/usr/bin:/bin"))
}

/// Searches for an executable in `augmented_path_env()`. Falls back to `name`.
pub fn resolve_binary(name: &str) -> PathBuf {
    resolve_binary_in_path(name, &augmented_path_env())
}

fn resolve_binary_in_path(name: &str, path_env: &OsString) -> PathBuf {
    for dir in env::split_paths(path_env) {
        let candidate = dir.join(name);
        if is_executable_file(&candidate) {
            return candidate;
        }
    }
    PathBuf::from(name)
}

/// Resolves `fusermount` or `fusermount3`, preferring `fusermount`.
pub fn resolve_fusermount_binary() -> PathBuf {
    let path_env = augmented_path_env();
    let primary = resolve_binary_in_path("fusermount", &path_env);
    if primary.is_absolute() {
        return primary;
    }
    let fallback = resolve_binary_in_path("fusermount3", &path_env);
    if fallback.is_absolute() {
        return fallback;
    }
    PathBuf::from("fusermount")
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn resolves_xdg_paths_from_roots() {
        let home = PathBuf::from("/tmp/test-home");
        let config = PathBuf::from("/tmp/test-config");
        let cache = PathBuf::from("/tmp/test-cache");

        let paths = AppPaths::with_roots(home, config, cache);

        assert_eq!(
            paths.config_dir,
            PathBuf::from("/tmp/test-config/rclone-manager")
        );
        assert_eq!(
            paths.cache_dir,
            PathBuf::from("/tmp/test-cache/rclone-manager")
        );
        assert_eq!(
            paths.vfs_cache_dir,
            PathBuf::from("/tmp/test-cache/rclone-manager/vfs")
        );
        assert_eq!(
            paths.logs_dir,
            PathBuf::from("/tmp/test-cache/rclone-manager/logs")
        );
        assert_eq!(
            paths.default_mount_dir,
            PathBuf::from("/tmp/test-home/RcloneMounts")
        );
        assert_eq!(
            paths.rclone_conf,
            PathBuf::from("/tmp/test-config/rclone/rclone.conf")
        );
        assert_eq!(
            paths.settings_file(),
            PathBuf::from("/tmp/test-config/rclone-manager/settings.json")
        );
        assert_eq!(
            paths.sync_tasks_file(),
            PathBuf::from("/tmp/test-config/rclone-manager/sync_tasks.json")
        );
    }

    #[test]
    fn ensure_dirs_creates_all_managed_directories() {
        let root = tempdir().expect("create temp dir");
        let paths = AppPaths::with_roots(
            root.path().join("home"),
            root.path().join("config"),
            root.path().join("cache"),
        );

        paths.ensure_dirs().expect("ensure dirs");

        assert!(paths.config_dir.is_dir());
        assert!(paths.cache_dir.is_dir());
        assert!(paths.vfs_cache_dir.is_dir());
        assert!(paths.logs_dir.is_dir());
        assert!(paths.default_mount_dir.is_dir());
    }

    #[test]
    fn generate_random_hex_16_produces_32_unique_hex_chars() {
        let first = generate_random_hex_16().expect("first token");
        let second = generate_random_hex_16().expect("second token");

        assert_eq!(first.len(), 32);
        assert!(first.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(first, second);
    }

    #[test]
    fn augmented_path_and_resolve_binary_locate_executables() {
        let path_env = augmented_path_env();
        let paths: Vec<PathBuf> = env::split_paths(&path_env).collect();
        assert!(paths.contains(&PathBuf::from("/usr/bin")));

        let temp = tempdir().expect("tempdir");
        let fake_bin = temp.path().join("custom-rclone-bin");
        fs::write(&fake_bin, "#!/bin/sh\n").expect("write binary");
        let mut perms = fs::metadata(&fake_bin).expect("metadata").permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&fake_bin, perms).expect("chmod");

        let custom_path = env::join_paths([temp.path()]).expect("join paths");
        assert_eq!(
            resolve_binary_in_path("custom-rclone-bin", &custom_path),
            fake_bin
        );
        assert_eq!(
            resolve_binary_in_path("missing-bin", &custom_path),
            PathBuf::from("missing-bin")
        );
    }
}
