# Rclone Manager (KDE/Qt) - Manual de Usuario

## 🎯 ¿Qué hace esta app?

**Rclone Manager** es una interfaz gráfica para Rclone enfocada en **seguridad** y **usabilidad**. Permite conectar Google Drive, montarlo como carpeta local y sincronizar archivos — sin tocar la terminal.

---

## ✨ Funcionalidades Clave

### 1. 🔐 Gestión Segura de Credenciales

#### Keyring del Sistema (KDE Wallet / GNOME Keyring)

Tus credenciales de Google OAuth (Client ID y Client Secret) se almacenan de forma **cifrada** en el keyring del sistema operativo. La app **nunca** las guarda en texto plano.

**Desde Settings podés:**

| Acción | Pasos |
|---|---|
| **Ver estado** | Badge verde "🔑 Credentials saved" o ámbar "⚠️ No credentials" |
| **Agregar/Actualizar** | Click en "Update Credentials" → pegás Client ID y Secret → "Save to Keyring" |
| **Auto-push** | Al guardar, las credenciales se actualizan automáticamente en TODOS tus remotos existentes |
| **Eliminar** | Click en "Remove from Keyring" |

#### Reconexión sin Recrear (Reconnect Drive)

Cuando tus credenciales OAuth expiran o regenerás las claves en Google Cloud Console:

**Desde el Dashboard:**
1. Actualizás Client ID/Secret en **Settings** (se auto-pushean a todos los remotos)
2. Volvés al Dashboard → cada remote desconectado muestra un botón **🔄**
3. Click en **🔄** → la app abre el navegador para reautorizar con Google
4. ✅ **Listo**: el remote queda conectado con el nuevo token

**Desde Settings:**
1. Igual que arriba, más una sección "Reconnect Drives" con botón por remote
2. Feedback visual del progreso en cada uno

**Ventajas:**
- ❌ No necesitas borrar y recrear el remote
- ❌ No pierdes configuración (auto-mount, sync tasks asociadas)
- ✅ El token se actualiza automáticamente

---

### 2. 🪟 Montaje Inteligente

Convierte tu Google Drive en una carpeta local:

```
rclone-kde/mounts/ivanexequielc/   ← Así se ve en tu PC
```

| Opción de montaje | Cómo se activa | Para qué sirve |
|---|---|---|
| **Read-Write (default)** | Click "Mount" en Dashboard | Uso diario |
| **Read Only (Safe Mode)** | ⚙️ → marcar "Read Only" → OK | Navegar sin riesgo de borrar |
| **Stream Mode** | ⚙️ → marcar "Stream Mode" → OK | Ahorrar disco local (caché mínima) |

**Protecciones de seguridad:**
- `--max-size 1G`: archivos enormes no se montan (evita crashes)
- `--vfs-cache-max-size 5G`: límite de caché local
- Anti-zombie: al iniciar y cerrar, la app limpia montajes rotos automáticamente

---

### 3. 🪞 Sincronización Bidireccional (Bisync)

Mantené carpetas locales idénticas a la nube.

| Estrategia | Dirección | Ideal para |
|---|---|---|
| **🔄 Bisync (Espejo)** | Local ↔ Nube | Trabajo diario, mantener ambos lados sincronizados |
| **⬆️ Sync (Backup)** | Local → Nube | Subir archivos, borra en nube lo que no existe local |
| **⬇️ Copy (Descarga)** | Nube → Local | Descargar todo sin borrar nada local |

**Seguridad en sync:**
- `--max-delete 5`: límite de seguridad que evita borrados masivos accidentales
- Botón **👁️ (Simular)**: ejecuta dry-run antes del sync real para previsualizar cambios
- Los logs se muestran en vivo con estilo "Matrix"

---

### 4. 🖥️ Dashboard en Tiempo Real

Cada remote se muestra como una tarjeta con información de un vistazo:

