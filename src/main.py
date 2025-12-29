import sys
import logging
import signal
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QIcon, QAction
import os

from core.process_manager import RcloneProcessManager
from core.rclone_client import RcloneClient
from core.config import Config
from core.sync_manager import SyncManager
from core.settings_manager import SettingsManager
from core.autostart_manager import AutostartManager
from ui.viewmodels.main_vm import MainViewModel
from ui.viewmodels.wizard_vm import WizardViewModel
from ui.viewmodels.sync_vm import SyncViewModel
from ui.viewmodels.settings_vm import SettingsViewModel

def setup_tray(app, icon_path, main_vm):
    tray_icon = QSystemTrayIcon(QIcon(icon_path), app)
    tray_icon.setToolTip(Config.APP_NAME)
    
    menu = QMenu()
    
    action_show = QAction("Show Rclone Manager", menu)
    action_show.triggered.connect(main_vm.show_window)
    menu.addAction(action_show)
    
    menu.addSeparator()
    
    action_quit = QAction("Quit", menu)
    action_quit.triggered.connect(main_vm.quit_app)
    menu.addAction(action_quit)
    
    tray_icon.setContextMenu(menu)
    
    # Click behavior
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            main_vm.show_window()
            
    tray_icon.activated.connect(on_tray_activated)
    tray_icon.show()
    return tray_icon

def main():
    logging.basicConfig(level=logging.INFO)
    
    # Init Backend
    pm = RcloneProcessManager(
        rc_addr=Config.RC_ADDR, 
        rc_user=Config.RC_USER, 
        rc_pass=Config.get_rc_pass(),
        rc_conf=Config.RCLONE_CONF
    )
    if not pm.start_daemon():
        print("Warning: Could not start rclone daemon. Is rclone installed?")

    client = RcloneClient(
        url=Config.get_rc_url(), 
        user=Config.RC_USER, 
        password=Config.get_rc_pass()
    )

    sync_manager = SyncManager()
    settings_manager = SettingsManager()
    autostart_manager = AutostartManager()

    # Init UI
    app = QApplication(sys.argv)
    app.setOrganizationName("Antigravity")
    app.setApplicationName(Config.APP_NAME)
    app.setQuitOnLastWindowClosed(False) # Keep running when minimized
    
    icon_path = os.path.join(os.path.dirname(__file__), "ui/assets/rclone_logo.png")
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)

    engine = QQmlApplicationEngine() 
    
    # ViewModels
    main_vm = MainViewModel(client, settings_manager)
    wizard_vm = WizardViewModel(client, settings_manager, autostart_manager)
    sync_vm = SyncViewModel(sync_manager, client)
    settings_vm = SettingsViewModel(settings_manager, client, autostart_manager)
    
    engine.rootContext().setContextProperty("mainViewModel", main_vm)
    engine.rootContext().setContextProperty("wizardViewModel", wizard_vm)
    engine.rootContext().setContextProperty("syncViewModel", sync_vm)
    engine.rootContext().setContextProperty("settingsViewModel", settings_vm)

    # Load QML
    qml_file = QUrl.fromLocalFile("src/ui/qml/Main.qml")
    engine.load(qml_file)

    if not engine.rootObjects():
        sys.exit(-1)
        
    # Get Window reference and Setup Tray
    root_window = engine.rootObjects()[0]
    main_vm.set_window(root_window)
    
    tray = setup_tray(app, icon_path, main_vm)

    # Check for Start Minimized preference
    if settings_manager.get_start_minimized():
        logging.info("Starting minimized to tray.")
        root_window.hide()
    else:
        root_window.show()

    # Trigger Sync All
    sync_vm.sync_all_on_startup()
    
    # Cleanup logic...

    # Cleanup on exit
    def cleanup(*args):
        pm.stop_daemon()
        app.quit()
        
    signal.signal(signal.SIGINT, cleanup)
    app.aboutToQuit.connect(pm.stop_daemon)
    
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
