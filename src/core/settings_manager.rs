use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

const DEFAULT_SYNC_STRATEGY: &str = "bisync";

/// Persisted application preferences (strictly excludes legacy KeePassXC fields).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct AppSettings {
    pub auto_mounts: Vec<String>,
    pub start_minimized: bool,
    pub mount_dir: Option<PathBuf>,
    pub sync_strategies: HashMap<String, String>,
}

/// Manages loading, legacy migration, and saving `settings.json` under XDG config.
#[derive(Debug, Clone)]
pub struct SettingsManager {
    settings_path: PathBuf,
    default_mount_dir: PathBuf,
    settings: AppSettings,
}

impl SettingsManager {
    /// Loads settings from `settings_path`, migrating from `legacy_path` if needed.
    ///
    /// Legacy unknown fields such as `keepassxc_remote` and `keepassxc_db_path` are
    /// automatically dropped upon deserialization and clean persistence.
    pub fn load_or_migrate(
        settings_path: PathBuf,
        default_mount_dir: PathBuf,
        legacy_path: Option<&Path>,
    ) -> Result<Self> {
        let mut manager = Self {
            settings_path,
            default_mount_dir,
            settings: AppSettings::default(),
        };

        if manager.settings_path.exists() {
            manager.settings = Self::read_settings_file(&manager.settings_path);
            return Ok(manager);
        }

        if let Some(legacy) = legacy_path
            && legacy.exists()
        {
            info!(
                "Migrating legacy settings from {} to {}",
                legacy.display(),
                manager.settings_path.display()
            );
            manager.settings = Self::read_settings_file(legacy);
            manager.save()?;
        }

        Ok(manager)
    }

    fn read_settings_file(path: &Path) -> AppSettings {
        match fs::read_to_string(path) {
            Ok(raw) => match serde_json::from_str::<AppSettings>(&raw) {
                Ok(parsed) => parsed,
                Err(err) => {
                    warn!(
                        "Corrupted settings at {}: {err}. Using defaults.",
                        path.display()
                    );
                    AppSettings::default()
                }
            },
            Err(err) => {
                warn!(
                    "Failed to read settings at {}: {err}. Using defaults.",
                    path.display()
                );
                AppSettings::default()
            }
        }
    }