```
🟢 ivanexequielc — Google Drive
   BISYNC  Storage: 2.3G / 15G [████████░░░░░░░]
                              [Mount] [⚙️] [🗑️]
```

- **Indicador de estado**: 🟢 Montado / 🟡 Conectado / 🔴 Error
- **Barra de almacenamiento**: verde (<90%) / roja (>90%)
- **Strategy chip**: muestra la estrategia de sync configurada
- **Botones contextuales**: cambian según estado (Mount/Open/Unmount)

---

### 5. 🔄 UI Responsive

La interfaz se adapta al tamaño de la ventana:

| Aspecto | Comportamiento |
|---|---|
| **Tamaño mínimo** | 700×500px — todos los componentes visibles |
| **Settings** | El contenido hace scroll cuando el editor de credenciales se expande |
| **Diálogos** | Logs, Sync Task, Mount Options se redimensionan automáticamente |
| **Títulos dinámicos** | La ventana del sistema muestra la vista actual |

---

### 6. ⚙️ Sistema Tray y Auto-Inicio

| Función | Cómo se activa |
|---|---|
| **Minimizar al cerrar** | Default — la ventana se oculta, no se cierra |
| **Arranque silencioso** | Settings → "Start Minimized to Tray" |
| **Auto-mount** | Settings → toggle por remote para montar al iniciar sesión |
| **Notificaciones** | Alertas vía `notify-send` al montar, desmontar, o en errores |

---

## 📖 Guía Paso a Paso

### Primer Uso

1. **Ejecutar la app**: Click en "Rclone Manager" del menú, o `./start.sh`
2. **Agregar credenciales** (opcional pero recomendado):
   - Ve a **(☰) → Settings**
   - Click en **"Add Credentials"**
   - Pegá tu **Client ID** y **Client Secret** de Google Cloud Console
   - Click en **"Save to Keyring"**
3. **Crear conexión**:
   - Dashboard → **"Add New Drive"**
   - Ingresá nombre (ej: "Mi Drive")
   - Click en **"Connect & Authorize"**
   - Iniciá sesión en el navegador que se abre
4. **Montar**: volvés al Dashboard → click **"Mount"** en tu remote

### Recuperar Conexión (si expiró el token)

1. Settings → **"Update Credentials"** → guardás las nuevas → se pushean automáticamente
2. Dashboard → click **🔄** en el remote → autorizás en el navegador

### Sincronizar Carpeta

1. **(☰) → Sync Tasks**
2. **"New Task"** → nombre, carpeta local, remote, estrategia
3. **"Sync Now"** o **"👁️"** para simular primero

---

## 🏗️ Estructura de Archivos

```
rclone-kde/
├── mounts/           # Puntos de montaje de Google Drive
│   └── ivanexequielc/
├── data/
│   └── cache/        # Caché VFS de archivos montados
├── src/
│   ├── main.py       # Punto de entrada
│   ├── core/         # Backend (seguridad, montaje, sync)
│   └── ui/           # Frontend (QML + ViewModels)
├── settings.json     # Preferencias de la app
├── sync_tasks.json   # Tareas de sincronización
├── start.sh          # Script de inicio
├── setup.sh          # Instalación
└── README.md         # Documentación principal
```

> **Nota**: Todos los paths son relativos al proyecto. Cloná el repo en otro dispositivo, ejecutá `setup.sh`, y todo funciona sin configuración adicional.

---

## 🔐 Resumen de Seguridad

| Aspecto | Cómo lo resuelve la app |
|---|---|
| **Almacenamiento de credenciales** | Keyring del sistema (KDE Wallet / GNOME Keyring) |
| **Comunicación GUI-Rclone** | Contraseña RC aleatoria de 16 bytes en keyring |
| **Protección contra borrados** | `--max-delete 5` en sync |
| **Montajes rotos** | Limpieza automática al iniciar y cerrar |
| **Token expirado** | Reconexión con 1 clic sin perder configuración |
| **Actualización de claves** | Auto-push a todos los remotos al guardar en Settings |
