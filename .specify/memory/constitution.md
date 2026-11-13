# Rclone Manager (Rust Evolution) Constitution

## Core Principles

### I. Memory Safety & Resilient Architecture
El nuevo núcleo en Rust debe garantizar seguridad de memoria en tiempo de compilación y tolerancia a fallos. Se prohíbe el uso de `unsafe` salvo casos estrictamente necesarios e interoperabilidad FFI documentada. Toda operación susceptible de fallo debe estructurarse mediante tipos algebraicos (`Result<T, E>`, `Option<T>`) y manejo explícito de errores (`thiserror`, `anyhow`).

### II. Async Daemon-First & Zero-Blocking Core
La interacción con el daemon Rclone RC (Remote Control) y la red debe ser 100% asíncrona utilizando `tokio` y `reqwest`. Ninguna operación de E/S, sondeo de red o verificación de puntos de montaje debe bloquear el hilo principal o la interfaz de usuario.

### III. Mount & FUSE Resilience (NON-NEGOTIABLE)
El sistema debe gestionar el ciclo de vida de los montajes de forma estricta:
1. Barrido y limpieza preventiva de montajes zombies (`ENOTCONN` / "Transport endpoint not connected") tanto al arranque como al cierre.
2. Implementación de desmontaje seguro y ordenado mediante `Drop` traits e intercepción de señales de terminación (`SIGINT`, `SIGTERM`).
3. Uso consistente del estándar XDG con `~/RcloneMounts` como directorio raíz de montajes por defecto (configurable en `~/.config/rclone-manager/settings.json`).

### IV. Desktop & Platform Integration (KDE Plasma / Wayland)
1. Integración de primer nivel con KDE Plasma y entornos de escritorio modernos bajo Wayland y X11 mediante `ksni` (StatusNotifierItem puro en Rust vía D-Bus, sin dependencias de GTK) y `notify-rust` para notificaciones D-Bus (`org.freedesktop.Notifications`).
2. Compatibilidad transparente con el entorno de ejecución de `systemd --user` y resolución robusta de ejecutables (`rclone`, variables de entorno `$PATH`).
3. Gestión segura de secretos y credenciales (Google Drive Client ID/Secret, contraseñas RC) delegada a KDE Wallet / Secret Service mediante `keyring`, manteniendo el identificador de servicio `"RcloneKDE"` para migración transparente.
4. Control de instancia única (Single-Instance IPC) mediante socket Unix abstracto (`\0rclone_manager_gna_lock`), activando la ventana existente al recibir el comando `"SHOW"` desde una segunda invocación.

### V. Spec-Driven & Test-First Development
Cada módulo nuevo o refactorizado debe contar con su especificación formal bajo GitHub Spec Kit:
1. Especificación funcional (`/speckit.specify`) y plan de arquitectura (`/speckit.plan`).
2. Tareas atómicas ejecutables (`/speckit.tasks`).
3. Pruebas unitarias y de integración para cada componente del núcleo (cliente RC, gestor de procesos, gestor de montajes).

### VI. Conventional Commits Mandatorio (NON-NEGOTIABLE)
TODO commit realizado en el repositorio DEBE respetar estrictamente la convención de [Conventional Commits v1.0.0](https://www.conventionalcommits.org/):
- Formato: `<tipo>(<ámbito opcional>): <descripción breve y precisa en imperativo>`
- Tipos autorizados: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- Esta regla es verificada y bloqueada a nivel local mediante el hook `commit-msg`. Está prohibido el uso de `--no-verify` para omitir esta regla.

### VII. Pre-Commit Security & Quality Gates
Antes de confirmar cualquier commit, el hook `pre-commit` ejecuta automáticamente:
1. **Escaneo de Secretos:** `gitleaks` bloquea commits que contengan tokens, claves privadas o credenciales en stage.
2. **Chequeo de Sintaxis:** Verificación de sintaxis de Rust (`cargo check`, `cargo fmt`), scripts (`bash -n`) y Python (`py_compile`).
3. **Auditoría de CVEs:** `cargo audit` verifica vulnerabilidades conocidas en dependencias.

### VIII. Filosofía Ponytail (Minimalismo & YAGNI)
Se adopta la mentalidad de Ponytail (`DietrichGebert/ponytail`):
1. La mejor línea de código es la que no se escribe.
2. Soluciones mínimas, completas y directas sobre la biblioteca estándar o dependencias existentes.
3. Cero abstracciones o wrappers innecesarios que nadie ha solicitado (ej.: eliminación explícita de integraciones legadas fuera de alcance como KeePassXC).
4. Toda lógica no trivial debe incluir su correspondiente test unitario.

### IX. Política de Rust Puro y Duro (Zero-Python Policy)
En la rama `feature/rust-migration` y en todo el ciclo de desarrollo de la nueva versión:
1. Queda estrictamente prohibido agregar, modificar o commitear código o dependencias del stack anterior en Python (`.py`, `pyproject.toml`, `uv.lock`, `requirements.txt`).
2. El nuevo stack tecnológico debe ser Rust puro y duro, autónomo y compilado.
3. Esta regla está protegida de manera forzada por el hook `pre-commit`, el cual rechazará automáticamente cualquier archivo de Python en stage.

## Technology Stack & Constraints

- **Lenguaje:** Rust 1.85+ (Edición 2024).
- **Runtime Asíncrono:** `tokio`.
- **Motor Rclone Híbrido:** `rclone rcd` vía HTTP (`reqwest`) para estado/config/cuotas + `tokio::process` supervisado (`kill_on_drop`) para `mount`, `bisync/sync/copy` y `authorize`.
- **Serialización:** `serde`, `serde_json`.
- **Rutas XDG:** `dirs` (`$XDG_CONFIG_HOME/rclone-manager`, `$XDG_CACHE_HOME/rclone-manager`, `~/RcloneMounts`).
- **Secretos:** `keyring` (integración con Secret Service / KDE Wallet bajo servicio `"RcloneKDE"`).
- **Integración KDE:** `ksni` (System Tray SNI), `notify-rust` (Notificaciones D-Bus), socket Unix abstracto (Single-Instance IPC).
- **Logging & Observabilidad:** `tracing`, `tracing-subscriber`, `tracing-appender` con rotación diaria.
- **Frontend / UI:** **Slint** (binario único 100% Rust, vistas `.slint`, soporte nativo Wayland/KDE).

## Quality Gates & Verification

- Todo código debe compilar con cero warnings (`cargo clippy --all-targets -- -D warnings`).
- Formato uniforme obligatorio (`cargo fmt --check`).
- Pruebas automatizadas con `cargo test`.
- No se permiten rutas absolutas hardcodeadas (`$HOME`, `$XDG_CONFIG_HOME`, `$XDG_CACHE_HOME` resueltas dinámicamente).

## Governance

Esta constitución rige todo el desarrollo de la migración a Rust en la rama `feature/rust-migration`. Cualquier cambio arquitectónico debe documentarse mediante una enmienda en este archivo o en las especificaciones asociadas.

**Version**: 1.2.0 | **Ratified**: 2026-11-12 | **Last Amended**: 2026-11-13
