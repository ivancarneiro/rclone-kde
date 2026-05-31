# Guía de Despliegue - Rclone Manager v1.3.0

Esta versión introduce mejoras críticas en seguridad (Keyring), estabilidad de montajes y una UI responsiva.

## 📋 Requisitos Previos

- **Python 3.10+**
- **Rclone v1.60+** instalado y en el PATH.
- **KDE Wallet** o **GNOME Keyring** activo (para almacenamiento seguro de credenciales).
- Dependencias de Python:
  ```bash
  pip install PyQt6 keyring
  ```

## 🚀 Instalación y Ejecución

### Opción A: Ejecución desde Código Fuente
1. Clonar el repositorio: `git clone https://github.com/ivancarneiro/rclone-kde.git`
2. Instalar dependencias: `pip install -r requirements.txt`
3. Iniciar: `python3 src/main.py`

### Opción B: Empaquetado con PyInstaller
Si deseas generar un ejecutable autocontenido:
1. Instalar PyInstaller: `pip install pyinstaller`
2. Generar el paquete: `pyinstaller rclone_kde.spec`
3. El ejecutable se encontrará en `dist/rclone-kde/rclone-kde`.

## 🔒 Configuración de Seguridad

1. Al abrir la app, ve a **Settings**.
2. Ingresa tu **Google OAuth Client ID** y **Secret**. 
3. La aplicación los guardará automáticamente en el Keyring del sistema.
4. Usa el botón **🔄 Reconnect** para autorizar tus unidades sin perder la configuración previa.

## 🛠️ Notas de esta Versión (v1.3.0)

- **Montajes:** Ahora se centralizan en el directorio del proyecto bajo `mounts/`.
- **Caché:** Se gestiona automáticamente en `data/cache/` con un límite de 5GB.
- **Sincronización:** Se recomienda usar el botón **Simulate (Dry-run)** antes de ejecutar tareas de Bisync por primera vez.

---
*Documento de despliegue generado para rclone-kde v1.3.0*