    pub fn save(&self) -> Result<()> {
        if let Some(parent) = self.settings_path.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("Failed to create settings directory: {}", parent.display())
            })?;
        }
        let json = serde_json::to_string_pretty(&self.settings)
            .context("Failed to serialize application settings")?;
        fs::write(&self.settings_path, json).with_context(|| {
            format!(
                "Failed to write settings to {}",
                self.settings_path.display()
            )
        })?;
        Ok(())
    }

    pub fn get_auto_mounts(&self) -> &[String] {
        &self.settings.auto_mounts
    }

    pub fn add_auto_mount(&mut self, remote_name: &str) -> Result<()> {
        if !self.settings.auto_mounts.iter().any(|r| r == remote_name) {
            self.settings.auto_mounts.push(remote_name.to_string());
            self.save()?;
        }
        Ok(())
    }

    pub fn remove_auto_mount(&mut self, remote_name: &str) -> Result<()> {
        let before = self.settings.auto_mounts.len();
        self.settings.auto_mounts.retain(|r| r != remote_name);
        if self.settings.auto_mounts.len() != before {
            self.save()?;
        }
        Ok(())
    }

    pub fn is_auto_mount_enabled(&self, remote_name: &str) -> bool {
        self.settings.auto_mounts.iter().any(|r| r == remote_name)
    }

    pub fn set_auto_mount(&mut self, remote_name: &str, enabled: bool) -> Result<()> {
        if enabled {
            self.add_auto_mount(remote_name)
        } else {
            self.remove_auto_mount(remote_name)
        }
    }

    pub fn get_sync_strategy(&self, remote_name: &str) -> &str {
        self.settings
            .sync_strategies
            .get(remote_name)
            .map(String::as_str)
            .unwrap_or(DEFAULT_SYNC_STRATEGY)
    }

    pub fn set_sync_strategy(&mut self, remote_name: &str, strategy: &str) -> Result<()> {
        self.settings
            .sync_strategies
            .insert(remote_name.to_string(), strategy.to_string());
        self.save()
    }

    pub fn get_start_minimized(&self) -> bool {
        self.settings.start_minimized
    }

    pub fn set_start_minimized(&mut self, enabled: bool) -> Result<()> {
        self.settings.start_minimized = enabled;
        self.save()
    }

    pub fn get_mount_dir(&self) -> &Path {
        self.settings
            .mount_dir
            .as_deref()
            .unwrap_or(&self.default_mount_dir)
    }

    pub fn set_mount_dir(&mut self, mount_dir: Option<PathBuf>) -> Result<()> {
        self.settings.mount_dir = mount_dir;
        self.save()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn migrates_legacy_settings_and_drops_keepassxc_fields() {
        let dir = tempdir().expect("tempdir");
        let legacy_path = dir.path().join("legacy_settings.json");
        let target_path = dir.path().join("xdg/rclone-manager/settings.json");
        let default_mounts = dir.path().join("RcloneMounts");

        let legacy_json = r#"{
            "auto_mounts": ["ivanexequielc"],
            "start_minimized": true,
            "keepassxc_remote": "test_remote",
            "keepassxc_db_path": "test.kdbx",
            "sync_strategies": { "ivanexequielc": "sync" }
        }"#;
        fs::write(&legacy_path, legacy_json).expect("write legacy");

        let manager = SettingsManager::load_or_migrate(
            target_path.clone(),
            default_mounts.clone(),
            Some(&legacy_path),
        )
        .expect("migrate settings");

        assert_eq!(manager.get_auto_mounts(), &["ivanexequielc"]);
        assert!(manager.get_start_minimized());
        assert_eq!(manager.get_sync_strategy("ivanexequielc"), "sync");
        assert_eq!(manager.get_sync_strategy("unknown"), "bisync");
        assert_eq!(manager.get_mount_dir(), default_mounts.as_path());

        let persisted = fs::read_to_string(&target_path).expect("read migrated");
        assert!(!persisted.contains("keepassxc"));
    }

    #[test]
    fn updates_auto_mounts_strategies_and_custom_mount_dir() {
        let dir = tempdir().expect("tempdir");
        let settings_path = dir.path().join("settings.json");
        let default_mounts = dir.path().join("RcloneMounts");

        let mut manager =
            SettingsManager::load_or_migrate(settings_path.clone(), default_mounts.clone(), None)
                .expect("init settings");

        manager
            .set_auto_mount("drive1", true)
            .expect("enable auto mount");
        manager
            .set_auto_mount("drive1", true)
            .expect("idempotent add");
        assert!(manager.is_auto_mount_enabled("drive1"));
        assert_eq!(manager.get_auto_mounts().len(), 1);

        manager
            .set_auto_mount("drive1", false)
            .expect("disable auto mount");
        assert!(!manager.is_auto_mount_enabled("drive1"));

        manager
            .set_sync_strategy("drive1", "copy")
            .expect("set strategy");
        manager.set_start_minimized(true).expect("set minimized");

        let custom_dir = dir.path().join("CustomMounts");
        manager
            .set_mount_dir(Some(custom_dir.clone()))
            .expect("set mount_dir");

        let reloaded = SettingsManager::load_or_migrate(settings_path, default_mounts, None)
            .expect("reload settings");
        assert_eq!(reloaded.get_sync_strategy("drive1"), "copy");
        assert!(reloaded.get_start_minimized());
        assert_eq!(reloaded.get_mount_dir(), custom_dir.as_path());
    }

    #[test]
    fn falls_back_to_defaults_on_corrupted_json() {
        let dir = tempdir().expect("tempdir");
        let settings_path = dir.path().join("settings.json");
        fs::write(&settings_path, "{ invalid json").expect("write invalid");

        let manager =
            SettingsManager::load_or_migrate(settings_path, dir.path().join("RcloneMounts"), None)
                .expect("load corrupted");

        assert!(manager.get_auto_mounts().is_empty());
        assert!(!manager.get_start_minimized());
    }
}
