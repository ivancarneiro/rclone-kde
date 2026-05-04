# Changelog
Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.2] - 2026-05-04
### Fixed
- **Mount Management**: Implementada limpieza robusta de "montajes zombie" (puntos de montaje FUSE rotos).
- **Startup/Shutdown**: Se agregó un barrido automático de `~/RcloneMounts` al iniciar y cerrar la aplicación para prevenir errores de "Transport endpoint is not connected" (ENOTCONN).

## [1.2.1] - 2026-01-14
### Fixed
- Error de crash al inicio relacionado con el monitor de actividad.
- Corregido el problema de "fantasmas" en la lista de transferencias activas.

## [1.2.0] - 2025-12-29
### Added
- Soporte para Sincronización Avanzada (Bisync).
- Nueva interfaz de gestión de tareas de sincronización.
- Soporte para `--drive-acknowledge-abuse` en Google Drive.
