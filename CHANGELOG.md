# Changelog
Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-11-13
### Added
- **Migración completa a Rust puro + Slint (`rclone-manager`)**: Aplicación nativa compilada en un único binario sin dependencias de Python ni Qt6.
- **Motor Rclone Async Híbrido**: Comunicación HTTP con `rclone rcd` vía `reqwest` (`list_remotes`, `list_mounts`, `about`, `core/stats`, `config/*`) combinada con subprocesos supervisados por Tokio (`mount`, `sync`/`bisync`/`copy` con streaming de logs en vivo y `authorize`).
- **Interfaz gráfica en Slint (`ui/main.slint`)**: Paridad visual de las 5 vistas principales (Dashboard con barras de cuota y diálogos de montaje/borrado, Asistente de nuevo Drive con precarga desde Keyring, Sync Tasks con visor de logs estilo Matrix y Dry-Run, Activity Monitor y Settings).
- **Integración nativa con KDE Plasma / Wayland**: Bandeja del sistema `StatusNotifierItem` mediante `ksni` (D-Bus puro), notificaciones D-Bus mediante `notify-rust`, autostart XDG, selector de directorios nativo (`kdialog`/`zenity`), instancia única por socket Unix abstracto (`SHOW`) y limpieza automática de montajes ante `SIGINT`/`SIGTERM`.
- **Rutas XDG Base Directory**: Configuración en `~/.config/rclone-manager/`, cachés VFS y logs rotativos en `~/.cache/rclone-manager/`, y montajes por defecto en `~/RcloneMounts` (configurable), con migración transparente de `settings.json` y `sync_tasks.json`.

### Removed
- Eliminada por completo la integración legacy con KeePassXC (simplificando la gestión de credenciales exclusivamente al Keyring del sistema vía Secret Service).
- Eliminado el stack anterior en Python/PyQt6/QML.

## [1.3.2] - 2026-08-14
### Fixed
- **Inicio automático (Autostart)**: Restaurado el archivo `.desktop` en `~/.config/autostart/rclone-gui-manager.desktop` apuntando a `start.sh --minimized`.
- **Resiliencia de Auto-Montaje**: Corregido problema donde la carga inicial con remotos vacíos desactivaba prematuramente la rutina de auto-montaje (`_initial_load_done`). Ahora espera a que los remotos estén disponibles.
- **Montaje silencioso en inicio auto**: Se evita la apertura emergente del gestor de archivos (Dolphin) durante el auto-montaje al iniciar el sistema.

## [1.3.1] - 2026-06-09
### Added
- **Integración con KeePassXC**: Lanzamiento automático de la base de datos al montar una unidad virtual.
- **Configuración visual**: Nueva sección en Settings para elegir el remoto y la ruta de la DB de KeePassXC.

### Security
- **Eliminación de scripts externos**: Se eliminaron los scripts de inicio condicional inseguros, integrando la lógica directamente en la app mediante el Keyring del sistema.

## [1.3.0] - 2026-05-26
### Added
- **Reconnect Drive**: Botón 🔄 en Dashboard y Settings para reautorizar remotos con credenciales del keyring sin perder configuración
- **Auto-push de credenciales**: Al guardar Client ID/Secret en Settings, se actualizan automáticamente en todos los remotos existentes
- **Reconnect desde Settings**: Sección "Reconnect Drives" con botón por remote y feedback visual de estado
- **Keyring signal wiring**: El Dashboard se refresca inmediatamente cuando cambian las credenciales en Settings
- **UI Responsive**: 
  - Ventana con tamaño mínimo (700×500)
  - ScrollView en Settings ahora permite scroll al expandir el editor de credenciales
  - Diálogos se redimensionan según tamaño de ventana (`Math.min(fixed, parent.width * 0.9)`)
  - Títulos dinámicos en la ventana del sistema (ej: "Global Settings - Rclone Manager")
- **Documentación**: README, WALKTHROUGH y CHANGELOG reescritos con énfasis en seguridad y usabilidad

### Changed
- **Mount directory**: Unificado bajo `base_dir/mounts` (antes `~/RcloneMounts`)
- **Cache directory**: Movido a `base_dir/data/cache` (antes `~/Rclone-GUI/data/cache` hardcodeado)
- **MountOptionsDialog**: Posicionamiento corregido (usa `x`/`y` en vez de `anchors.centerIn`)
- **SyncView dialogs**: Popups y diálogos usan coordenadas explícitas y tamaños responsivos

### Fixed
- **Modal behind window**: MountOptionsDialog ya no aparece detrás de la ventana principal
- **Settings scroll**: El contenido de Settings ahora hace scroll correctamente cuando el editor de credenciales se expande
- **Títulos duplicados**: La ventana del sistema ahora muestra el título de la vista actual + "Rclone Manager"
- **Referencias a rutas absolutas**: Eliminadas todas las referencias a `/home/ciex/` en los archivos de código

### Security
- **Credenciales en Keyring**: Google OAuth Client ID/Secret almacenados en KDE Wallet / GNOME Keyring
- **Auto-push seguro**: Las credenciales se actualizan sin refrescar el token existente (`config_refresh_token=false`)
- **Reautorización guiada**: Flujo completo de reautorización OAuth con manejo de timeouts (120s) y parseo robusto de tokens

## [1.2.2] - 2026-05-04
### Fixed
- **Mount Management**: Implementada limpieza robusta de "montajes zombie" (puntos de montaje FUSE rotos).
- **Startup/Shutdown**: Se agregó un barrido automático del directorio de montajes (`<base_dir>/mounts`) al iniciar y cerrar la aplicación para prevenir errores de "Transport endpoint is not connected" (ENOTCONN).

## [1.2.1] - 2026-01-14
### Fixed
- Error de crash al inicio relacionado con el monitor de actividad.
- Corregido el problema de "fantasmas" en la lista de transferencias activas.

## [1.2.0] - 2025-12-29
### Added
- Soporte para Sincronización Avanzada (Bisync).
- Nueva interfaz de gestión de tareas de sincronización.
- Soporte para `--drive-acknowledge-abuse` en Google Drive.
