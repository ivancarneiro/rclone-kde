# Feature Specification: Rclone Manager Rust & Slint Migration

**Feature Branch**: `feature/rust-migration`

**Created**: 2026-11-13

**Status**: Approved

**Input**: Migración completa de Rclone Manager v1.3.2 (Python/PyQt6/QML) a un binario nativo en Rust + Slint bajo estándar XDG puro, motor Rclone híbrido asíncrono, integración D-Bus nativa para KDE Plasma/Wayland y paridad funcional 1:1 excluyendo la integración legada de KeePassXC.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Core Foundation, XDG & Keyring Migration (Priority: P1)

Como usuario existente en Linux/KDE Plasma, al iniciar la nueva versión en Rust quiero que la aplicación respete el estándar XDG (`~/.config/rclone-manager/`, `~/.cache/rclone-manager/`, `~/RcloneMounts`), reutilice mis credenciales ya guardadas en KDE Wallet (`RcloneKDE`), migre automáticamente mi `settings.json` / `sync_tasks.json` heredado descartando campos obsoletos (KeePassXC) y garantice una única instancia activa capaz de mostrar su ventana si intento abrirla de nuevo.

**Why this priority**: Es la base obligatoria de configuración, seguridad e IPC sobre la que operan todos los gestores y la interfaz gráfica.

**Independent Test**: Se verifica mediante pruebas unitarias de resolución XDG, migración JSON sin campos KeePassXC, lectura/escritura en `SecretStore` (simulado y real) y prueba IPC con dos sockets Unix abstractos validando que el segundo envía `"SHOW\n"` y el primero lo recibe.

**Acceptance Scenarios**:

1. **Given** que existe `./settings.json` con `auto_mounts`, `start_minimized` y `keepassxc_remote`, y no existe `~/.config/rclone-manager/settings.json`, **When** se inicializa `SettingsManager`, **Then** se importa la configuración en `~/.config/rclone-manager/settings.json` preservando `auto_mounts`, `start_minimized` y `sync_strategies`, eliminando `keepassxc_*`.
2. **Given** credenciales `google_client_id`, `google_client_secret` o `rc_pass` almacenadas en KDE Wallet bajo el servicio `"RcloneKDE"`, **When** se consulta `SecretManager`, **Then** se recuperan sin pedir reingreso manual.
3. **Given** una instancia ejecutándose con el socket abstracto `\0rclone_manager_gna_lock` escuchando, **When** se lanza una segunda instancia, **Then** la segunda instancia envía `"SHOW\n"`, cierra con código `0` y la instancia principal recibe el evento `InstanceCommand::Show`.

---

### User Story 2 - Dashboard & Virtual Mount Resilience (Priority: P1)

Como usuario, quiero ver mis remotos configurados en un Dashboard en tiempo real (estado, cuota de almacenamiento, estrategia de sincronización) y poder montar, abrir en mi gestor de archivos, desmontar, reconectar con 1 clic (`🔄`) o eliminar cada remoto con protección anti-zombie.

**Why this priority**: Es el flujo principal de uso diario de Rclone Manager.

**Independent Test**: Tests de integración del cliente RC contra un mock HTTP para `config/listremotes`, `about`, `core/stats`, y tests del `MountManager` validando la construcción de comandos `rclone mount`, detección de puntos de montaje y limpieza con `fusermount -uz`.

**Acceptance Scenarios**:

1. **Given** un remoto montado o zombie al arrancar o cerrar la aplicación, **When** se ejecuta `cleanup_all` / `cleanup_zombie` o se recibe `SIGINT`/`SIGTERM`, **Then** los procesos gestionados se terminan de forma ordenada y se ejecuta `fusermount -uz` sobre el punto de montaje.
2. **Given** un remoto desconectado y credenciales OAuth válidas en el keyring, **When** el usuario pulsa "Reconnect", **Then** la app actualiza `client_id`/`client_secret` sin refrescar token, ejecuta `rclone authorize drive` (timeout 120s), extrae el JSON del token y actualiza el remoto.
3. **Given** remotos configurados en `auto_mounts`, **When** el Dashboard carga los remotos disponibles por primera vez, **Then** los monta silenciosamente sin abrir ventanas emergentes del gestor de archivos.

