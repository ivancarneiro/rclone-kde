use std::path::Path;

use anyhow::Result;
use tracing::{error, info};
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::{EnvFilter, fmt, layer::SubscriberExt, util::SubscriberInitExt};

use rclone_manager::core::config::{AppPaths, SINGLE_INSTANCE_ID};
use rclone_manager::core::secret_manager::SecretManager;
use rclone_manager::core::settings_manager::SettingsManager;
use rclone_manager::core::single_instance;

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

#[tokio::main]
async fn main() -> Result<()> {
    let paths = AppPaths::from_env()?;
    paths.ensure_dirs()?;

    let _log_guard = init_logging(&paths.logs_dir);
    info!("--- Rclone Manager Starting ---");

    let Some((_instance_guard, _instance_rx)) =
        single_instance::acquire_or_notify(SINGLE_INSTANCE_ID).await?
    else {
        info!("Another instance is already running; sent SHOW signal and exiting.");
        return Ok(());
    };

    let legacy_settings = Path::new("settings.json");
    let settings = match SettingsManager::load_or_migrate(
        paths.settings_file(),
        paths.default_mount_dir.clone(),
        Some(legacy_settings),
    ) {
        Ok(mgr) => mgr,
        Err(err) => {
            error!("Failed to initialize settings manager: {err}");
            return Err(err);
        }
    };

    let secrets = SecretManager::system();
    let _rc_pass = secrets.get_or_create_rc_pass();

    info!(
        config_dir = %paths.config_dir.display(),
        mount_dir = %settings.get_mount_dir().display(),
        has_google_credentials = secrets.has_google_credentials(),
        "Core Phase 1 initialized"
    );

    Ok(())
}
