use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::json;
use slint::{CloseRequestResponse, ComponentHandle, ModelRc, SharedString, VecModel};
use tokio::process::Command;
use tokio::runtime::Handle;
use tokio::sync::{Mutex, mpsc};
use tokio::task::JoinHandle;
use tokio::time::sleep;
use tracing::{debug, error, info, warn};

use crate::core::autostart_manager::AutostartManager;
use crate::core::config::{AppPaths, augmented_path_env, resolve_binary};
use crate::core::mount_manager::{MountManager, MountOptions};
use crate::core::notifications::{UrgencyLevel, send_notification};
use crate::core::rclone_client::{RcloneClient, authorize_drive, format_bytes};
use crate::core::secret_manager::{KeyringSecretStore, SecretManager};
use crate::core::settings_manager::SettingsManager;
use crate::core::single_instance::InstanceCommand;
use crate::core::sync_manager::SyncManager;
use crate::core::sync_worker::{SyncEvent, spawn_sync_process, validate_and_build_sync_args};
use crate::ui::tray::TrayAction;
use crate::ui::{ActivityItemData, AppWindow, RemoteCardData, SyncTaskData};

/// Shared runtime state connecting Slint callbacks and background Tokio workers.
#[derive(Clone)]
pub struct AppController {
    pub paths: AppPaths,
    pub client: RcloneClient,
    pub secrets: Arc<SecretManager<KeyringSecretStore>>,
    pub settings: Arc<Mutex<SettingsManager>>,
    pub mounts: Arc<Mutex<MountManager>>,
    pub sync_manager: Arc<Mutex<SyncManager>>,
    pub autostart: Arc<AutostartManager>,
    pub runtime: Handle,
    pub quitting: Arc<AtomicBool>,
    initial_auto_mount_done: Arc<AtomicBool>,
    reconnecting: Arc<Mutex<HashMap<String, String>>>,
    task_logs: Arc<Mutex<HashMap<u32, Vec<String>>>>,
    active_sync_tasks: Arc<Mutex<HashMap<u32, JoinHandle<()>>>>,
    activity_history: Arc<Mutex<Vec<ActivityRecord>>>,
    http_google: reqwest::Client,
}

#[derive(Debug, Clone)]
struct ActivityRecord {
    name: String,
    item_type: String,
    size: String,
    status: String,
    progress: f32,
    timestamp: String,
}

