use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

/// Persisted synchronization task definition.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SyncTask {
    pub id: u32,
    pub name: String,
    pub local_path: String,
    pub remote_path: String,
    pub remote_name: String,
    #[serde(default = "default_strategy")]
    pub strategy: String,
    #[serde(default = "default_last_sync")]
    pub last_sync: String,
    #[serde(default = "default_status")]
    pub status: String,
}

fn default_strategy() -> String {
    "bisync".to_string()
}

fn default_last_sync() -> String {
    "Never".to_string()
}

fn default_status() -> String {
    "Idle".to_string()
}

/// Manages persistence and legacy migration of `sync_tasks.json`.
#[derive(Debug, Clone)]
pub struct SyncManager {
    tasks_path: PathBuf,
    tasks: Vec<SyncTask>,
}

impl SyncManager {
    /// Loads tasks from `tasks_path`, migrating from `legacy_path` on first launch if present.
    pub fn load_or_migrate(tasks_path: PathBuf, legacy_path: Option<&Path>) -> Result<Self> {
        let mut manager = Self {
            tasks_path,
            tasks: Vec::new(),
        };

        if manager.tasks_path.exists() {
            manager.tasks = Self::read_tasks_file(&manager.tasks_path);
            return Ok(manager);
        }

        if let Some(legacy) = legacy_path
            && legacy.exists()
        {
            info!(
                "Migrating legacy sync tasks from {} to {}",
                legacy.display(),
                manager.tasks_path.display()
            );
            manager.tasks = Self::read_tasks_file(legacy);
            manager.save()?;
        }

        Ok(manager)
    }

    fn read_tasks_file(path: &Path) -> Vec<SyncTask> {
        match fs::read_to_string(path) {
            Ok(raw) => match serde_json::from_str::<Vec<SyncTask>>(&raw) {
                Ok(parsed) => parsed,
                Err(err) => {
                    warn!(
                        "Corrupted sync tasks at {}: {err}. Using empty list.",
                        path.display()
                    );
                    Vec::new()
                }
            },
            Err(err) => {
                warn!(
                    "Failed to read sync tasks at {}: {err}. Using empty list.",
                    path.display()
                );
                Vec::new()
            }
        }
    }

    pub fn save(&self) -> Result<()> {
        if let Some(parent) = self.tasks_path.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create sync tasks dir {}", parent.display()))?;
        }
        let json =
            serde_json::to_string_pretty(&self.tasks).context("Failed to serialize sync tasks")?;
        fs::write(&self.tasks_path, json).with_context(|| {
            format!(
                "Failed to write sync tasks to {}",
                self.tasks_path.display()
            )
        })?;
        Ok(())
    }

    pub fn get_tasks(&self) -> &[SyncTask] {
        &self.tasks
    }

    pub fn add_task(
        &mut self,
        name: &str,
        local_path: &str,
        remote_path: &str,
        remote_name: &str,
        strategy: &str,
    ) -> Result<SyncTask> {
        let next_id = self.tasks.iter().map(|t| t.id).max().unwrap_or(0) + 1;
        let task = SyncTask {
            id: next_id,
            name: name.to_string(),
            local_path: local_path.to_string(),
            remote_path: remote_path.to_string(),
            remote_name: remote_name.to_string(),
            strategy: if strategy.is_empty() {
                default_strategy()
            } else {
                strategy.to_string()
            },
            last_sync: default_last_sync(),
            status: default_status(),
        };
        self.tasks.push(task.clone());
        self.save()?;
        Ok(task)
    }

    pub fn remove_task(&mut self, task_id: u32) -> Result<()> {
        let before = self.tasks.len();
        self.tasks.retain(|t| t.id != task_id);
        if self.tasks.len() != before {
            self.save()?;
        }
        Ok(())
    }

    pub fn update_task(
        &mut self,
        task_id: u32,
        name: &str,
        local_path: &str,
        remote_path: &str,
        remote_name: &str,
        strategy: &str,
    ) -> Result<()> {
        if let Some(task) = self.tasks.iter_mut().find(|t| t.id == task_id) {
            task.name = name.to_string();
            task.local_path = local_path.to_string();
            task.remote_path = remote_path.to_string();
            task.remote_name = remote_name.to_string();
            task.strategy = if strategy.is_empty() {
                default_strategy()
            } else {
                strategy.to_string()
            };
            task.status = default_status();
            self.save()?;
        }
        Ok(())
    }

    pub fn update_task_status(
        &mut self,
        task_id: u32,
        status: &str,
        last_sync: Option<&str>,
    ) -> Result<()> {
        if let Some(task) = self.tasks.iter_mut().find(|t| t.id == task_id) {
            task.status = status.to_string();
            if let Some(ts) = last_sync {
                task.last_sync = ts.to_string();
            }
            self.save()?;
        }
        Ok(())
    }

    pub fn get_strategy_for_remote(&self, remote_name: &str) -> Option<&str> {
        self.tasks
            .iter()
            .find(|t| t.remote_name == remote_name)
            .map(|t| t.strategy.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn migrates_legacy_tasks_and_supports_crud() {
        let dir = tempdir().expect("tempdir");
        let legacy_path = dir.path().join("legacy_sync_tasks.json");
        let target_path = dir.path().join("xdg/rclone-manager/sync_tasks.json");

        let legacy_json = r#"[
            {
                "id": 1,
                "name": "Docs",
                "local_path": "/tmp/docs",
                "remote_path": "Docs",
                "remote_name": "gdrive",
                "strategy": "bisync",
                "last_sync": "Never",
                "status": "Idle"
            }
        ]"#;
        fs::write(&legacy_path, legacy_json).expect("write legacy");

        let mut mgr = SyncManager::load_or_migrate(target_path.clone(), Some(&legacy_path))
            .expect("migrate tasks");
        assert_eq!(mgr.get_tasks().len(), 1);
        assert_eq!(mgr.get_strategy_for_remote("gdrive"), Some("bisync"));

        let added = mgr
            .add_task("Backup", "/tmp/bak", "Backup", "work", "sync")
            .expect("add task");
        assert_eq!(added.id, 2);

        mgr.update_task_status(2, "Idle", Some("2026-11-13 03:40:00"))
            .expect("update status");
        mgr.update_task(1, "Docs Renamed", "/tmp/docs2", "Docs2", "gdrive", "copy")
            .expect("update task");

        let reloaded = SyncManager::load_or_migrate(target_path, None).expect("reload");
        assert_eq!(reloaded.get_tasks().len(), 2);
        assert_eq!(reloaded.get_tasks()[0].name, "Docs Renamed");
        assert_eq!(reloaded.get_tasks()[0].strategy, "copy");
        assert_eq!(reloaded.get_tasks()[1].last_sync, "2026-11-13 03:40:00");

        mgr.remove_task(1).expect("remove task");
        assert_eq!(mgr.get_tasks().len(), 1);
        assert_eq!(mgr.get_tasks()[0].id, 2);
    }
}
