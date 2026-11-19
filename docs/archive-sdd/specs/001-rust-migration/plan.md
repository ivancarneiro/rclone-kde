# Implementation Plan: Rclone Manager Rust & Slint Migration

**Branch**: `feature/rust-migration` | **Date**: 2026-11-13 | **Spec**: [spec.md](file:///home/ciex/rclone-kde/specs/001-rust-migration/spec.md)

## Summary

Migrar Rclone Manager (v1.3.2) a una aplicación nativa 100% Rust usando **Slint** como interfaz declarativa, **Tokio + Reqwest** para el motor híbrido asíncrono contra Rclone (`rclone rcd` + subprocesos supervisados), **keyring** compatible con `"RcloneKDE"` bajo KDE Wallet, **ksni** + **notify-rust** para integración D-Bus nativa en KDE Plasma/Wayland, y estándar **XDG puro** con migración automática desde configuraciones heredadas (descartando KeePassXC).

## Technical Context

**Language/Version**: Rust 1.99.1 (Edition 2024, MSRV 1.85+)
**Primary Dependencies**: `tokio`, `reqwest`, `serde`, `serde_json`, `thiserror`, `anyhow`, `tracing`, `tracing-subscriber`, `tracing-appender`, `dirs`, `keyring`, `ksni`, `notify-rust`, `slint`
**Storage**: Archivos JSON XDG (`~/.config/rclone-manager/settings.json`, `sync_tasks.json`), caché VFS y logs en `~/.cache/rclone-manager/`, montajes por defecto en `~/RcloneMounts`, secretos en KDE Wallet (`RcloneKDE`)
**Testing**: `cargo test` (unit tests con traits/mocks de almacenamiento y servidor HTTP mock para RC; tests de integración IPC y FS en `tempfile`/directorios temporales)
**Target Platform**: Linux (KDE Plasma Wayland / X11)
**Project Type**: Desktop application (binario único compilado)
**Constraints**: Zero-Python Policy, Zero-Warnings (`clippy -D warnings`), Ponytail/YAGNI (sin KeePassXC ni abstracciones prematuras), sin `unsafe`

## Constitution Check

- **I. Memory Safety**: Cero `unsafe`; errores tipados con `thiserror` y `anyhow`. Cumple.
- **II. Async Daemon-First**: Todo I/O de red/procesos sobre `tokio` sin bloquear el hilo de UI Slint. Cumple.
- **III. Mount & FUSE Resilience**: Limpieza preventiva al arranque/cierre, señales `SIGINT`/`SIGTERM`, `Drop`, y `~/RcloneMounts` (configurable). Cumple.
- **IV. Desktop Integration**: `ksni`, `notify-rust`, `keyring` (`RcloneKDE`), socket abstracto Unix con comando `"SHOW"`. Cumple.
- **V. Spec-Driven & Test-First**: Especificación, plan y tareas en `specs/001-rust-migration/` con pruebas unitarias por módulo. Cumple.
- **VIII. Ponytail / YAGNI**: Paridad 1:1 con v1.3.2 eliminando KeePassXC; código directo y conciso. Cumple.
- **IX. Zero-Python**: Validado por `.githooks/pre-commit`. Cumple.

## Project Structure

### Documentation (this feature)

```text
specs/001-rust-migration/
├── spec.md              # Especificación funcional y criterios de aceptación
├── plan.md              # Plan arquitectónico por fases (este archivo)
└── tasks.md             # Lista de tareas ejecutables por fase
```

### Source Code (repository root)

```text
src/
├── lib.rs               # Exposición de módulos para tests e integración
├── main.rs              # Bootstrap: logging, single-instance, core init, UI Slint + Tray
├── core/
│   ├── mod.rs
│   ├── config.rs            # AppPaths (XDG), constantes, generador aleatorio de rc_pass
│   ├── secret_manager.rs    # SecretStore trait + KeyringSecretStore ("RcloneKDE")
│   ├── settings_manager.rs  # AppSettings XDG + migración legacy sin KeePassXC
│   ├── single_instance.rs   # Socket Unix abstracto + wakeup "SHOW"
│   ├── rclone_client.rs     # Fase 2: Cliente HTTP asíncrono (reqwest) para rclone rcd
│   ├── process_manager.rs   # Fase 2: Ciclo de vida rclone rcd + rotación de logs
│   ├── mount_manager.rs     # Fase 2: rclone mount supervisado + anti-zombie fusermount -uz
│   ├── sync_manager.rs      # Fase 2: Persistencia XDG sync_tasks.json + migración legacy
│   ├── sync_worker.rs       # Fase 2: rclone bisync/sync/copy con streaming mpsc
│   ├── autostart_manager.rs # Fase 2: ~/.config/autostart/rclone-gui-manager.desktop
│   └── notifications.rs     # Fase 2: notify-rust D-Bus
└── ui/                      # Fase 3: Slint (.slint + viewmodels/controllers + ksni tray)
    ├── mod.rs
    ├── tray.rs
    └── slint/
        ├── main.slint
        ├── dashboard.slint
        ├── wizard.slint
        ├── sync.slint
        ├── activity.slint
        ├── settings.slint
        └── mount_dialog.slint
```

**Structure Decision**: Proyecto único (`rclone-manager`) con separación limpia `core` (lógica asíncrona/sistema independiente de UI y 100% testeable) y `ui` (Slint + Tray).

## Phased Rollout

1. **Fase 1 — Core Foundation**: `Cargo.toml` base, `config.rs`, `secret_manager.rs`, `settings_manager.rs`, `single_instance.rs`, `tracing` en `main.rs` + tests unitarios.
2. **Fase 2 — Rclone Engine & Managers**: `rclone_client.rs`, `process_manager.rs`, `mount_manager.rs`, `sync_manager.rs`, `sync_worker.rs`, `autostart_manager.rs`, `notifications.rs` + tests unitarios/mock.
3. **Fase 3 — Slint UI & KDE Tray Integration**: Vistas `.slint` (paridad 1:1 v1.3.2 sin KeePassXC), puente asíncrono Tokio ↔ Slint (`slint::invoke_from_event_loop`), bandeja `ksni`, manejo de señales `SIGINT`/`SIGTERM` y pruebas end-to-end.