impl AppController {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        paths: AppPaths,
        client: RcloneClient,
        secrets: Arc<SecretManager<KeyringSecretStore>>,
        settings: Arc<Mutex<SettingsManager>>,
        mounts: Arc<Mutex<MountManager>>,
        sync_manager: Arc<Mutex<SyncManager>>,
        autostart: Arc<AutostartManager>,
        runtime: Handle,
    ) -> Self {
        let http_google = reqwest::Client::builder()
            .timeout(Duration::from_secs(4))
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());

        Self {
            paths,
            client,
            secrets,
            settings,
            mounts,
            sync_manager,
            autostart,
            runtime,
            quitting: Arc::new(AtomicBool::new(false)),
            initial_auto_mount_done: Arc::new(AtomicBool::new(false)),
            reconnecting: Arc::new(Mutex::new(HashMap::new())),
            task_logs: Arc::new(Mutex::new(HashMap::new())),
            active_sync_tasks: Arc::new(Mutex::new(HashMap::new())),
            activity_history: Arc::new(Mutex::new(Vec::new())),
            http_google,
        }
    }

    /// Binds all Slint callbacks, initial model state, and background event listeners.
    pub fn bind_window(
        self: &Arc<Self>,
        window: &AppWindow,
        mut tray_rx: mpsc::UnboundedReceiver<TrayAction>,
        mut instance_rx: mpsc::Receiver<InstanceCommand>,
    ) {
        let weak = window.as_weak();

        // Populate initial synchronous UI state
        self.runtime.block_on(async {
            self.sync_settings_to_ui(window).await;
            self.sync_tasks_to_ui(window).await;
        });

        // Window close minimizes to tray unless quitting explicitly
        window.window().on_close_requested({
            let quitting = Arc::clone(&self.quitting);
            move || {
                if quitting.load(Ordering::SeqCst) {
                    CloseRequestResponse::HideWindow
                } else {
                    info!("Hiding main window to system tray");
                    CloseRequestResponse::HideWindow
                }
            }
        });

        // Refresh remotes
        window.on_refresh_remotes({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move || {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.refresh_remotes(&weak).await;
                });
            }
        });

        // Mount remote
        window.on_mount_remote({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |remote_name, read_only, network_mode| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let name = remote_name.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.mount_remote(
                        &weak,
                        &name,
                        MountOptions {
                            read_only,
                            network_mode,
                        },
                        false,
                    )
                    .await;
                });
            }
        });

        // Unmount remote
        window.on_unmount_remote({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |remote_name| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let name = remote_name.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.unmount_remote(&weak, &name).await;
                });
            }
        });

        // Open mount folder in Dolphin/file manager
        window.on_open_mount({
            let ctrl = Arc::clone(self);
            move |remote_name| {
                let ctrl = Arc::clone(&ctrl);
                let name = remote_name.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    let mount_point = {
                        let mounts = ctrl.mounts.lock().await;
                        mounts.get_mount_point(&name)
                    };
                    let _ = Command::new(resolve_binary("xdg-open"))
                        .arg(&mount_point)
                        .env("PATH", augmented_path_env())
                        .stdout(Stdio::null())
                        .stderr(Stdio::null())
                        .spawn();
                });
            }
        });

        // Reconnect remote with stored keyring credentials
        window.on_reconnect_remote({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |remote_name| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let name = remote_name.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.reconnect_remote(&weak, &name).await;
                });
            }
        });

        // Delete remote
        window.on_delete_remote({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |remote_name| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let name = remote_name.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.delete_remote(&weak, &name).await;
                });
            }
        });

        // Wizard: Create Drive remote
        window.on_create_drive_remote({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |name, client_id, client_secret, auto_mount| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let name = name.to_string();
                let cid = client_id.to_string();
                let secret = client_secret.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.create_drive_remote(&weak, name, cid, secret, auto_mount)
                        .await;
                });
            }
        });

        // Wizard: Clear keyring credentials
        window.on_clear_wizard_credentials({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move || {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.delete_google_credentials(&weak).await;
                });
            }
        });

        // Settings: Run on startup
        window.on_set_run_on_startup({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |enabled| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    let res = if enabled {
                        let exe = std::env::current_exe()
                            .unwrap_or_else(|_| PathBuf::from("rclone-manager"));
                        ctrl.autostart.enable(&exe)
                    } else {
                        ctrl.autostart.disable()
                    };
                    if let Err(err) = res {
                        ctrl.set_banner(&weak, format!("Autostart error: {err}"));
                    }
                    let enabled_now = ctrl.autostart.is_enabled();
                    let _ = slint::invoke_from_event_loop({
                        let weak = weak.clone();
                        move || {
                            if let Some(win) = weak.upgrade() {
                                win.set_run_on_startup(enabled_now);
                            }
                        }
                    });
                });
            }
        });

        // Settings: Start minimized
        window.on_set_start_minimized({
            let ctrl = Arc::clone(self);
            move |enabled| {
                let ctrl = Arc::clone(&ctrl);
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    let mut settings = ctrl.settings.lock().await;
                    if let Err(err) = settings.set_start_minimized(enabled) {
                        error!("Failed to save start_minimized: {err}");
                    }
                });
            }
        });

        // Settings: Browse mount root
        window.on_browse_mount_dir({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move || {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    if let Some(chosen) = pick_directory("Select Mount Root Directory").await {
                        let path_str = chosen.to_string_lossy().into_owned();
                        let _ = slint::invoke_from_event_loop(move || {
                            if let Some(win) = weak.upgrade() {
                                win.set_mount_dir_text(path_str.into());
                            }
                        });
                    }
                });
            }
        });

        // Settings: Save mount root
        window.on_save_mount_dir({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |path_str| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let raw = path_str.trim().to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    let new_dir = if raw.is_empty() {
                        None
                    } else {
                        Some(PathBuf::from(&raw))
                    };
                    let effective = {
                        let mut settings = ctrl.settings.lock().await;
                        if let Err(err) = settings.set_mount_dir(new_dir) {
                            ctrl.set_banner(&weak, format!("Failed saving mount_dir: {err}"));
                            return;
                        }
                        settings.get_mount_dir().to_path_buf()
                    };
                    if let Err(err) = std::fs::create_dir_all(&effective) {
                        ctrl.set_banner(&weak, format!("Could not create mount dir: {err}"));
                        return;
                    }
                    {
                        let mut mounts = ctrl.mounts.lock().await;
                        mounts.set_mount_root(effective.clone());
                    }
                    ctrl.set_banner(
                        &weak,
                        format!("Mount directory updated to {}", effective.display()),
                    );
                    ctrl.refresh_remotes(&weak).await;
                });
            }
        });

        // Settings: Save Google credentials + auto-push
        window.on_save_google_credentials({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |client_id, client_secret| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let cid = client_id.to_string();
                let secret = client_secret.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.save_google_credentials(&weak, &cid, &secret).await;
                });
            }
        });

        // Settings: Delete Google credentials
        window.on_delete_google_credentials({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move || {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    ctrl.delete_google_credentials(&weak).await;
                });
            }
        });

        // Settings: Toggle auto-mount per remote
        window.on_toggle_auto_mount({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |remote_name, enabled| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let name = remote_name.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    {
                        let mut settings = ctrl.settings.lock().await;
                        if let Err(err) = settings.set_auto_mount(&name, enabled) {
                            ctrl.set_banner(&weak, format!("Failed saving auto-mount: {err}"));
                        }
                    }
                    ctrl.refresh_remotes(&weak).await;
                });
            }
        });

        // Settings: Set sync strategy per remote
        window.on_set_sync_strategy({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |remote_name, strategy| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let name = remote_name.to_string();
                let strat = strategy.to_string();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    {
                        let mut settings = ctrl.settings.lock().await;
                        if let Err(err) = settings.set_sync_strategy(&name, &strat) {
                            ctrl.set_banner(&weak, format!("Failed saving strategy: {err}"));
                        }
                    }
                    ctrl.refresh_remotes(&weak).await;
                });
            }
        });

        // Sync: Browse local folder
        window.on_browse_sync_folder({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move || {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    if let Some(chosen) = pick_directory("Select Local Folder").await {
                        let path_str = chosen.to_string_lossy().into_owned();
                        let _ = slint::invoke_from_event_loop(move || {
                            if let Some(win) = weak.upgrade() {
                                win.set_sync_browse_path(path_str.into());
                            }
                        });
                    }
                });
            }
        });

        // Sync: Add task
        window.on_add_sync_task({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |name, local_path, remote_name, remote_path, strategy| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let (name, local, rname, rpath, strat) = (
                    name.to_string(),
                    local_path.to_string(),
                    remote_name.to_string(),
                    remote_path.to_string(),
                    strategy.to_string(),
                );
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    {
                        let mut sync_mgr = ctrl.sync_manager.lock().await;
                        if let Err(err) = sync_mgr.add_task(&name, &local, &rpath, &rname, &strat) {
                            ctrl.set_banner(&weak, format!("Failed adding task: {err}"));
                        }
                    }
                    ctrl.push_sync_tasks_to_ui(&weak).await;
                });
            }
        });

        // Sync: Update task
        window.on_update_sync_task({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |id, name, local_path, remote_name, remote_path, strategy| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let (name, local, rname, rpath, strat) = (
                    name.to_string(),
                    local_path.to_string(),
                    remote_name.to_string(),
                    remote_path.to_string(),
                    strategy.to_string(),
                );
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    if let Ok(task_id) = u32::try_from(id) {
                        let mut sync_mgr = ctrl.sync_manager.lock().await;
                        if let Err(err) =
                            sync_mgr.update_task(task_id, &name, &local, &rpath, &rname, &strat)
                        {
                            ctrl.set_banner(&weak, format!("Failed updating task: {err}"));
                        }
                    }
                    ctrl.push_sync_tasks_to_ui(&weak).await;
                });
            }
        });

        // Sync: Remove task
        window.on_remove_sync_task({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |id| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let rt = ctrl.runtime.clone();
                rt.spawn(async move {
                    if let Ok(task_id) = u32::try_from(id) {
                        if let Some(handle) = ctrl.active_sync_tasks.lock().await.remove(&task_id) {
                            handle.abort();
                        }
                        let mut sync_mgr = ctrl.sync_manager.lock().await;
                        if let Err(err) = sync_mgr.remove_task(task_id) {
                            ctrl.set_banner(&weak, format!("Failed removing task: {err}"));
                        }
                    }
                    ctrl.push_sync_tasks_to_ui(&weak).await;
                });
            }
        });

        // Sync: Run or simulate task
        window.on_run_sync_task({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |id, dry_run| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                if let Ok(task_id) = u32::try_from(id) {
                    let rt = ctrl.runtime.clone();
                    rt.spawn(async move {
                        ctrl.run_sync_task(&weak, task_id, false, dry_run).await;
                    });
                }
            }
        });

        // Sync: Open task log modal
        window.on_select_log_task({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            move |id, task_name| {
                let ctrl = Arc::clone(&ctrl);
                let weak = weak.clone();
                let tname = task_name.to_string();
                if let Ok(task_id) = u32::try_from(id) {
                    let rt = ctrl.runtime.clone();
                    rt.spawn(async move {
                        let joined = ctrl
                            .task_logs
                            .lock()
                            .await
                            .get(&task_id)
                            .map(|lines| lines.join("\n"))
                            .unwrap_or_default();
                        let _ = slint::invoke_from_event_loop(move || {
                            if let Some(win) = weak.upgrade() {
                                win.set_active_log_task_id(id);
                                win.set_active_log_task_name(tname.into());
                                win.set_active_log_text(joined.into());
                            }
                        });
                    });
                }
            }
        });

        // Initial remote load (with brief daemon warm-up retry)
        self.runtime.spawn({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            async move {
                for _ in 0..8 {
                    if ctrl.quitting.load(Ordering::SeqCst) {
                        return;
                    }
                    if ctrl.client.noop().await.unwrap_or(false) {
                        break;
                    }
                    sleep(Duration::from_millis(400)).await;
                }
                ctrl.refresh_remotes(&weak).await;
            }
        });

        // Background activity monitor polling (every 2s)
        self.runtime.spawn({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            async move {
                while !ctrl.quitting.load(Ordering::SeqCst) {
                    ctrl.poll_core_stats(&weak).await;
                    sleep(Duration::from_secs(2)).await;
                }
            }
        });

        // Tray & Single-Instance wakeup listener
        self.runtime.spawn({
            let ctrl = Arc::clone(self);
            let weak = weak.clone();
            async move {
                loop {
                    tokio::select! {
                        Some(action) = tray_rx.recv() => {
                            match action {
                                TrayAction::Show => show_window(&weak),
                                TrayAction::Hide => hide_window(&weak),
                                TrayAction::Quit => {
                                    ctrl.quitting.store(true, Ordering::SeqCst);
                                    let _ = slint::quit_event_loop();
                                    break;
                                }
                            }
                        }
                        Some(cmd) = instance_rx.recv() => {
                            match cmd {
                                InstanceCommand::Show => show_window(&weak),
                            }
                        }
                        else => break,
                    }
                }
            }
        });
    }

    /// Aborts active sync tasks and cleans up all managed FUSE mounts.
    pub async fn shutdown(&self) {
        self.quitting.store(true, Ordering::SeqCst);

        let mut tasks = self.active_sync_tasks.lock().await;
        for (_, handle) in tasks.drain() {
            handle.abort();
        }
        drop(tasks);

        let mut mounts = self.mounts.lock().await;
        mounts.cleanup_all();
    }

    async fn sync_settings_to_ui(&self, window: &AppWindow) {
        let (mount_dir, start_min) = {
            let settings = self.settings.lock().await;
            (
                settings.get_mount_dir().to_string_lossy().into_owned(),
                settings.get_start_minimized(),
            )
        };
        let creds = self.secrets.get_google_credentials();
        let has_creds = creds.is_some();
        let (cid, secret) = match creds {
            Some(c) => (c.client_id, c.client_secret),
            None => (String::new(), String::new()),
        };

        window.set_run_on_startup(self.autostart.is_enabled());
        window.set_start_minimized(start_min);
        window.set_mount_dir_text(mount_dir.into());
        window.set_has_google_credentials(has_creds);
        window.set_wizard_client_id(cid.into());
        window.set_wizard_client_secret(secret.into());
    }

    async fn sync_tasks_to_ui(&self, window: &AppWindow) {
        let tasks = {
            let mgr = self.sync_manager.lock().await;
            mgr.get_tasks().to_vec()
        };
        let ui_tasks: Vec<SyncTaskData> = tasks
            .into_iter()
            .map(|t| SyncTaskData {
                id: t.id as i32,
                name: t.name.into(),
                local_path: t.local_path.into(),
                remote_name: t.remote_name.into(),
                remote_path: t.remote_path.into(),
                strategy: t.strategy.into(),
                last_sync: t.last_sync.into(),
                status: t.status.into(),
            })
            .collect();
        window.set_sync_tasks(ModelRc::new(VecModel::from(ui_tasks)));
    }

    async fn push_sync_tasks_to_ui(&self, weak: &slint::Weak<AppWindow>) {
        let tasks = {
            let mgr = self.sync_manager.lock().await;
            mgr.get_tasks().to_vec()
        };
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    let ui_tasks: Vec<SyncTaskData> = tasks
                        .into_iter()
                        .map(|t| SyncTaskData {
                            id: t.id as i32,
                            name: t.name.into(),
                            local_path: t.local_path.into(),
                            remote_name: t.remote_name.into(),
                            remote_path: t.remote_path.into(),
                            strategy: t.strategy.into(),
                            last_sync: t.last_sync.into(),
                            status: t.status.into(),
                        })
                        .collect();
                    win.set_sync_tasks(ModelRc::new(VecModel::from(ui_tasks)));
                }
            }
        });
    }

    fn set_banner(&self, weak: &slint::Weak<AppWindow>, msg: String) {
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    win.set_status_banner(msg.into());
                }
            }
        });
    }

    pub async fn refresh_remotes(self: &Arc<Self>, weak: &slint::Weak<AppWindow>) {
        let Some((remote_names, auto_mount_targets)) = self.refresh_remotes_cards(weak).await
        else {
            return;
        };

        // Silent auto-mount once remotes have loaded for the first time
        if !remote_names.is_empty() && !self.initial_auto_mount_done.swap(true, Ordering::SeqCst) {
            for target in auto_mount_targets {
                let ctrl = Arc::clone(self);
                let weak = weak.clone();
                self.runtime.spawn(async move {
                    ctrl.mount_remote(&weak, &target, MountOptions::default(), true)
                        .await;
                });
            }
        }
    }

    async fn refresh_remotes_cards(
        &self,
        weak: &slint::Weak<AppWindow>,
    ) -> Option<(Vec<String>, Vec<String>)> {
        let remote_names = match self.client.list_remotes().await {
            Ok(list) => list,
            Err(err) => {
                debug!("Could not list remotes from rclone RC yet: {err}");
                return None;
            }
        };

        let active_mounts = self.client.list_mounts().await.unwrap_or_default();
        let config_dump = self.client.config_dump().await.unwrap_or_default();
        let reconnect_map = self.reconnecting.lock().await.clone();

        let mut cards = Vec::with_capacity(remote_names.len());
        let mut auto_mount_targets = Vec::new();

        for name in &remote_names {
            let fs_str = format!("{name}:");
            let mount_point = {
                let mounts = self.mounts.lock().await;
                mounts.get_mount_point(name)
            };

            let is_mounted_api = active_mounts
                .iter()
                .any(|m| m.fs.contains(&fs_str) || m.fs.contains(name));
            let is_mounted_sys = MountManager::is_mounted_system(&mount_point);
            let is_mounted = is_mounted_api || is_mounted_sys;

            let remote_type = config_dump
                .get(name)
                .and_then(|v| v.get("type"))
                .and_then(|v| v.as_str())
                .unwrap_or("Remote")
                .to_string();

            let mut detail = format!(
                "{remote_type} ({})",
                if is_mounted { "Active" } else { "Idle" }
            );

            if remote_type == "drive"
                && let Some(token_str) = config_dump
                    .get(name)
                    .and_then(|v| v.get("token"))
                    .and_then(|v| v.as_str())
                && let Some(email) = self.try_fetch_google_email(token_str).await
            {
                detail = email;
            }

            let mut quota_text = String::new();
            let mut storage_percent = 0.0f32;
            if let Ok(about) = self.client.about(&fs_str).await
                && let (Some(total), Some(used)) = (about.total, about.used)
            {
                quota_text = format!("{} / {}", format_bytes(used), format_bytes(total));
                storage_percent = if total > 0 {
                    (used as f64 / total as f64) as f32
                } else {
                    0.0
                };
            }

            let (strategy, auto_mount) = {
                let settings = self.settings.lock().await;
                (
                    settings.get_sync_strategy(name).to_string(),
                    settings.is_auto_mount_enabled(name),
                )
            };

            if auto_mount && !is_mounted {
                auto_mount_targets.push(name.clone());
            }

            let reconnect_status = reconnect_map.get(name).cloned().unwrap_or_default();
            let is_reconnecting = reconnect_status.starts_with("Reconnecting")
                || reconnect_status.starts_with("Updating")
                || reconnect_status.starts_with("🔐");

            cards.push((
                name.clone(),
                format!("{name} ({remote_type})"),
                detail,
                is_mounted,
                quota_text,
                storage_percent,
                strategy,
                auto_mount,
                reconnect_status,
                is_reconnecting,
            ));
        }

        let names_for_ui = remote_names.clone();
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    let ui_cards: Vec<RemoteCardData> = cards
                        .into_iter()
                        .map(
                            |(
                                name,
                                display,
                                detail,
                                is_mounted,
                                quota_text,
                                storage_percent,
                                sync_strategy,
                                auto_mount,
                                reconnect_status,
                                is_reconnecting,
                            )| RemoteCardData {
                                name: name.into(),
                                display: display.into(),
                                detail: detail.into(),
                                is_mounted,
                                quota_text: quota_text.into(),
                                storage_percent,
                                sync_strategy: sync_strategy.into(),
                                auto_mount,
                                reconnect_status: reconnect_status.into(),
                                is_reconnecting,
                            },
                        )
                        .collect();

                    let ui_names: Vec<SharedString> =
                        names_for_ui.into_iter().map(Into::into).collect();

                    win.set_remotes(ModelRc::new(VecModel::from(ui_cards)));
                    win.set_remote_names(ModelRc::new(VecModel::from(ui_names)));
                }
            }
        });

        // Silent auto-mount return values (handled by refresh_remotes)
        Some((remote_names, auto_mount_targets))
    }

    async fn try_fetch_google_email(&self, token_str: &str) -> Option<String> {
        let token_val: serde_json::Value = serde_json::from_str(token_str).ok()?;
        let access_token = token_val.get("access_token")?.as_str()?;

        let resp = self
            .http_google
            .get("https://www.googleapis.com/drive/v3/about?fields=user")
            .bearer_auth(access_token)
            .send()
            .await
            .ok()?;

        if !resp.status().is_success() {
            return None;
        }
        let body: serde_json::Value = resp.json().await.ok()?;
        body.get("user")?
            .get("emailAddress")?
            .as_str()
            .map(ToString::to_string)
    }

    async fn mount_remote(
        self: &Arc<Self>,
        weak: &slint::Weak<AppWindow>,
        remote_name: &str,
        opts: MountOptions,
        silent: bool,
    ) {
        let result = {
            let mut mounts = self.mounts.lock().await;
            mounts.mount_remote(remote_name, opts).await
        };

        match result {
            Ok(res) if res.success => {
                if !res.already_mounted && !silent {
                    send_notification(
                        "Drive Mounted",
                        &format!("{remote_name} mounted at {}", res.mount_point.display()),
                        UrgencyLevel::Normal,
                    );
                }
                self.refresh_remotes_cards(weak).await;
            }
            Ok(res) => {
                let err = res
                    .error
                    .unwrap_or_else(|| "Unknown mount error".to_string());
                self.set_banner(weak, format!("Mount failed for {remote_name}: {err}"));
                send_notification(
                    "Mount Failed",
                    &format!("Could not mount {remote_name}: {err}"),
                    UrgencyLevel::Critical,
                );
            }
            Err(err) => {
                self.set_banner(weak, format!("Mount error for {remote_name}: {err}"));
            }
        }
    }

    async fn unmount_remote(self: &Arc<Self>, weak: &slint::Weak<AppWindow>, remote_name: &str) {
        let ok = {
            let mut mounts = self.mounts.lock().await;
            mounts.unmount_remote(remote_name).await
        };
        if ok {
            send_notification(
                "Drive Unmounted",
                &format!("{remote_name} unmounted cleanly"),
                UrgencyLevel::Low,
            );
        } else {
            self.set_banner(weak, format!("Unmount failed for {remote_name}"));
        }
        self.refresh_remotes(weak).await;
    }

    async fn delete_remote(self: &Arc<Self>, weak: &slint::Weak<AppWindow>, remote_name: &str) {
        let _ = self.unmount_remote(weak, remote_name).await;
        {
            let mut settings = self.settings.lock().await;
            let _ = settings.remove_auto_mount(remote_name);
        }
        if let Err(err) = self.client.config_delete(remote_name).await {
            warn!("RC config/delete failed ({err}), falling back to rclone CLI");
            let _ = Command::new(resolve_binary("rclone"))
                .args(["config", "delete", remote_name])
                .env("PATH", augmented_path_env())
                .status()
                .await;
        }
        self.refresh_remotes(weak).await;
    }

    async fn set_reconnect_status(
        self: &Arc<Self>,
        weak: &slint::Weak<AppWindow>,
        remote_name: &str,
        status: &str,
    ) {
        {
            let mut map = self.reconnecting.lock().await;
            if status.is_empty() {
                map.remove(remote_name);
            } else {
                map.insert(remote_name.to_string(), status.to_string());
            }
        }
        self.refresh_remotes(weak).await;
    }

    async fn reconnect_remote(self: &Arc<Self>, weak: &slint::Weak<AppWindow>, remote_name: &str) {
        let Some(creds) = self.secrets.get_google_credentials() else {
            self.set_reconnect_status(
                weak,
                remote_name,
                "❌ No credentials in keyring. Save them in Settings first.",
            )
            .await;
            return;
        };

        self.set_reconnect_status(weak, remote_name, "Updating credentials...")
            .await;

        let update_res = self
            .client
            .config_update(
                remote_name,
                &json!({
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                }),
                Some(&json!({ "config_refresh_token": false })),
            )
            .await;

        if let Err(err) = update_res {
            self.set_reconnect_status(
                weak,
                remote_name,
                &format!("❌ Config update failed: {err}"),
            )
            .await;
            return;
        }

        self.set_reconnect_status(
            weak,
            remote_name,
            "🔐 Opening browser for Google authorization...",
        )
        .await;

        let token_json =
            match authorize_drive(Some(&creds.client_id), Some(&creds.client_secret), 120).await {
                Ok(token) => token,
                Err(err) => {
                    self.set_reconnect_status(weak, remote_name, &format!("❌ {err}"))
                        .await;
                    return;
                }
            };

        if let Err(err) = self
            .client
            .config_update(remote_name, &json!({ "token": token_json }), None)
            .await
        {
            self.set_reconnect_status(weak, remote_name, &format!("❌ Token update failed: {err}"))
                .await;
            return;
        }

        self.set_reconnect_status(weak, remote_name, "✅ Reconnected successfully!")
            .await;
        send_notification(
            "Drive Reconnected",
            &format!("{remote_name} authorized successfully"),
            UrgencyLevel::Normal,
        );
    }

    async fn create_drive_remote(
        self: &Arc<Self>,
        weak: &slint::Weak<AppWindow>,
        name: String,
        client_id: String,
        client_secret: String,
        auto_mount: bool,
    ) {
        if name.trim().is_empty() {
            self.set_wizard_state(weak, false, "Remote name is required.");
            return;
        }

        if auto_mount {
            let mut settings = self.settings.lock().await;
            let _ = settings.add_auto_mount(&name);
            if !self.autostart.is_enabled() {
                let exe =
                    std::env::current_exe().unwrap_or_else(|_| PathBuf::from("rclone-manager"));
                let _ = self.autostart.enable(&exe);
            }
        }

        self.set_wizard_state(
            weak,
            true,
            "🔐 Launching browser for Google authorization...",
        );

        let cid_opt = (!client_id.trim().is_empty()).then_some(client_id.trim());
        let secret_opt = (!client_secret.trim().is_empty()).then_some(client_secret.trim());

        let token_json = match authorize_drive(cid_opt, secret_opt, 120).await {
            Ok(tok) => tok,
            Err(err) => {
                self.set_wizard_state(weak, false, &format!("❌ {err}"));
                return;
            }
        };

        self.set_wizard_state(weak, true, "Saving remote configuration...");

        let mut params = json!({ "token": token_json });
        if let Some(cid) = cid_opt {
            params["client_id"] = json!(cid);
        }
        if let Some(secret) = secret_opt {
            params["client_secret"] = json!(secret);
        }

        if let Err(err) = self.client.config_create(&name, "drive", &params).await {
            self.set_wizard_state(weak, false, &format!("❌ Failed creating remote: {err}"));
            return;
        }

        if let (Some(cid), Some(secret)) = (cid_opt, secret_opt) {
            if let Err(err) = self.secrets.save_google_credentials(cid, secret) {
                warn!("Could not persist Google credentials in keyring: {err}");
            } else {
                self.push_keyring_ui_state(weak).await;
            }
        }

        self.set_wizard_state(weak, false, "✅ Drive created successfully!");
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    win.set_current_page("dashboard".into());
                }
            }
        });
        self.refresh_remotes(weak).await;
    }

    fn set_wizard_state(&self, weak: &slint::Weak<AppWindow>, busy: bool, msg: &str) {
        let msg_owned = msg.to_string();
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    win.set_wizard_busy(busy);
                    win.set_wizard_status_text(msg_owned.into());
                }
            }
        });
    }

    async fn save_google_credentials(
        self: &Arc<Self>,
        weak: &slint::Weak<AppWindow>,
        client_id: &str,
        client_secret: &str,
    ) {
        self.set_keyring_ui_status(weak, true, "Saving credentials to system keyring...");

        if let Err(err) = self
            .secrets
            .save_google_credentials(client_id, client_secret)
        {
            self.set_keyring_ui_status(weak, false, &format!("❌ Keyring error: {err}"));
            return;
        }

        self.push_keyring_ui_state(weak).await;

        // Auto-push credentials to all existing Drive remotes
        let mut updated_count = 0usize;
        if let Ok(dump) = self.client.config_dump().await {
            for (name, cfg) in dump {
                if cfg.get("type").and_then(|v| v.as_str()) == Some("drive")
                    && self
                        .client
                        .config_update(
                            &name,
                            &json!({
                                "client_id": client_id,
                                "client_secret": client_secret,
                            }),
                            Some(&json!({ "config_refresh_token": false })),
                        )
                        .await
                        .is_ok()
                {
                    updated_count += 1;
                }
            }
        }

        self.set_keyring_ui_status(
            weak,
            false,
            &format!("✅ Credentials saved and pushed to {updated_count} Drive remote(s)."),
        );
    }

    async fn delete_google_credentials(self: &Arc<Self>, weak: &slint::Weak<AppWindow>) {
        self.set_keyring_ui_status(weak, true, "Removing credentials from keyring...");
        if let Err(err) = self.secrets.delete_google_credentials() {
            self.set_keyring_ui_status(weak, false, &format!("❌ Keyring delete failed: {err}"));
            return;
        }
        self.push_keyring_ui_state(weak).await;
        self.set_keyring_ui_status(weak, false, "🗑️ Credentials removed from keyring.");
    }

    async fn push_keyring_ui_state(&self, weak: &slint::Weak<AppWindow>) {
        let creds = self.secrets.get_google_credentials();
        let has_creds = creds.is_some();
        let (cid, secret) = match creds {
            Some(c) => (c.client_id, c.client_secret),
            None => (String::new(), String::new()),
        };
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    win.set_has_google_credentials(has_creds);
                    win.set_wizard_client_id(cid.into());
                    win.set_wizard_client_secret(secret.into());
                }
            }
        });
    }

    fn set_keyring_ui_status(&self, weak: &slint::Weak<AppWindow>, busy: bool, msg: &str) {
        let msg_owned = msg.to_string();
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    win.set_keyring_busy(busy);
                    win.set_keyring_status_text(msg_owned.into());
                }
            }
        });
    }

    async fn run_sync_task(
        self: &Arc<Self>,
        weak: &slint::Weak<AppWindow>,
        task_id: u32,
        force_resync: bool,
        dry_run: bool,
    ) {
        {
            let active = self.active_sync_tasks.lock().await;
            if active.contains_key(&task_id) && !force_resync {
                return;
            }
        }

        let ctrl = Arc::clone(self);
        let weak_clone = weak.clone();
        self.runtime.spawn(async move {
            let mut resync_mode = force_resync;

            loop {
                {
                    let mut active = ctrl.active_sync_tasks.lock().await;
                    if let Some(prev) = active.remove(&task_id) {
                        prev.abort();
                    }
                }

                let task = {
                    let mgr = ctrl.sync_manager.lock().await;
                    mgr.get_tasks().iter().find(|t| t.id == task_id).cloned()
                };
                let Some(task) = task else {
                    return;
                };

                let status_label = match (dry_run, task.strategy.as_str()) {
                    (true, "bisync") => "Simulating: Syncing...",
                    (true, "sync") => "Simulating: Backing up (Up)...",
                    (true, "copy") => "Simulating: Downloading (Down)...",
                    (false, "bisync") if resync_mode => "Resyncing...",
                    (false, "bisync") => "Syncing...",
                    (false, "sync") => "Backing up (Up)...",
                    (false, "copy") => "Downloading (Down)...",
                    _ => "Working...",
                };

                {
                    let mut mgr = ctrl.sync_manager.lock().await;
                    let _ = mgr.update_task_status(task_id, status_label, None);
                }
                ctrl.push_sync_tasks_to_ui(&weak_clone).await;

                let args = match validate_and_build_sync_args(
                    &task,
                    &ctrl.paths.rclone_conf,
                    resync_mode,
                    dry_run,
                ) {
                    Ok(a) => a,
                    Err(err) => {
                        let err_msg = err.to_string();
                        ctrl.append_task_log(&weak_clone, task_id, err_msg.clone())
                            .await;
                        {
                            let mut mgr = ctrl.sync_manager.lock().await;
                            let _ = mgr.update_task_status(task_id, "Error", None);
                        }
                        ctrl.push_sync_tasks_to_ui(&weak_clone).await;
                        send_notification("Sync Warning ⚠️", &err_msg, UrgencyLevel::Critical);
                        return;
                    }
                };

                {
                    let mut logs = ctrl.task_logs.lock().await;
                    let entry = logs.entry(task_id).or_default();
                    entry.clear();
                    if dry_run {
                        entry.push("--- 👁 SIMULATION MODE (DRY-RUN) ---".to_string());
                        entry.push(format!("Strategy: {}", task.strategy));
                        entry.push("No changes will be applied to files.".to_string());
                    } else if resync_mode {
                        entry.push("--- AUTO-RECOVERY: Resyncing... ---".to_string());
                    }
                }
                ctrl.sync_active_log_modal(&weak_clone, task_id).await;

                let (tx, mut rx) = mpsc::channel(64);
                let worker_handle = spawn_sync_process(task_id, resolve_binary("rclone"), args, tx);
                ctrl.active_sync_tasks
                    .lock()
                    .await
                    .insert(task_id, worker_handle);

                let mut needs_resync = false;
                let mut finished_ok = false;
                let mut err_text = None;

                while let Some(event) = rx.recv().await {
                    match event {
                        SyncEvent::LogLine { task_id, line } => {
                            ctrl.record_activity_from_log(&line).await;
                            ctrl.append_task_log(&weak_clone, task_id, line).await;
                        }
                        SyncEvent::NeedsResync { .. } => {
                            needs_resync = true;
                        }
                        SyncEvent::FinishedSuccess { .. } => {
                            finished_ok = true;
                        }
                        SyncEvent::FinishedError { error, .. } => {
                            err_text = Some(error);
                        }
                    }
                }

                ctrl.active_sync_tasks.lock().await.remove(&task_id);

                if finished_ok {
                    let ts = current_utc_hms_timestamp(true);
                    let mut mgr = ctrl.sync_manager.lock().await;
                    let _ = mgr.update_task_status(task_id, "Idle", Some(&ts));
                    drop(mgr);
                    ctrl.push_sync_tasks_to_ui(&weak_clone).await;
                    return;
                }

                if needs_resync && !dry_run && !resync_mode {
                    warn!("Auto-recovering task {task_id} with --resync...");
                    resync_mode = true;
                    continue;
                }

                let err_summary = err_text.unwrap_or_else(|| "Sync failed".to_string());
                error!("Sync failed for task {task_id}: {err_summary}");
                {
                    let mut mgr = ctrl.sync_manager.lock().await;
                    let _ = mgr.update_task_status(task_id, "Error", None);
                }
                ctrl.push_sync_tasks_to_ui(&weak_clone).await;
                send_notification(
                    "Sync Warning ⚠️",
                    &format!("Conflicts/Errors in '{}'. Check Logs.", task.name),
                    UrgencyLevel::Critical,
                );
                return;
            }
        });
    }

    async fn append_task_log(&self, weak: &slint::Weak<AppWindow>, task_id: u32, line: String) {
        {
            let mut logs = self.task_logs.lock().await;
            let entry = logs.entry(task_id).or_default();
            entry.push(line);
            if entry.len() > 500 {
                let overflow = entry.len() - 500;
                entry.drain(0..overflow);
            }
        }
        self.sync_active_log_modal(weak, task_id).await;
    }

    async fn sync_active_log_modal(&self, weak: &slint::Weak<AppWindow>, task_id: u32) {
        let joined = self
            .task_logs
            .lock()
            .await
            .get(&task_id)
            .map(|l| l.join("\n"))
            .unwrap_or_default();

        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade()
                    && win.get_active_log_task_id() == task_id as i32
                {
                    win.set_active_log_text(joined.into());
                }
            }
        });
    }

    async fn record_activity_from_log(&self, line: &str) {
        let status = if line.contains("Copied (new)") || line.contains("Copied (replaced)") {
            "success"
        } else if line.contains("Deleted") {
            "deleted"
        } else if line.contains("Failed to") || line.contains("Error:") {
            "error"
        } else {
            return;
        };

        let parts: Vec<&str> = line.split(':').collect();
        let filename = if parts.len() >= 3 {
            parts[parts.len() - 2].trim().to_string()
        } else {
            return;
        };

        let mut hist = self.activity_history.lock().await;
        if let Some(existing) = hist
            .iter_mut()
            .find(|i| i.name == filename && i.status == "syncing")
        {
            existing.status = status.to_string();
            existing.progress = 100.0;
        } else {
            hist.push(ActivityRecord {
                name: filename,
                item_type: "file".to_string(),
                size: "-".to_string(),
                status: status.to_string(),
                progress: 100.0,
                timestamp: current_utc_hms_timestamp(false),
            });
            if hist.len() > 100 {
                let overflow = hist.len() - 100;
                hist.drain(0..overflow);
            }
        }
    }

    async fn poll_core_stats(&self, weak: &slint::Weak<AppWindow>) {
        let Ok(stats) = self.client.core_stats().await else {
            return;
        };

        let speed_text = format!("{}/s", format_bytes(stats.speed.max(0.0) as u64));
        let bytes_text = format_bytes(stats.bytes);

        let mut hist = self.activity_history.lock().await;
        for active in &stats.transferring {
            if let Some(existing) = hist.iter_mut().find(|i| i.name == active.name) {
                existing.size = format_bytes(active.size);
                existing.status = "syncing".to_string();
                existing.progress = active.percentage as f32;
            } else {
                hist.push(ActivityRecord {
                    name: active.name.clone(),
                    item_type: "file".to_string(),
                    size: format_bytes(active.size),
                    status: "syncing".to_string(),
                    progress: active.percentage as f32,
                    timestamp: current_utc_hms_timestamp(false),
                });
            }
        }

        for done in &stats.transferred {
            let final_status = if done.error.is_empty() {
                "success"
            } else {
                "error"
            };
            if let Some(existing) = hist.iter_mut().find(|i| i.name == done.name) {
                existing.size = format_bytes(done.size);
                existing.status = final_status.to_string();
                existing.progress = 100.0;
            } else {
                hist.push(ActivityRecord {
                    name: done.name.clone(),
                    item_type: "file".to_string(),
                    size: format_bytes(done.size),
                    status: final_status.to_string(),
                    progress: 100.0,
                    timestamp: current_utc_hms_timestamp(false),
                });
            }
        }

        let snapshot: Vec<ActivityRecord> = hist.iter().rev().cloned().collect();
        drop(hist);

        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || {
                if let Some(win) = weak.upgrade() {
                    win.set_global_speed_text(speed_text.into());
                    win.set_global_bytes_text(bytes_text.into());
                    let items: Vec<ActivityItemData> = snapshot
                        .into_iter()
                        .map(|r| ActivityItemData {
                            name: r.name.into(),
                            item_type: r.item_type.into(),
                            size: r.size.into(),
                            status: r.status.into(),
                            progress: r.progress,
                            timestamp: r.timestamp.into(),
                        })
                        .collect();
                    win.set_activity_items(ModelRc::new(VecModel::from(items)));
                }
            }
        });
    }
}

