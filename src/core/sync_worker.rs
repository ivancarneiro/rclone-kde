use std::fs;
use std::path::{Path, PathBuf};
use std::process::Stdio;

use anyhow::{Context, Result, bail};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tracing::{error, info};

use super::config::augmented_path_env;
use super::sync_manager::SyncTask;

/// Events streamed from a supervised sync subprocess.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SyncEvent {
    LogLine { task_id: u32, line: String },
    NeedsResync { task_id: u32 },
    FinishedSuccess { task_id: u32 },
    FinishedError { task_id: u32, error: String },
}

/// Validates safety invariants and builds `rclone` arguments for `bisync`, `sync`, or `copy`.
pub fn validate_and_build_sync_args(
    task: &SyncTask,
    rclone_conf: &Path,
    force_resync: bool,
    dry_run: bool,
) -> Result<Vec<String>> {
    let local = Path::new(&task.local_path);
    if !local.exists() {
        bail!(
            "SAFETY: Local path '{}' is missing. Aborting.",
            task.local_path
        );
    }

    if task.strategy == "sync" {
        let mut entries = fs::read_dir(local).with_context(|| {
            format!(
                "SAFETY: Cannot read local folder '{}'. Aborting.",
                task.local_path
            )
        })?;
        if entries.next().is_none() {
            bail!("SAFETY: Local folder is empty. This would wipe the remote (Backup). Aborting.");
        }
    }

    let remote_spec = format!("{}:{}", task.remote_name, task.remote_path);
    let mut args = Vec::new();

    match task.strategy.as_str() {
        "bisync" => {
            args.push("bisync".to_string());
            args.push(task.local_path.clone());
            args.push(remote_spec);
            let never_synced = task.last_sync.is_empty() || task.last_sync == "Never";
            if force_resync || (never_synced && !dry_run) {
                args.push("--resync".to_string());
            }
            args.push("--max-delete".to_string());
            args.push("5".to_string());
        }
        "sync" => {
            args.push("sync".to_string());
            args.push(task.local_path.clone());
            args.push(remote_spec);
            args.push("--max-delete".to_string());
            args.push("5".to_string());
        }
        "copy" => {
            args.push("copy".to_string());
            args.push(remote_spec);
            args.push(task.local_path.clone());
        }
        other => bail!("Unsupported sync strategy: {other}"),
    }

    args.extend([
        "--verbose".to_string(),
        "--config".to_string(),
        rclone_conf.to_string_lossy().into_owned(),
        "--drive-acknowledge-abuse".to_string(),
        "--drive-import-formats".to_string(),
        "docx,xlsx,pptx".to_string(),
        "--max-size".to_string(),
        "1G".to_string(),
    ]);

    if dry_run {
        args.push("--dry-run".to_string());
    }

    Ok(args)
}

