# Rclone Manager - Project Instructions

## Convenciones de Desarrollo
- **Commits**: Seguir [Conventional Commits](https://www.conventionalcommits.org/) (ej: `fix(mount): ...`, `docs: ...`).
- **Documentación**: 
    - Mantener `CHANGELOG.md` siguiendo "Keep a Changelog".
    - En `README.md`, los arreglos de errores van bajo la sección "## 🛠️ Bug Fixes".
- **Arquitectura**: 
    - La lógica de montajes debe centralizarse en `MountManager`.
    - La limpieza de montajes zombie se realiza mediante `fusermount -uz` (lazy unmount).

## Workflow de Resiliencia
- La aplicación DEBE limpiar el directorio de montajes (`~/RcloneMounts`) al iniciar y al cerrar para evitar errores de conexión (ENOTCONN).
