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
from core.sync_manager import SyncManager
from core.settings_manager import SettingsManager
from core.autostart_manager import AutostartManager
from core.config import Config
from core.mount_manager import MountManager
from ui.viewmodels.main_vm import MainViewModel
from ui.viewmodels.wizard_vm import WizardViewModel
from ui.viewmodels.sync_vm import SyncViewModel
from ui.viewmodels.settings_vm import SettingsViewModel
from ui.viewmodels.activity_vm import ActivityViewModel

def setup_tray(app, icon_path, main_vm):
    tray_icon = QSystemTrayIcon(QIcon(icon_path), app)
    menu = QMenu()

    action_show = QAction("Show Manager", menu)
    action_show.triggered.connect(main_vm.show_window)

    action_hide = QAction("Hide", menu)
    action_hide.triggered.connect(main_vm.hide_window)

    menu.addSeparator()

    action_quit = QAction("Exit", menu)
    action_quit.triggered.connect(main_vm.quit_app)

    menu.addAction(action_show)
    menu.addAction(action_hide)
    menu.addSeparator()
    menu.addAction(action_quit)

    tray_icon.setContextMenu(menu)
    tray_icon.show()
    return tray_icon

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Main")

    # Single Instance Check
    from core.single_instance import SingleInstanceCheck
    lock = SingleInstanceCheck()
    if lock.is_running():
        logger.error("Application is already running. Exiting.")
        return 1

    # Init Backend
    rc_password = Config.get_rc_pass()
    pm = RcloneProcessManager(
        rc_addr=Config.RC_ADDR,
        rc_user=Config.RC_USER,
        rc_pass=rc_password,
        rc_conf=Config.RCLONE_CONF
    )
    if not pm.start_daemon():
        print("Warning: Could not start rclone daemon. Is rclone installed?")

    client = RcloneClient(
        url=Config.get_rc_url(),
        user=Config.RC_USER,
        password=rc_password
    )

    sync_manager = SyncManager()
    settings_manager = SettingsManager()
    autostart_manager = AutostartManager()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon_path = os.path.join(os.path.dirname(__file__), "ui/assets/rclone_logo.png")
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)

    engine = QQmlApplicationEngine()

    start_minimized_arg = "--minimized" in sys.argv
    if start_minimized_arg:
        logging.info("Startup flag --minimized detected.")

    # ViewModels
    main_vm = MainViewModel(client, settings_manager, sync_manager)
    wizard_vm = WizardViewModel(client, settings_manager, autostart_manager)
    sync_vm = SyncViewModel(sync_manager, client)
    settings_vm = SettingsViewModel(settings_manager, client, autostart_manager)
    activity_vm = ActivityViewModel(client, sync_vm)

    # Wire credential changes to dashboard refresh (transparent UI update)
    settings_vm.credentialStatusChanged.connect(main_vm.refresh_remotes)

    # UI Engine
    engine.rootContext().setContextProperty("mainViewModel", main_vm)
    engine.rootContext().setContextProperty("main_vm", main_vm)
    engine.rootContext().setContextProperty("wizardViewModel", wizard_vm)
    engine.rootContext().setContextProperty("syncViewModel", sync_vm)
    engine.rootContext().setContextProperty("sync_vm", sync_vm)
    engine.rootContext().setContextProperty("settingsViewModel", settings_vm)
    engine.rootContext().setContextProperty("settings_vm", settings_vm)
    engine.rootContext().setContextProperty("activityViewModel", activity_vm)
    engine.rootContext().setContextProperty("activity_vm", activity_vm)

    engine.load(QUrl.fromLocalFile("src/ui/qml/Main.qml"))

    if not engine.rootObjects():
        sys.exit(-1)

    # Setup Tray with a slight delay to avoid DBus race conditions in Plasma 6
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1500, lambda: setup_tray(app, icon_path, main_vm))

    # Get Window reference and Setup Tray
    root_window = engine.rootObjects()[0]
    main_vm.set_window(root_window)

    # Check for Start Minimized preference
    if settings_manager.get_start_minimized() or start_minimized_arg:
        logging.info("Starting minimized to tray.")
        root_window.hide()
    else:
        root_window.show()

    # Trigger Sync All
    sync_vm.sync_all_on_startup()

    # Initialize Mount Manager for global cleanup
    mm = MountManager(client)
    mm.cleanup_all()

    # Cleanup on exit
    def cleanup(*args):
        mm.cleanup_all()
        pm.stop_daemon()
        app.quit()

    signal.signal(signal.SIGINT, cleanup)
    app.aboutToQuit.connect(pm.stop_daemon)

    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
