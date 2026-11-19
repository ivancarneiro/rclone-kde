use std::io::{ErrorKind, Write};
use std::os::linux::net::SocketAddrExt;
use std::os::unix::net::{
    SocketAddr, UnixListener as StdUnixListener, UnixStream as StdUnixStream,
};

use anyhow::{Context, Result};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::net::UnixListener;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tracing::{debug, warn};

/// Commands received by the primary instance from secondary invocations.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InstanceCommand {
    Show,
}

/// Keeps the single-instance abstract socket listener alive until dropped.
#[derive(Debug)]
pub struct SingleInstanceGuard {
    accept_task: JoinHandle<()>,
}

impl Drop for SingleInstanceGuard {
    fn drop(&mut self) {
        self.accept_task.abort();
    }
}

/// Acquires the Linux abstract Unix socket `\0<app_id>`.
///
/// - If no other instance is running, binds the socket and returns `Ok(Some((guard, rx)))`.
/// - If another instance already owns the socket (`AddrInUse`), sends `"SHOW\n"` to it
///   and returns `Ok(None)` so the caller can exit cleanly.
pub async fn acquire_or_notify(
    app_id: &str,
) -> Result<Option<(SingleInstanceGuard, mpsc::Receiver<InstanceCommand>)>> {
    let addr = SocketAddr::from_abstract_name(app_id.as_bytes())
        .with_context(|| format!("Invalid abstract socket name: {app_id}"))?;

    match StdUnixListener::bind_addr(&addr) {
        Ok(std_listener) => {
            std_listener
                .set_nonblocking(true)
                .context("Failed to set single-instance socket nonblocking")?;
            let listener = UnixListener::from_std(std_listener)
                .context("Failed to adopt single-instance listener into Tokio")?;

            let (tx, rx) = mpsc::channel(8);
            let accept_task = tokio::spawn(async move {
                loop {
                    match listener.accept().await {
                        Ok((stream, _)) => {
                            let mut reader = BufReader::new(stream);
                            let mut line = String::new();
                            match reader.read_line(&mut line).await {
                                Ok(0) => {}
                                Ok(_) => {
                                    if line.trim() == "SHOW" {
                                        debug!("Received SHOW wakeup from secondary instance");
                                        if tx.send(InstanceCommand::Show).await.is_err() {
                                            break;
                                        }
                                    }
                                }
                                Err(err) => {
                                    warn!("Failed reading from single-instance peer: {err}");
                                }
                            }
                        }
                        Err(err) => {
                            warn!("Single-instance accept error: {err}");
                            break;
                        }
                    }
                }
            });

            Ok(Some((SingleInstanceGuard { accept_task }, rx)))
        }
        Err(err) if err.kind() == ErrorKind::AddrInUse => {
            notify_existing_instance(&addr)?;
            Ok(None)
        }
        Err(err) => Err(err).context("Failed to bind single-instance abstract socket"),
    }
}

fn notify_existing_instance(addr: &SocketAddr) -> Result<()> {
    let mut stream =
        StdUnixStream::connect_addr(addr).context("Failed to connect to active instance socket")?;
    stream
        .write_all(b"SHOW\n")
        .and_then(|()| stream.flush())
        .context("Failed to send SHOW wakeup command")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    use tokio::time::timeout;

    #[tokio::test]
    async fn primary_receives_show_command_from_secondary_invocation() {
        let test_id = format!("rclone_manager_test_{}", std::process::id());

        let (guard, mut rx) = acquire_or_notify(&test_id)
            .await
            .expect("bind primary")
            .expect("primary should acquire lock");

        let secondary = acquire_or_notify(&test_id).await.expect("secondary notify");
        assert!(
            secondary.is_none(),
            "secondary should detect active instance"
        );

        let cmd = timeout(Duration::from_secs(2), rx.recv())
            .await
            .expect("timed out waiting for SHOW")
            .expect("channel closed");
        assert_eq!(cmd, InstanceCommand::Show);

        drop(guard);
    }
}
