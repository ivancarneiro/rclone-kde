# Rclone Manager (KDE/Qt) - Project Walkthrough

## 🎯 Goal
Build a modern, robust GUI for Rclone on Linux/KDE to simplify Google Drive management, mounting, and bidirectional synchronization.

## ✨ Delivered Features

### 1. Drive Management (The "Wizard")
*   **Easy Setup**: Step-by-step wizard to connect Google Drive.
*   **Advanced Mode**: Supports custom `Client ID` and `Client Secret` for production performance.
*   **Integration**: Seamless OAuth2 flow launching system browser.

### 2. Smart Mounting
*   **One-Click Mount**: Mount drives as local folders (`./mounts/...`).
*   **Auto-Mount**: Configure drives to mount automatically on system startup.
*   **System Tray**: App runs in background; starts minimized if configured.

### 3. Bidirectional Sync (Bisync)
*   **Sync Tasks**: Create tasks to keep local folders identical to remote ones.
*   **Live Logs**: "Matrix-style" real-time terminal view of sync progress.
*   **Auto-Sync**: Checks and runs all sync tasks immediately when the app starts.
*   **Conflict Handling**: Desktop notifications (bubbles) if a sync conflict occurs.

### 4. Security & Production Readiness
*   **Keyring Integration**: The internal control password is generated securely and stored in the system Keyring (GNOME/KWallet).
*   **System Config**: Uses the standard `~/.config/rclone/rclone.conf` so it works alongside your existing Rclone CLI setup.

### 5. Easy Installation
*   **One-Script Install**: `setup.sh` handles everything (VirtualEnv, Dependencies, Rclone check, Desktop Shortcut).

### 6. Custom Branding
*   **Dual Icon System**:
    *   **Isologo**: Used in System Menus and Main Drawer for brand presence.
    *   **Symbol**: Used in Tray and Window Title for clean, minimalist look.

## 🧪 Verification
We verified the production flow by:
1.  **Fresh Install**: Cloned the repository into a clean test directory.
2.  **Setup**: Ran `./setup.sh` successfully.
3.  **Launch**: Confirmed app starts, auto-sync triggers, and logs appear.
4.  **Security**: Verified file permissions and Keyring usage.

## 📸 Screenshots

| Dashboard | Sync Logs | Tray Icon |
|:---:|:---:|:---:|
| *(You have seen the UI live)* | Matrix View implemented | Minimized |

## 🚀 How to Run
```bash
# Just click the "Rclone Manager" icon in your menu!
# Or via terminal:
./start.sh
```
