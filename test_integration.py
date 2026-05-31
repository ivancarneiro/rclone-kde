import os
import sys
import time
import shutil
import logging

# Agregar src al path
sys.path.append(os.path.abspath("src"))

from core.process_manager import RcloneProcessManager
from core.autostart_manager import AutostartManager
from core.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IntegrationTest")

def test_process_lifecycle():
    logger.info(">>> Test: Ciclo de vida del proceso (Daemon)")
    # Usamos una config temporal o la de sistema
    pm = RcloneProcessManager(rc_addr="localhost:5573", rc_user="test", rc_pass="test", rc_conf=Config.RCLONE_CONF)
    
    # 1. Start
    success = pm.start_daemon()
    if not success:
        logger.error("Fallo al iniciar el demonio")
        return False
    
    pid = pm.process.pid
    logger.info(f"Demonio iniciado con PID: {pid}")
    
    # Verificar que el proceso existe
    try:
        os.kill(pid, 0)
    except OSError:
        logger.error("El proceso no está corriendo")
        return False

    # 2. Stop
    pm.stop_daemon()
    time.sleep(1)
    
    # Verificar que el proceso ya no existe
    try:
        os.kill(pid, 0)
        logger.error("El proceso sigue vivo después de stop_daemon")
        return False
    except OSError:
        logger.info("Confirmado: Proceso detenido correctamente")
    
    return True

def test_autostart_logic():
    logger.info(">>> Test: Lógica de Autostart")
    am = AutostartManager()
    
    # Limpiar previo
    am.disable_autostart()
    
    # Enable
    if not am.enable_autostart():
        logger.error("Fallo al habilitar autostart")
        return False
    
    if not am.is_enabled():
        logger.error("Autostart figura como deshabilitado después de habilitar")
        return False
        
    # Verificar contenido
    with open(am.desktop_file, 'r') as f:
        content = f.read()
        logger.info(f"Contenido del .desktop:\n{content}")
        if "main.py" not in content and "rclone-kde" not in content:
            logger.error("Comando Exec inválido en .desktop")
            return False

    # Disable
    am.disable_autostart()
    if am.is_enabled():
        logger.error("Autostart sigue habilitado después de deshabilitar")
        return False

    logger.info("Confirmado: Lógica de autostart validada")
    return True

if __name__ == "__main__":
    results = []
    results.append(("Process Lifecycle", test_process_lifecycle()))
    results.append(("Autostart Logic", test_autostart_logic()))
    
    print("\n" + "="*30)
    print("RESULTADOS DE LOS TESTS")
    print("="*30)
    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
        if not passed: all_passed = False
    
    if not all_passed:
        sys.exit(1)
