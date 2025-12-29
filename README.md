# Rclone Manager (KDE/Qt Version)

## 📋 Resumen y Propósito
**Rclone Manager** es una interfaz gráfica moderna (GUI) desarrollada para Linux (específicamente entornos KDE Plasma, aunque compatible con otros) que facilita la gestión de **Rclone**, la potente herramienta de línea de comandos para gestionar almacenamiento en la nube.

Esta aplicación permite a los usuarios:
*   Conectar cuentas de Google Drive de forma sencilla (Wizard).
*   **Montar** unidades en la nube como si fueran discos locales.
*   **Sincronizar** carpetas bidireccionalmente (Modo Espejo/Bisync) con soporte en segundo plano.
*   Gestionar el **arranque automático** de unidades al iniciar el sistema.
*   Integración nativa con la **Bandeja del Sistema (System Tray)**.

---

## 💻 Requisitos del Sistema
*   **Sistema Operativo**: Linux (Probado en KDE Neon / Ubuntu / Fedora).
*   **Dependencia Externa**: `rclone` debe estar instalado en el sistema (`sudo apt install rclone` o via script oficial).
*   **Python**: Versión 3.9 o superior.
*   **Librerías Gráficas**: Qt6 (vía PyQt6).

---

## 🛠️ Tecnologías Usadas

### Stack Principal
*   **Lenguaje**: Python 3.
*   **Frontend**: Qt Quick (QML) + Kirigami (Estilo KDE).
*   **Backend Binding**: PyQt6.
*   **Motor de Nube**: Rclone (ejecutándose en modo `rcd` daemon).

### Librerías Clave (Python)
*   `PyQt6`: Enlace entre Python y el framework Qt6.
*   `aiohttp`: Para la comunicación asíncrona HTTP con la API de Rclone (`rclone rc`).
*   `subprocess`, `threading`: Manejo de procesos en segundo plano (workers de sincronización).

---

## 🏗️ Arquitectura y Funciones

La aplicación sigue el patrón de diseño **MVVM (Model-View-ViewModel)** para separar la lógica de negocio de la interfaz gráfica.

### 1. `src/core/` (Lógica de Negocio)
*   **`rclone_client.py`**: Cliente HTTP asíncrono para comunicarse con el daemon de Rclone (`http://localhost:5572`). Maneja comandos como `mount`, `listremotes`, `config/dump`.
*   **`process_manager.py`**: Se encarga de iniciar y detener el proceso `rclone rcd` automáticamente al abrir/cerrar la app.
*   **`sync_manager.py`**: Gestiona la base de datos (JSON) de tareas de sincronización (carpetas locales ↔ remotas).
*   **`settings_manager.py`**: Controla las preferencias globales (`settings.json`) como el auto-montaje y el inicio minimizado.
*   **`autostart_manager.py`**: Crea y elimina archivos `.desktop` en `~/.config/autostart/` para la integración con el inicio de sesión de Linux.

### 2. `src/ui/viewmodels/` (ViewModels)
*   **`main_vm.py`**: Cerebro de la pantalla principal. Lista conexiones, gestiona el montaje/desmontaje y coordina el System Tray.
*   **`wizard_vm.py`**: Lógica del asistente de "Nueva Conexión". Maneja el flujo de OAuth2 con Google Drive.
*   **`sync_vm.py`**: Controla la vista de Sincronización. Lanza hilos (`QThread`) para ejecutar `rclone bisync` sin congelar la interfaz.
*   **`settings_vm.py`**: Intermediario para el panel de configuración global.

### 3. `src/ui/qml/` (Interfaz de Usuario)
*   **`Main.qml`**: Ventana principal con navegación lateral (Drawer) y Dashboard.
*   **`SyncView.qml`**: Panel de gestión de tareas de sincronización. Incluye tutoriales e indicadores de estado.
*   **`SettingsView.qml`**: Pantalla de configuración global.
*   **`Dialogs/NewDriveWizard.qml`**: Asistente paso a paso para crear conexiones.

---

## 📖 Manual de Uso

