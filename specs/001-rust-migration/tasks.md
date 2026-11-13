# Tasks: Rclone Manager Rust & Slint Migration

**Input**: Design documents from `/specs/001-rust-migration/`
**Prerequisites**: [spec.md](file:///home/ciex/rclone-kde/specs/001-rust-migration/spec.md), [plan.md](file:///home/ciex/rclone-kde/specs/001-rust-migration/plan.md)

## Phase 1: Core Foundation (US1)

**Goal**: Establecer la base XDG, generación/gestión segura de secretos en Keyring, persistencia/migración de `settings.json` sin KeePassXC, logging rotativo e IPC de instancia única.

- [x] T1.1 Configurar dependencias base de Fase 1 en `Cargo.toml` (`tokio`, `serde`, `serde_json`, `thiserror`, `anyhow`, `tracing`, `tracing-subscriber`, `tracing-appender`, `dirs`, `keyring`) y verificar `cargo audit`.
- [x] T1.2 [P] Implementar `src/core/config.rs` (`AppPaths` XDG puro, constantes `KEYRING_SERVICE = "RcloneKDE"`, `ensure_dirs()`, generador hexadecimal de 16 bytes) con tests unitarios.
- [x] T1.3 [P] Implementar `src/core/secret_manager.rs` (trait `SecretStore`, `KeyringSecretStore`, `InMemorySecretStore`, `GoogleCredentials`, `get_or_create_rc_pass`) con tests unitarios.
- [x] T1.4 Implementar `src/core/settings_manager.rs` (`AppSettings` sin KeePassXC, carga/guardado XDG y migración automática desde `./settings.json` legado) con tests unitarios.
- [x] T1.5 Implementar `src/core/single_instance.rs` (socket Unix abstracto `\0rclone_manager_gna_lock` con comando `"SHOW\n"` y receptor `mpsc`) con test de integración IPC.
- [x] T1.6 Configurar `src/lib.rs`, `src/core/mod.rs` y bootstrap en `src/main.rs` (`tracing-subscriber` + rotación diaria en `~/.cache/rclone-manager/logs`, single-instance, `AppPaths`, `SettingsManager`, `SecretManager`).
- [x] T1.7 Verificar Fase 1 con `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` y commit atómico.

**Checkpoint**: Core Foundation compilando sin warnings y con cobertura de tests unitarios.

---

## Phase 2: Rclone Engine & Managers (US2, US3, US4, US5)

**Goal**: Implementar comunicación híbrida con Rclone (`rclone rcd` vía `reqwest` + subprocesos `tokio::process` con `kill_on_drop`), gestión resiliente de montajes FUSE, persistencia/ejecución de tareas sync, autostart `.desktop` y notificaciones D-Bus.

- [ ] T2.1 Implementar `src/core/rclone_client.rs` (cliente HTTP `reqwest` con BasicAuth, `core/version`, `config/listremotes`, `about`, `core/stats`, `rc/noop`, `config/update` y `authorize` helper) con tests contra mock HTTP.
- [ ] T2.2 Implementar `src/core/process_manager.rs` (arranque/parada de `rclone rcd`, limpieza previa de puerto, pipe de stdout/stderr a log rotativo `rclone-daemon.log`).
- [ ] T2.3 Implementar `src/core/mount_manager.rs` (montaje con flags VFS, `--max-size 1G`, `--read-only`, detección de punto de montaje, `cleanup_zombie` / `cleanup_all` con `fusermount -uz`, y `Drop`).
- [ ] T2.4 Implementar `src/core/sync_manager.rs` (persistencia en `~/.config/rclone-manager/sync_tasks.json` con migración automática de `./sync_tasks.json` si existe) y `src/core/sync_worker.rs` (ejecución `bisync`/`sync`/`copy` con `--max-delete 5`, `--dry-run` y streaming por `mpsc`).
- [ ] T2.5 [P] Implementar `src/core/autostart_manager.rs` (`~/.config/autostart/rclone-gui-manager.desktop` apuntando al binario con `--minimized`) y `src/core/notifications.rs` (`notify-rust`).
- [ ] T2.6 Verificar Fase 2 con `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` y commit atómico.

**Checkpoint**: Todo el backend en Rust completo, probado y desacoplado de la interfaz gráfica.

---

## Phase 3: Slint UI & KDE Tray Integration (US2, US3, US4, US5)

**Goal**: Construir las 5 vistas en Slint con paridad 1:1 de v1.3.2 (sin KeePassXC), integrar `ksni` para System Tray en KDE Plasma/Wayland, conectar el despertar de ventana desde Single-Instance IPC y manejar señales `SIGINT`/`SIGTERM`.

- [ ] T3.1 Añadir `slint` (y `ksni`) en `Cargo.toml`, crear `build.rs` para compilar los archivos `.slint` y verificar `cargo audit`.
- [ ] T3.2 Implementar vistas `.slint`: `main.slint` (ventana `min 700x500`, drawer lateral, títulos dinámicos), `dashboard.slint` y `mount_dialog.slint`.
- [ ] T3.3 Implementar vistas `.slint`: `wizard.slint`, `sync.slint` (con diálogo de creación y logs estilo Matrix), `activity.slint` y `settings.slint` (Keyring CRUD, auto-push, reconnect por remoto, autostart, mount_dir; sin KeePassXC).
- [ ] T3.4 Implementar `src/ui/tray.rs` con `ksni` (`StatusNotifierItem` D-Bus: Show Manager, Hide, Exit) y bucle de eventos Tokio ↔ Slint (`invoke_from_event_loop`).
- [ ] T3.5 Conectar `SingleInstance` (`InstanceCommand::Show`), señales `SIGINT`/`SIGTERM` para `cleanup_all()` al cerrar, y autostart silencioso de `auto_mounts` al iniciar.
- [ ] T3.6 Verificar Fase 3 (`cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, `cargo build --release`), probar ejecución en KDE Plasma/Wayland y actualizar `README.md` / `CHANGELOG.md`.