/// Spawns a supervised sync subprocess (`kill_on_drop`) and streams log lines via `mpsc`.
pub fn spawn_sync_process(
    task_id: u32,
    program: PathBuf,
    args: Vec<String>,
    tx: mpsc::Sender<SyncEvent>,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        info!(
            "SyncWorker starting task {task_id}: {} {:?}",
            program.display(),
            args
        );

        let mut cmd = Command::new(&program);
        cmd.args(&args)
            .env("PATH", augmented_path_env())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);

        let mut child = match cmd.spawn() {
            Ok(c) => c,
            Err(err) => {
                error!("Failed spawning sync process for task {task_id}: {err}");
                let _ = tx
                    .send(SyncEvent::FinishedError {
                        task_id,
                        error: err.to_string(),
                    })
                    .await;
                return;
            }
        };

        let mut out_lines = child.stdout.take().map(|s| BufReader::new(s).lines());
        let mut err_lines = child.stderr.take().map(|s| BufReader::new(s).lines());

        while out_lines.is_some() || err_lines.is_some() {
            let line_opt = tokio::select! {
                res = async {
                    match out_lines.as_mut() {
                        Some(r) => r.next_line().await,
                        None => std::future::pending().await,
                    }
                }, if out_lines.is_some() => {
                    match res {
                        Ok(Some(line)) => Some(line),
                        Ok(None) | Err(_) => {
                            out_lines = None;
                            None
                        }
                    }
                }
                res = async {
                    match err_lines.as_mut() {
                        Some(r) => r.next_line().await,
                        None => std::future::pending().await,
                    }
                }, if err_lines.is_some() => {
                    match res {
                        Ok(Some(line)) => Some(line),
                        Ok(None) | Err(_) => {
                            err_lines = None;
                            None
                        }
                    }
                }
            };

            if let Some(raw) = line_opt {
                let clean = raw.trim().to_string();
                if clean.is_empty() {
                    continue;
                }
                if clean.contains("Must run --resync to recover")
                    || clean.contains("cannot find prior")
                {
                    let _ = tx.send(SyncEvent::NeedsResync { task_id }).await;
                }
                if tx
                    .send(SyncEvent::LogLine {
                        task_id,
                        line: clean,
                    })
                    .await
                    .is_err()
                {
                    break;
                }
            }
        }

        match child.wait().await {
            Ok(status) if status.success() => {
                let _ = tx.send(SyncEvent::FinishedSuccess { task_id }).await;
            }
            Ok(status) => {
                let code = status
                    .code()
                    .map(|c| c.to_string())
                    .unwrap_or_else(|| "signal".to_string());
                let _ = tx
                    .send(SyncEvent::FinishedError {
                        task_id,
                        error: format!("Process finished with exit code {code}"),
                    })
                    .await;
            }
            Err(err) => {
                let _ = tx
                    .send(SyncEvent::FinishedError {
                        task_id,
                        error: err.to_string(),
                    })
                    .await;
            }
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn sample_task(local_path: &Path, strategy: &str) -> SyncTask {
        SyncTask {
            id: 1,
            name: "Test".to_string(),
            local_path: local_path.to_string_lossy().into_owned(),
            remote_path: "Folder".to_string(),
            remote_name: "gdrive".to_string(),
            strategy: strategy.to_string(),
            last_sync: "Never".to_string(),
            status: "Idle".to_string(),
        }
    }

    #[test]
    fn aborts_sync_strategy_when_local_folder_is_empty() {
        let dir = tempdir().expect("tempdir");
        let task = sample_task(dir.path(), "sync");
        let conf = dir.path().join("rclone.conf");

        let err = validate_and_build_sync_args(&task, &conf, false, false)
            .expect_err("empty folder must abort sync");
        assert!(err.to_string().contains("SAFETY: Local folder is empty"));

        fs::write(dir.path().join("file.txt"), "ok").expect("create file");
        let args =
            validate_and_build_sync_args(&task, &conf, false, false).expect("non-empty sync");
        assert_eq!(args[0], "sync");
        assert!(args.windows(2).any(|w| w == ["--max-delete", "5"]));
    }

    #[test]
    fn builds_bisync_copy_and_dry_run_flags() {
        let dir = tempdir().expect("tempdir");
        let conf = dir.path().join("rclone.conf");

        let bisync = sample_task(dir.path(), "bisync");
        let bisync_args =
            validate_and_build_sync_args(&bisync, &conf, false, false).expect("bisync args");
        assert_eq!(bisync_args[0], "bisync");
        assert!(bisync_args.contains(&"--resync".to_string()));
        assert!(bisync_args.windows(2).any(|w| w == ["--max-delete", "5"]));

        let dry_args =
            validate_and_build_sync_args(&bisync, &conf, false, true).expect("dry run args");
        assert!(!dry_args.contains(&"--resync".to_string()));
        assert!(dry_args.contains(&"--dry-run".to_string()));

        let copy = sample_task(dir.path(), "copy");
        let copy_args =
            validate_and_build_sync_args(&copy, &conf, false, false).expect("copy args");
        assert_eq!(copy_args[0], "copy");
        assert_eq!(copy_args[1], "gdrive:Folder");
        assert_eq!(copy_args[2], dir.path().to_string_lossy());
    }

    #[tokio::test]
    async fn streams_live_logs_and_detects_resync_trigger() {
        let (tx, mut rx) = mpsc::channel(16);
        let handle = spawn_sync_process(
            7,
            PathBuf::from("/bin/sh"),
            vec![
                "-c".to_string(),
                "echo 'INFO: synced.txt: Copied (new)'; echo 'ERROR: Must run --resync to recover' >&2"
                    .to_string(),
            ],
            tx,
        );

        let mut events = Vec::new();
        while let Some(ev) = rx.recv().await {
            events.push(ev);
        }
        handle.await.expect("join worker");

        assert!(events.contains(&SyncEvent::LogLine {
            task_id: 7,
            line: "INFO: synced.txt: Copied (new)".to_string(),
        }));
        assert!(events.contains(&SyncEvent::NeedsResync { task_id: 7 }));
        assert!(events.contains(&SyncEvent::FinishedSuccess { task_id: 7 }));
    }
}
