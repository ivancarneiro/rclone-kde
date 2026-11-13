use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use tracing::info;

const DESKTOP_FILENAME: &str = "rclone-gui-manager.desktop";

/// Manages the XDG autostart `.desktop` entry (`~/.config/autostart/rclone-gui-manager.desktop`).
#[derive(Debug, Clone)]
pub struct AutostartManager {
    autostart_dir: PathBuf,
}

impl AutostartManager {
    pub fn new(autostart_dir: PathBuf) -> Self {
        Self { autostart_dir }
    }

    pub fn from_env() -> Result<Self> {
        let config_dir = dirs::config_dir()
            .or_else(|| dirs::home_dir().map(|h| h.join(".config")))
            .context("Could not determine user config directory")?;
        Ok(Self::new(config_dir.join("autostart")))
    }

    pub fn desktop_file_path(&self) -> PathBuf {
        self.autostart_dir.join(DESKTOP_FILENAME)
    }

    pub fn is_enabled(&self) -> bool {
        self.desktop_file_path().exists()
    }

    pub fn enable(&self, exec_binary: &Path) -> Result<()> {
        fs::create_dir_all(&self.autostart_dir).with_context(|| {
            format!(
                "Failed to create autostart directory {}",
                self.autostart_dir.display()
            )
        })?;

        let content = format!(
            "[Desktop Entry]\n\
             Type=Application\n\
             Name=Rclone GUI Manager\n\
             Comment=Manage and mount Rclone remotes\n\
             Exec={} --minimized\n\
             Icon=utilities-terminal\n\
             Hidden=false\n\
             NoDisplay=false\n\
             X-GNOME-Autostart-enabled=true\n",
            exec_binary.display()
        );

        let path = self.desktop_file_path();
        fs::write(&path, content)
            .with_context(|| format!("Failed to write desktop entry at {}", path.display()))?;
        info!("Autostart enabled: {}", path.display());
        Ok(())
    }

    pub fn disable(&self) -> Result<()> {
        let path = self.desktop_file_path();
        if path.exists() {
            fs::remove_file(&path)
                .with_context(|| format!("Failed to remove desktop entry at {}", path.display()))?;
            info!("Autostart disabled: {}", path.display());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn creates_and_removes_autostart_desktop_entry() {
        let dir = tempdir().expect("tempdir");
        let mgr = AutostartManager::new(dir.path().join("autostart"));
        let bin = Path::new("/usr/local/bin/rclone-manager");

        assert!(!mgr.is_enabled());
        mgr.enable(bin).expect("enable autostart");
        assert!(mgr.is_enabled());

        let content = fs::read_to_string(mgr.desktop_file_path()).expect("read desktop file");
        assert!(content.contains("Exec=/usr/local/bin/rclone-manager --minimized"));
        assert!(content.contains("X-GNOME-Autostart-enabled=true"));

        mgr.disable().expect("disable autostart");
        assert!(!mgr.is_enabled());
        // Disabling again should remain idempotent
        mgr.disable().expect("idempotent disable");
    }
}
