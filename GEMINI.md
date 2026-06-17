# Rclone Manager - Project Instructions

## Flujo de Trabajo (Git Flow)
- **Rama `master`**: Reservada estrictamente para producción. NUNCA hacer push directo.
- **Rama `staging`**: Rama principal de desarrollo y pruebas. Todos los cambios nuevos deben integrarse aquí primero.
- **Merge a master**: Solo mediante Pull Request (PR) real (`gh pr create`).
- **Integridad**: NUNCA desactivar la protección de la rama `master` en GitHub/GitLab. La sincronización debe ser un proceso de revisión y aprobación formal, incluso si es por nosotros mismos.
- **Validación**: Mandatorio ejecutar `uv run pytest` en `staging` antes de abrir un PR a `master`.
- **Commits atómicos y preventivos**: Tras finalizar y probar los cambios de una funcionalidad (feature), se deben commitear inmediatamente a `staging` antes de iniciar el desarrollo de un feature o corregir un problema diferente. Evitar acumular múltiples cambios inconexos sin commit.

## Convenciones de Desarrollo
- **Commits**: Seguir [Conventional Commits](https://www.conventionalcommits.org/) (ej: `fix(mount): ...`, `docs: ...`).
- **Documentación**: 
    - Mantener `CHANGELOG.md` siguiendo "Keep a Changelog".
    - En `README.md`, los arreglos de errores van bajo la sección "## 🛠️ Bug Fixes".
- **Arquitectura**: 
    - La lógica de montajes debe centralizarse en `MountManager`.
    - La limpieza de montajes zombie se realiza mediante `fusermount -uz` (lazy unmount).

## Workflow de Resiliencia
- La aplicación DEBE limpiar el directorio de montajes (`<base_dir>/mounts`) al iniciar y al cerrar para evitar errores de conexión (ENOTCONN).