---

### User Story 3 - New Drive OAuth Wizard (Priority: P2)

Como usuario, quiero añadir un nuevo remoto de Google Drive mediante un asistente guiado que precargue automáticamente mi `client_id` y `client_secret` desde el keyring si existen, abra el navegador para autorizar y opcionalmente guarde las credenciales y habilite el auto-montaje.

**Why this priority**: Permite incorporar nuevos remotos sin usar la terminal.

**Independent Test**: Verificación unitaria de parseo del token JSON devuelto por `rclone authorize` y validación del flujo de creación y persistencia en keyring.

**Acceptance Scenarios**:

1. **Given** credenciales guardadas en el keyring, **When** se abre el Wizard, **Then** los campos se precargan con un indicador visual de credenciales disponibles.
2. **Given** un nombre de remoto válido y autorización exitosa en el navegador, **When** finaliza `rclone authorize`, **Then** se crea el remoto en `rclone.conf`, se persisten credenciales si se marcó la opción y se actualiza el Dashboard.

---

### User Story 4 - Sync Tasks, Bisync & Live Logs (Priority: P2)

Como usuario, quiero crear, listar, ejecutar, simular (`dry-run`) y eliminar tareas de sincronización (`bisync`, `sync`, `copy`) entre carpetas locales y remotos, visualizando el flujo de logs en tiempo real sin bloquear la interfaz.

**Why this priority**: Cubre los flujos de respaldo y espejo bidireccional de datos.

**Independent Test**: Tests de persistencia de `sync_tasks.json` en `~/.config/rclone-manager/` y streaming asíncrono de salida de subprocesos mediante canales `tokio::sync::mpsc`.

**Acceptance Scenarios**:

1. **Given** una tarea configurada con estrategia `bisync`, `sync` o `copy`, **When** se ejecuta en modo real o simulación (`--dry-run`), **Then** se aplica `--max-delete 5` por seguridad y cada línea de stdout/stderr llega en tiempo real a la vista de logs.
2. **Given** un cierre de ventana o cancelación, **When** el worker se detiene o es dropeado, **Then** el subproceso `rclone` hijo se termina limpiamente (`kill_on_drop`).

---

### User Story 5 - Activity Monitor, Settings, Tray & Autostart (Priority: P3)

Como usuario de KDE Plasma/Wayland, quiero monitorear transferencias activas (`core/stats`), gestionar credenciales OAuth (agregar, actualizar con auto-push a remotos existentes, eliminar), configurar arranque minimizado, auto-inicio (`.desktop` en `~/.config/autostart/`), carpeta raíz de montajes y controlar la app desde el System Tray nativo.

**Why this priority**: Completa la paridad 1:1 con v1.3.2 y la experiencia nativa de escritorio.

**Independent Test**: Tests de generación/borrado del archivo `.desktop` en un directorio temporal, tests de deserialización de `core/stats` y validación de auto-push de credenciales.

**Acceptance Scenarios**:

1. **Given** el toggle de Autostart activado en Settings, **When** se habilita, **Then** se crea `~/.config/autostart/rclone-gui-manager.desktop` apuntando al binario compilado con `--minimized`.
2. **Given** el usuario cierra la ventana principal, **When** la app no está en modo quit explícito, **Then** la ventana se oculta manteniendo el icono activo en la bandeja del sistema (`ksni`).
3. **Given** nuevas credenciales OAuth guardadas desde Settings, **When** existen remotos de Google Drive configurados, **Then** se propagan automáticamente (`client_id` / `client_secret` con `config_refresh_token=false`) a todos ellos.

---

### Edge Cases

