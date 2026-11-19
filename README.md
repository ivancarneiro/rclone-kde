# Rclone Manager (Rust + Slint KDE Edition)

[![Recorrido Completo (Walkthrough)](https://img.shields.io/badge/📖-Ver_Recorrido/Manual_de_Uso-blue)](WALKTHROUGH.md)

---

## 📋 Resumen y Propósito

**Rclone Manager** es una interfaz gráfica moderna para Linux que simplifica la gestión de **Rclone** — la potente herramienta de almacenamiento en nube por línea de comandos. Diseñada con **seguridad por defecto** y una **experiencia de usuario fluida**, la app permite gestionar Google Drive sin tocar la terminal.

| Característica | Valor |
|---|---|
| 🛡️ **Seguridad** | Credenciales en Keyring del sistema, auto-limpieza de montajes, límite seguro de borrados |
| 🎯 **Usabilidad** | Reconexión con 1 clic, UI responsive, montaje/sync sin fricción |
| 🪟 **Montaje virtual** | Drive como carpeta local — archivos no ocupan disco |
| 🔄 **Sync bidireccional** | Espejo local ↔ nube con logs en vivo |

---

## 🔐 Seguridad: Diseñada para Producción

### 1. Credenciales en Keyring del Sistema (KDE Wallet / GNOME Keyring)

La app **nunca almacena credenciales en texto plano**. Todo pasa por el keyring del sistema:

| ¿Qué se guarda? | Dónde | Por qué es seguro |
|---|---|---|
| **Google OAuth: Client ID + Secret** | Keyring (`RcloneKDE`) | Cifrado por el sistema operativo, solo tu usuario puede acceder |
| **Contraseña RC API** | Keyring (`RcloneKDE`) | Token aleatorio de 16 bytes (32 caracteres hexadecimales) para autenticar la comunicación interna entre la GUI y el motor Rclone |
| **Token de acceso a Drive** | `~/.config/rclone/rclone.conf` | Archivo con permisos restringidos a tu usuario, compatible con `rclone` CLI |

**Flujo de seguridad al crear una conexión:**
1. Ingresás Client ID y Client Secret en el Wizard
2. Se abré el navegador oficial de Google para autorizar
3. Al éxito, las credenciales se guardan automáticamente en el Keyring
4. En usos futuros, el Wizard las precarga desde el Keyring — no necesitas volver a pegarlas

### 2. Gestión Completa del Ciclo de Vida de Credenciales

Desde **Settings** podés:

| Acción | Cómo |
|---|---|
| **Agregar** | Botón "Add Credentials" → se guardan en Keyring |
| **Actualizar** | Botón "Update Credentials" con auto-push a todos los remotos existentes |
| **Eliminar** | Botón "Remove from Keyring" |
| **Ver estado** | Badge verde "🔑 Credentials saved" o ámbar "⚠️ No credentials" |

### 3. Auto-Push de Credenciales a Remotos Existentes

Al guardar nuevas credenciales en Settings, la app **las propaga automáticamente** a todas las conexiones de Google Drive configuradas. No necesitas actualizar cada remote manualmente.

### 4. Reconexión Segura (Reconnect Drive)

Si tus claves OAuth expiran o regenerás tus credenciales en Google Cloud Console:

1. Actualizás Client ID/Secret en **Settings**
2. Hacés clic en **"🔄 Reconnect"** (desde el Dashboard o Settings)
3. La app: actualiza las credenciales → abre el navegador para reautorizar → guarda el nuevo token

**Sin perder la configuración** del remote (nombre, auto-mount, sync tasks).

### 5. Seguridad en Montajes

| Protección | Descripción |
|---|---|
| **Límite de tamaño** | `--max-size 1G` evita montar archivos enormes que degradarían el rendimiento |
| **Modo Read-Only** | Opción "Safe Mode" al montar — imposible borrar o modificar archivos |
| **Anti-Zombie** | Al iniciar y cerrar, la app barre y limpia montajes rotos (`fusermount -uz`) |
| **Desmontaje lazy** | Usa `fusermount -uz` para evitar que el sistema se cuelgue al cerrar |

### 6. Seguridad en Sincronización

| Protección | Descripción |
|---|---|
| **Límite de borrados** | `--max-delete 5` evita la pérdida masiva de archivos por error de configuración |
| **Dry-run (Simular)** | Botón "👁️" para previsualizar qué cambios haría el sync sin ejecutarlos |
| **Worker asíncrono** | La sincronización corre en tareas Tokio supervisadas — la UI nunca se congela |

---

## 🎯 Usabilidad: Hecha para el Usuario Final

### 1. Dashboard en Tiempo Real

Cada remote se muestra como una tarjeta con:

| Indicador | Qué muestra |
|---|---|
| 🟢🟡🔴 **Status dot** | Montado / Conectado / Error |
| **Barra de almacenamiento** | Uso de Google Drive con alerta visual (>90% en rojo) |
| **Strategy chip** | `BISYNC`, `SYNC`, `COPY` — de un vistazo |
| **Botón contextual** | "Mount" / "Open" / "Unmount" según estado |
| **🔄 Reconnect** | Solo visible si hay credenciales guardadas y el remote no está montado |

### 2. Reconexión con 1 Clic

Botón **"🔄"** en cada remote del Dashboard (y en Settings):
- Detecta automáticamente si hay credenciales en el Keyring
- Muestra feedback visual del progreso: "Reconnecting... → ✅ Reconnected!"
- Tiempo de espera generoso (120s) para la autorización en el navegador

### 3. UI Totalmente Responsive

| Aspecto | Detalle |
|---|---|
| **Tamaño mínimo** | 700×500 píxeles — todos los componentes visibles |
| **ScrollView inteligente** | El contenido de Settings hace scroll cuando se expande el editor de credenciales |
| **Diálogos adaptables** | Se redimensionan según el tamaño de la ventana (`Math.min(fixed, parent.width * 0.9)`) |
| **Títulos dinámicos** | La ventana del sistema muestra la vista actual: "Global Settings - Rclone Manager" |

### 4. Gestión de Conexiones

- **Add New Drive**: Wizard paso a paso con precarga de credenciales desde Keyring
- **Mount options**: Modo lectura, modo stream, todo desde un diálogo
- **Auto-Mount**: Elegí qué drives se montan automáticamente al iniciar sesión
- **Delete**: Confirmación antes de borrar (MessageDialog)

### 5. Sync Bidireccional (Bisync)

| Feature | Descripción |
|---|---|
| **Live Logs** | Vista "Matrix" en tiempo real del progreso de sync |
| **Múltiples estrategias** | Bisync (espejo), Sync (backup local→nube), Copy (descarga nube→local) |
| **Help contextual** | Popup "Cómo usar" con instrucciones claras |
| **Selector de carpeta local** | Botón "..." para elegir con diálogo nativo |

### 6. Rutas XDG Estándar

La aplicación sigue el estándar **XDG Base Directory** (y migra de forma transparente `settings.json` / `sync_tasks.json` previos):

```
~/.config/rclone-manager/
├── settings.json      # Preferencias y auto-montajes
└── sync_tasks.json    # Tareas de sincronización
~/.cache/rclone-manager/
├── vfs/               # Caché VFS de rclone
└── logs/              # Logs rotativos diarios
~/RcloneMounts/        # Puntos de montaje por defecto (configurable en Settings)
```

### 7. Integración con el Sistema

- **System Tray**: Bandeja `StatusNotifierItem` nativa vía D-Bus (`ksni`), minimiza al cerrar, arranque silencioso (`--minimized`)
- **Instancia Única**: Despierta la ventana activa si se intenta abrir una segunda instancia
- **Auto-start**: Acceso directo en `~/.config/autostart/` (gestión desde Settings)
- **Notificaciones del sistema**: Alertas de montaje, errores y conflictos vía D-Bus (`notify-rust`)
- **Apertura en gestor de archivos**: Botón "Open" → Dolphin/gestor predeterminado en el punto de montaje

---

## 💻 Requisitos del Sistema

| Requisito | Detalle |
|---|---|
| **Sistema** | Linux (KDE Plasma Wayland/X11, GNOME, etc.) |
| **Dependencia externa** | `rclone` y `fusermount` / `fusermount3` instalados |
| **Compilación** | Toolchain de Rust (`cargo`, `rustc`) |
| **Keyring** | KDE Wallet, GNOME Keyring o cualquier backend `secret-service` |

---

## 🛠️ Compilación e Instalación

```bash
git clone <repo-url> rclone-kde
cd rclone-kde
cargo build --release
```

El binario único queda generado en `target/release/rclone-manager`.

---

## 🧠 Conceptos Clave: ¿Mount o Sync?

### 🪟 Mount (Montaje Virtual)
Crea una carpeta local que "mira" a la nube. Los archivos **no ocupan espacio** en tu disco.
- ✅ Ideal para trabajar con muchos archivos sin llenar el disco
- ✅ Abrí archivos directamente desde Dolphin
- 🔒 Opción Read-Only para navegación segura

### 🪞 Sync (Espejo Bidireccional / Bisync)
Crea una **copia física idéntica** en tu disco local. Mantiene ambos lados sincronizados.
- ✅ Ideal para backups y trabajo offline
- ✅ Tres estrategias: espejo, backup (local→nube), descarga (nube→local)
- ✅ Simulación (dry-run) antes de ejecutar

---

## 🏗️ Arquitectura (Rust + Slint)

```
├── ui/
│   └── main.slint              # Interfaz declarativa Slint (5 vistas + modales)
└── src/
    ├── main.rs                 # Runtime Tokio, single-instance, tray y ciclo Slint
    ├── lib.rs
    ├── core/
    │   ├── config.rs           # Rutas XDG y resolución de binarios
    │   ├── rclone_client.rs    # Cliente HTTP RC API de Rclone + authorize
    │   ├── process_manager.rs  # Supervisión del daemon rclone rcd
    │   ├── mount_manager.rs    # Montaje/desmontaje + limpieza anti-zombie
    │   ├── sync_manager.rs     # Persistencia CRUD de tareas sync
    │   ├── sync_worker.rs      # Subproceso supervisado sync/bisync/copy + logs
    │   ├── secret_manager.rs   # CRUD de credenciales en Keyring (Secret Service)
    │   ├── settings_manager.rs # Preferencias y migración legacy
    │   ├── single_instance.rs  # Socket abstracto Unix + señal SHOW
    │   ├── autostart_manager.rs
    │   └── notifications.rs    # Notificaciones D-Bus
    └── ui/
        ├── mod.rs
        ├── controller.rs       # Puente asíncrono entre Slint y Tokio/Core
        └── tray.rs             # System Tray nativo vía ksni
```

---

## 🚀 Cómo Usar

```bash
# Ejecutar en primer plano:
./target/release/rclone-manager

# O iniciar minimizado en la bandeja del sistema:
./target/release/rclone-manager --minimized
```

---

## 🛠️ Bug Fixes

- **Inicio Automático con el Sistema**: Restaurada la entrada `.desktop` en `~/.config/autostart/rclone-gui-manager.desktop` para garantizar el inicio de `rclone-kde` con la sesión del sistema en modo minimizado.
- **Resiliencia en Auto-Montaje de Unidades Virtuales**: Corregida la condición de carrera en `MainViewModel` donde la verificación inicial vacía marcaba la carga inicial como terminada (`_initial_load_done`), evitando que el auto-montaje se ejecutara cuando los remotos terminaban de cargar. Ahora el auto-montaje aguarda a la presencia de remotos y se ejecuta de forma silenciosa sin abrir ventanas de Dolphin no deseadas al iniciar el sistema.
