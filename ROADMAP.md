# Rclone Manager Roadmap

## v1.2: Advanced Sync & Mount Options (Next Priority)
- [ ] **Selector de Estrategia de Sincronización (Wizard/Settings)**
    - **Default:** `bisync` (Two-way / Espejo) - *Comportamiento actual.*
    - **Option:** `sync` (One-way: Local -> Remote) - Para backups puros.
    - **Option:** `copy` (One-way: Remote -> Local) - Para descargar sin borrar.
- [ ] **Opciones de Montaje (Mount)**
    - **Default:** Read/Write with VFS Cache - *Comportamiento actual.*
    - **Option:** `--read-only` (Protección contra borrado accidental).
    - **Option:** `--network-mode` (Optimización para conexiones inestables).

## v1.3: Usabilidad y Rendimiento
- [ ] **Botonera de Ayuda/Info:** Tooltips o modales explicando conceptos clave (Mount vs Sync) en el Dashboard.
- [ ] **Bandwidth Limiter:** Configurar límites de velocidad de subida/bajada global.
- [ ] **Selective Sync:** Excluir carpetas/patrones específicos (ej: `*.tmp`, `node_modules/`).
- [ ] **Historial de Logs:** Visualizar logs de tareas pasadas (persistencia).

## v2.0: Multi-Cloud & Encryption
- [ ] **Soporte Nativo para `rclone crypt`:** Crear carpetas encriptadas desde la UI.
- [ ] **Dashboard Unificado:** Ver estado de múltiples nubes en una sola gráfica.