- ¿Qué ocurre si `rclone` o `fusermount` no están instalados o no se encuentran en el `$PATH` mínimo de `systemd --user`? El gestor resuelve ejecutables incluyendo `~/.local/bin`, `~/.cargo/bin`, `/usr/local/bin`, `/usr/bin` y reporta un estado claro sin pánico.
- ¿Qué ocurre si el daemon de Keyring (KDE Wallet) está bloqueado o no disponible? `SecretManager` emite una advertencia en logs y utiliza un fallback seguro en memoria para `rc_pass` sin impedir el arranque.
- ¿Qué ocurre si el puerto `5572` está ocupado por un `rclone rcd` huérfano previo? `ProcessManager` limpia procesos previos asociados al puerto configurado antes de lanzar la nueva instancia supervisada.
- ¿Qué ocurre si `settings.json` en disco tiene JSON corrupto o campos legados como `keepassxc_*`? Los campos desconocidos se ignoran silenciosamente y un archivo corrupto no provoca pánico (se registra error y se usan valores por defecto).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE compilar como un binario nativo en Rust 100% libre de dependencias Python (Zero-Python Policy).
- **FR-002**: El sistema DEBE resolver rutas siguiendo el estándar XDG (`~/.config/rclone-manager/`, `~/.cache/rclone-manager/`, `~/RcloneMounts` por defecto y `~/.config/rclone/rclone.conf`).
- **FR-003**: El sistema DEBE migrar automáticamente `./settings.json` y `./sync_tasks.json` hacia `~/.config/rclone-manager/` en el primer arranque si el destino aún no existe, descartando `keepassxc_remote` y `keepassxc_db_path`.
- **FR-004**: El sistema DEBE almacenar y leer `rc_pass`, `google_client_id` y `google_client_secret` desde el Keyring del sistema bajo el servicio `"RcloneKDE"`.
- **FR-005**: El sistema DEBE garantizar instancia única mediante socket Unix abstracto (`\0rclone_manager_gna_lock`), enviando `"SHOW\n"` cuando se invoca una segunda instancia para restaurar la ventana activa.
- **FR-006**: El sistema DEBE utilizar un motor híbrido asíncrono: `rclone rcd` vía HTTP (`reqwest`) para estado/config/cuotas y `tokio::process` supervisado (`kill_on_drop`) para `mount`, `bisync/sync/copy` y `authorize`.
- **FR-007**: El sistema DEBE limpiar montajes zombie (`fusermount -uz`) al iniciar, antes de montar y al cerrar (incluyendo manejo de `SIGINT`/`SIGTERM`).
- **FR-008**: El sistema DEBE implementar paridad 1:1 de las 5 vistas en **Slint** (Dashboard, NewDriveWizard, SyncView, ActivityView, SettingsView + MountOptionsDialog) sin ninguna funcionalidad ni referencia de KeePassXC.
- **FR-009**: El sistema DEBE integrarse con KDE Plasma/Wayland mediante `ksni` (StatusNotifierItem D-Bus) y `notify-rust` (notificaciones D-Bus).

### Key Entities *(include if feature involves data)*

- **AppPaths**: Resolución de directorios XDG (`config_dir`, `cache_dir`, `vfs_cache_dir`, `logs_dir`, `default_mount_dir`, `rclone_conf`).
- **AppSettings**: Preferencias persistidas (`auto_mounts`, `start_minimized`, `mount_dir`, `sync_strategies`), excluyendo KeePassXC.
- **GoogleCredentials**: Par `client_id` / `client_secret` almacenado en el Keyring del sistema.
- **SyncTask**: Definición de tarea (`id`, `name`, `local_path`, `remote_path`, `remote_name`, `strategy`, `last_sync`, `status`).
- **RemoteInfo / MountState**: Estado en tiempo real de un remoto (`name`, `mounted`, `mount_point`, `quota_used`, `quota_total`, `sync_strategy`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` y `cargo audit` pasan al 100% sin advertencias ni vulnerabilidades.
- **SC-002**: Ningún hook de `.githooks/` (`pre-commit`, `commit-msg`) ni `gitleaks` es omitido o falla en los commits.
- **SC-003**: Cero líneas de Python y cero referencias a KeePassXC en el código fuente y configuración generada.
- **SC-004**: El binario compilado arranca en KDE Plasma/Wayland mostrando icono en la bandeja del sistema, detecta remotos existentes y monta/desmonta sin bloqueos de UI.

## Assumptions

- El sistema anfitrión es Linux (KDE Plasma bajo Wayland o X11) con `rclone` y `fusermount` / `fusermount3` disponibles en el sistema.
- El usuario cuenta con un proveedor de `org.freedesktop.secrets` (KDE Wallet / GNOME Keyring) en sesiones de escritorio interactivas.