fn show_window(weak: &slint::Weak<AppWindow>) {
    let _ = slint::invoke_from_event_loop({
        let weak = weak.clone();
        move || {
            if let Some(win) = weak.upgrade() {
                let _ = win.show();
                win.window().set_minimized(false);
            }
        }
    });
}

fn hide_window(weak: &slint::Weak<AppWindow>) {
    let _ = slint::invoke_from_event_loop({
        let weak = weak.clone();
        move || {
            if let Some(win) = weak.upgrade() {
                let _ = win.hide();
            }
        }
    });
}

async fn pick_directory(title: &str) -> Option<PathBuf> {
    let kdialog = resolve_binary("kdialog");
    if kdialog.is_absolute()
        && let Ok(out) = Command::new(kdialog)
            .args(["--getexistingdirectory", "--title", title])
            .env("PATH", augmented_path_env())
            .output()
            .await
        && out.status.success()
    {
        let raw = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if !raw.is_empty() {
            return Some(PathBuf::from(raw));
        }
    }

    let zenity = resolve_binary("zenity");
    if zenity.is_absolute()
        && let Ok(out) = Command::new(zenity)
            .args(["--file-selection", "--directory", "--title", title])
            .env("PATH", augmented_path_env())
            .output()
            .await
        && out.status.success()
    {
        let raw = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if !raw.is_empty() {
            return Some(PathBuf::from(raw));
        }
    }

    None
}

fn current_utc_hms_timestamp(include_date: bool) -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let h = (secs % 86_400) / 3600;
    let m = (secs % 3600) / 60;
    let s = secs % 60;
    if include_date {
        // Civil date calculation from Unix days (Howard Hinnant's algorithm)
        let days = (secs / 86_400) as i64;
        let z = days + 719_468;
        let era = z.div_euclid(146_097);
        let doe = z.rem_euclid(146_097) as u64;
        let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
        let y = (yoe as i64) + era * 400;
        let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        let mp = (5 * doy + 2) / 153;
        let d = doy - (153 * mp + 2) / 5 + 1;
        let mo = if mp < 10 { mp + 3 } else { mp - 9 };
        let year = y + i64::from(mo <= 2);
        format!("{year:04}-{mo:02}-{d:02} {h:02}:{m:02}:{s:02} UTC")
    } else {
        format!("{h:02}:{m:02}:{s:02}")
    }
}
