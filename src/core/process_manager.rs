use std::io::Write;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::task::JoinHandle;
use tokio::time::sleep;
use tracing::{info, warn};

use super::config::{augmented_path_env, resolve_binary};

/// Manages the lifecycle of the background `rclone rcd` daemon process.
#[derive(Debug)]
pub struct RcloneProcessManager {
    rc_addr: String,
    rc_user: String,
    rc_pass: String,
    rclone_conf: PathBuf,
    logs_dir: PathBuf,
    child: Option<Child>,
    log_task: Option<JoinHandle<()>>,
}

impl RcloneProcessManager {
    pub fn new(
        rc_addr: impl Into<String>,
        rc_user: impl Into<String>,
        rc_pass: impl Into<String>,
        rclone_conf: PathBuf,
        logs_dir: PathBuf,
    ) -> Self {
        Self {
            rc_addr: rc_addr.into(),
            rc_user: rc_user.into(),
            rc_pass: rc_pass.into(),
            rclone_conf,
            logs_dir,
            child: None,
            log_task: None,
        }
    }

    pub fn is_rclone_installed() -> bool {
        resolve_binary("rclone").is_absolute()
    }

    /// Builds the CLI arguments for `rclone rcd`.
    pub fn build_rcd_args(&self) -> Vec<String> {
        let mut args = vec![
            "rcd".to_string(),
            "--rc-addr".to_string(),
            self.rc_addr.clone(),
            "--rc-user".to_string(),
            self.rc_user.clone(),
            "--config".to_string(),
            self.rclone_conf.to_string_lossy().into_owned(),
            "--drive-acknowledge-abuse".to_string(),
            "-vv".to_string(),
        ];

        if self.rc_pass.is_empty() {
            args.push("--rc-no-auth".to_string());
        }

        args
    }

    async fn cleanup_port_hogs(&self) {
        let pattern = format!("rc-addr.*{}", self.rc_addr);
        info!("Cleaning up stale rclone processes matching '{pattern}'...");
        let _ = Command::new("pkill")
            .args(["-f", &pattern])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await;
        sleep(Duration::from_millis(400)).await;
    }

    /// Starts `rclone rcd` and pipes its stdout/stderr into a daily rotating log file.
    pub async fn start_daemon(&mut self) -> Result<()> {
        if !Self::is_rclone_installed() {
            bail!("rclone binary not found in PATH");
        }

        if let Some(child) = &mut self.child
            && child.try_wait()?.is_none()
        {
            return Ok(());
        }

        self.cleanup_port_hogs().await;

        let rclone_bin = resolve_binary("rclone");
        let args = self.build_rcd_args();
        info!("Starting Rclone daemon on {}", self.rc_addr);

        let mut cmd = Command::new(rclone_bin);
        cmd.args(&args)
            .env("PATH", augmented_path_env())
            .env("RCLONE_RC_PASS", &self.rc_pass)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);

        let mut child = cmd.spawn().context("Failed to spawn `rclone rcd`")?;
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();

        let logs_dir = self.logs_dir.clone();
        self.log_task = Some(tokio::spawn(async move {
            let mut appender = tracing_appender::rolling::daily(&logs_dir, "rclone-daemon.log");

            let mut out_lines = stdout.map(|s| BufReader::new(s).lines());
            let mut err_lines = stderr.map(|s| BufReader::new(s).lines());

            while out_lines.is_some() || err_lines.is_some() {
                tokio::select! {
                    res = async {
                        match out_lines.as_mut() {
                            Some(reader) => reader.next_line().await,
                            None => std::future::pending().await,
                        }
                    }, if out_lines.is_some() => {
                        match res {
                            Ok(Some(line)) => {
                                let _ = writeln!(appender, "[STDOUT] {line}");
                            }
                            Ok(None) | Err(_) => out_lines = None,
                        }
                    }
                    res = async {
                        match err_lines.as_mut() {
                            Some(reader) => reader.next_line().await,
                            None => std::future::pending().await,
                        }
                    }, if err_lines.is_some() => {
                        match res {
                            Ok(Some(line)) => {
                                let _ = writeln!(appender, "[STDERR] {line}");
                            }
                            Ok(None) | Err(_) => err_lines = None,
                        }
                    }
                }
            }
        }));

        self.child = Some(child);
        Ok(())
    }

    /// Gracefully stops the managed `rclone rcd` daemon and its log reader task.
    pub async fn stop_daemon(&mut self) -> Result<()> {
        if let Some(handle) = self.log_task.take() {
            handle.abort();
        }
        if let Some(mut child) = self.child.take() {
            if let Err(err) = child.start_kill() {
                warn!("Failed to terminate rclone daemon: {err}");
            }
            let _ = tokio::time::timeout(Duration::from_secs(5), child.wait()).await;
            info!("Rclone daemon stopped");
        }
        Ok(())
    }
}

impl Drop for RcloneProcessManager {
    fn drop(&mut self) {
        if let Some(handle) = self.log_task.take() {
            handle.abort();
        }
        if let Some(mut child) = self.child.take() {
            let _ = child.start_kill();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_rcd_args_with_and_without_password() {
        let with_pass = RcloneProcessManager::new(
            "127.0.0.1:5572",
            "rclone",
            "secret_pass",
            PathBuf::from("/tmp/rclone.conf"),
            PathBuf::from("/tmp/logs"),
        );
        let args = with_pass.build_rcd_args();
        assert_eq!(args[0], "rcd");
        assert!(
            args.windows(2)
                .any(|w| w == ["--rc-addr", "127.0.0.1:5572"])
        );
        assert!(
            args.windows(2)
                .any(|w| w == ["--config", "/tmp/rclone.conf"])
        );
        assert!(!args.contains(&"--rc-no-auth".to_string()));

        let without_pass = RcloneProcessManager::new(
            "127.0.0.1:5572",
            "rclone",
            "",
            PathBuf::from("/tmp/rclone.conf"),
            PathBuf::from("/tmp/logs"),
        );
        assert!(
            without_pass
                .build_rcd_args()
                .contains(&"--rc-no-auth".to_string())
        );
    }
}