### 1. Iniciar la Aplicación
Ejecuta el script principal:
```bash
python3 src/main.py
```
La aplicación iniciará el daemon de Rclone en segundo plano.

### 2. Crear una Conexión (Google Drive)
1.  En el Dashboard, haz clic en **"Add New Drive"**.
2.  Ingresa un nombre para la conexión (ej. "MiGoogleDrive").
3.  Clic en "Next".
4.  Marca "Mount automatically" si deseas que se monte al iniciar el PC.
5.  Clic en **"Connect & Authorize"**. Se abrirá tu navegador para iniciar sesión en Google.
6.  Al finalizar, verás la nueva conexión en el Dashboard.

### 3. Montar y Usar
*   En el Dashboard, haz clic en **"Mount"** en tu tarjeta de conexión.
*   El estado cambiará a **Mounted** (Verde).
*   Ahora puedes abrir tu gestor de archivos (Dolphin/Nautilus) en `~/RcloneMounts/NombreConexion` y usar tus archivos directamente.

### 4. Sincronización Bireccional (Bisync)
Ideal para mantener una carpeta local idéntica a una en la nube.
1.  Ve al menú lateral **(☰) -> Sync Tasks**.
2.  Clic en **"New Task"**.
3.  Selecciona tu carpeta Local y la ruta Remota.
4.  Clic en **"Sync Now"** para iniciar.
    *   **Logs en Tiempo Real**: Pulsa el botón **"Logs"** en la tarea### Estructura de Archivos recomendada:
```
Rclone-GUI/
├── rclone-kde/
│   ├── settings.json         # Preferencias de la app
│   ├── sync_tasks.json       # Base de datos de tareas sync
│   ├── src/
│   │   ├── main.py           # Punto de entrada
│   │   ├── core/             # Backend
│   │   ├── ui/               # Frontend (QML + ViewModels)
│   │   └── assets/           # Imágenes e iconos
```

**Nota Importante**: La aplicación utiliza ahora la configuración estándar de Rclone (`~/.config/rclone/rclone.conf`). Esto significa que **detectará automáticamente** cualquier control remoto que ya tengas configurado en tu sistema.
### 5. Configuración y System Tray
*   **Minimizar**: Al cerrar la ventana, la app se minimiza al área de notificaciones (reloj).
*   **Configuración**: Ve a **(☰) -> Settings**.
    *   Activa **"Start Minimized to Tray"** para un arranque silencioso.
    *   Gestiona qué unidades se montan solas con los interruptores de **"Auto-Mount"**.

---

## 👨‍💻 Instalación Fácil (Para Usuarios)

Hemos incluido un script de instalación simplificado:

```bash
cd Rclone-GUI/rclone-kde
chmod +x setup.sh
./setup.sh
```

Esto:
1.  Creará el entorno virtual.
2.  Instalará todas las dependencias (incluyendo `keyring` para máxima seguridad).
3.  Creará un acceso directo en tu menú de aplicaciones ("Rclone Manager").

## 🔐 Seguridad y Arquitectura de Credenciales

Esta aplicación utiliza un **modelo de seguridad híbrido** para garantizar tanto la protección del sistema como la compatibilidad con el ecosistema Rclone:

1.  **Protección de la App (Keyring)**:
    *   La comunicación interna entre la interfaz gráfica (GUI) y el motor Rclone (RC API) está blindada.
    *   Utilizamos el **Keyring del Sistema** (GNOME Keyring / KWallet) para generar y almacenar una contraseña aleatoria única para esta sesión de control. Esto impide que otro software en tu PC pueda "secuestrar" el control de Rclone.

2.  **Credenciales de Nube (Standard)**:
    *   Tus tokens de acceso (Google Drive, Client ID, Secret) se almacenan en el archivo de configuración estándar de Rclone (`~/.config/rclone/rclone.conf`).
    *   **¿Por qué?**: Esto asegura que puedas seguir utilizando `rclone` desde la terminal sin perder acceso a tus cuentas.
    *   La seguridad de estos tokens depende de los permisos del archivo (que Rclone restringe a solo tu usuario) o del cifrado nativo de Rclone si decides activarlo.

