use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::Ordering;

use anyhow::{Context, Result};
use slint::ComponentHandle;
use tokio::signal::unix::{SignalKind, signal};
use tokio::sync::{Mutex, mpsc};
use tracing::{error, info, warn};
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::{EnvFilter, fmt, layer::SubscriberExt, util::SubscriberInitExt};

use rclone_manager::core::autostart_manager::AutostartManager;
use rclone_manager::core::config::{
    AppPaths, RC_DEFAULT_ADDR, RC_DEFAULT_USER, SINGLE_INSTANCE_ID,
};
use rclone_manager::core::mount_manager::MountManager;
use rclone_manager::core::process_manager::RcloneProcessManager;
use rclone_manager::core::rclone_client::RcloneClient;
use rclone_manager::core::secret_manager::SecretManager;
use rclone_manager::core::settings_manager::SettingsManager;
use rclone_manager::core::single_instance;
use rclone_manager::core::sync_manager::SyncManager;
use rclone_manager::ui::AppWindow;
use rclone_manager::ui::controller::AppController;
use rclone_manager::ui::tray::{TrayAction, spawn_tray};

fn init_logging(logs_dir: &Path) -> WorkerGuard {
    let file_appender = tracing_appender::rolling::daily(logs_dir, "rclone-manager.log");
    let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    tracing_subscriber::registry()
        .with(env_filter)
        .with(fmt::layer().with_target(true))
        .with(fmt::layer().with_ansi(false).with_writer(non_blocking))
        .init();

    guard
}

fn spawn_signal_handler(rt: &tokio::runtime::Handle, quitting: Arc<std::sync::atomic::AtomicBool>) {
    rt.spawn(async move {
        let sigint = tokio::signal::ctrl_c();
        let mut sigterm = match signal(SignalKind::terminate()) {
            Ok(s) => Some(s),
            Err(err) => {
                warn!("Could not install SIGTERM handler: {err}");
                None
            }
        };

        tokio::select! {
            _ = sigint => {
                info!("Received SIGINT, shutting down gracefully...");
            }
            _ = async {
                if let Some(ref mut s) = sigterm {
                    s.recv().await;
                } else {
                    std::future::pending::<()>().await;
                }
            } => {
                info!("Received SIGTERM, shutting down gracefully...");
            }
        }

        quitting.store(true, Ordering::SeqCst);
        let _ = slint::quit_event_loop();
    });
}

fn main() -> Result<()> {
    let start_minimized_cli = std::env::args().any(|arg| arg == "--minimized" || arg == "-m");

    let paths = AppPaths::from_env()?;
    paths.ensure_dirs()?;

    let _log_guard = init_logging(&paths.logs_dir);
    info!("--- Rclone Manager Starting ---");

    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .context("Failed to initialize Tokio runtime")?;

    let Some((_instance_guard, instance_rx)) =
        rt.block_on(single_instance::acquire_or_notify(SINGLE_INSTANCE_ID))?
    else {
        info!("Another instance is already running; sent SHOW signal and exiting.");
        return Ok(());
    };

    let settings_mgr = match SettingsManager::load_or_migrate(
        paths.settings_file(),
        paths.default_mount_dir.clone(),
        Some(Path::new("settings.json")),
    ) {
        Ok(mgr) => mgr,
        Err(err) => {
            error!("Failed to initialize settings manager: {err}");
            return Err(err);
        }
    };

    let sync_mgr = match SyncManager::load_or_migrate(
        paths.sync_tasks_file(),
        Some(Path::new("sync_tasks.json")),
    ) {
        Ok(mgr) => mgr,
        Err(err) => {
            error!("Failed to initialize sync manager: {err}");
            return Err(err);
        }
    };

    let start_minimized = start_minimized_cli || settings_mgr.get_start_minimized();
    let initial_mount_dir = settings_mgr.get_mount_dir().to_path_buf();

    let secrets = Arc::new(SecretManager::system());
    let rc_pass = secrets.get_or_create_rc_pass();

    let mut process_manager = RcloneProcessManager::new(
        RC_DEFAULT_ADDR,
        RC_DEFAULT_USER,
        &rc_pass,
        paths.rclone_conf.clone(),
        paths.logs_dir.clone(),
    );

    if let Err(err) = rt.block_on(process_manager.start_daemon()) {
        warn!("Could not start rclone rcd daemon during startup: {err}");
    }

    let mut mount_manager = MountManager::new(
        initial_mount_dir,
        paths.vfs_cache_dir.clone(),
        paths.rclone_conf.clone(),
    );
    // Clean any stale/zombie FUSE mounts on startup (resilience requirement)
    mount_manager.cleanup_all();

    let client = RcloneClient::new(
        &format!("http://{RC_DEFAULT_ADDR}"),
        RC_DEFAULT_USER,
        &rc_pass,
    );
    let autostart = Arc::new(AutostartManager::from_env()?);

    let (tray_tx, tray_rx) = mpsc::unbounded_channel::<TrayAction>();
    let _tray_handle = rt.block_on(spawn_tray(tray_tx));

    let controller = Arc::new(AppController::new(
        paths,
        client,
        secrets,
        Arc::new(Mutex::new(settings_mgr)),
        Arc::new(Mutex::new(mount_manager)),
        Arc::new(Mutex::new(sync_mgr)),
        autostart,
        rt.handle().clone(),
    ));

    spawn_signal_handler(rt.handle(), Arc::clone(&controller.quitting));

    let window = AppWindow::new().context("Failed to create Slint AppWindow")?;
    controller.bind_window(&window, tray_rx, instance_rx);

    if !start_minimized {
        window.show().context("Failed to show main window")?;
    } else {
        info!("Starting minimized to system tray");
        // On Wayland/Winit, showing then immediately hiding transitions the adapter
        // to Suspended cleanly so later tray/IPC show() calls create a mapped surface.
        let weak = window.as_weak();
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(win) = weak.upgrade() {
                let _ = win.show();
                let _ = win.hide();
            }
        });
    }

    slint::run_event_loop_until_quit().context("Slint event loop error")?;

    info!("Shutting down Rclone Manager...");
    rt.block_on(async {
        controller.shutdown().await;
        if let Err(err) = process_manager.stop_daemon().await {
            warn!("Error stopping rclone rcd daemon: {err}");
        }
    });

    info!("Rclone Manager exited cleanly.");
    Ok(())
}
