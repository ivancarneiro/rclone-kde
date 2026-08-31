import sys
import os
import pytest
import asyncio
from unittest.mock import MagicMock, patch

# Añadir src al path para poder importar
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.settings_manager import SettingsManager
from core.rclone_client import RcloneClient
from ui.viewmodels.main_vm import MainViewModel

def test_settings_manager_keepassxc():
    """Verifica que SettingsManager maneja correctamente la config de KeePassXC."""
    sm = SettingsManager()
    sm.set_keepassxc_config("test_remote", "test.kdbx")
    config = sm.get_keepassxc_config()
    assert config["remote"] == "test_remote"
    assert config["db_path"] == "test.kdbx"

@pytest.mark.asyncio
async def test_rclone_client_resilience():
    """Verifica que RcloneClient no explota si el daemon no está listo."""
    # Usamos un puerto que probablemente no esté escuchando
    client = RcloneClient(url="http://localhost:12345")
    result = await client.noop()
    assert "error" in result
    assert result["error"] == "connection_failed"

def test_main_vm_os_module_fix():
    """Verifica que el módulo 'os' está disponible en MainViewModel (NameError fix)."""
    # Mockear dependencias de MainViewModel
    mock_client = MagicMock()
    mock_settings = MagicMock()
    mock_sync = MagicMock()
    mock_mount = MagicMock()
    
    with patch('ui.viewmodels.main_vm.Config'), \
         patch('ui.viewmodels.main_vm.MountWorker'), \
         patch('ui.viewmodels.main_vm.StatusWorker'), \
         patch('ui.viewmodels.main_vm.NotificationManager'):
        
        vm = MainViewModel(mock_client, mock_settings, mock_sync, mock_mount)
        # Si el error NameError: 'os' no está definido persiste, esto fallará
        # al intentar ejecutar _on_mount_success
        
        result = {
            "remote_name": "ivanexequielc",
            "mount_point": "/tmp/fake_mount",
            "success": True,
            "action": "mount"
        }
        
        # Mockear settings para evitar cargar archivos reales
        vm._settings_manager.get_keepassxc_config = MagicMock(return_value={
            "remote": "ivanexequielc",
            "db_path": "ciex.kdbx"
        })
        
        # Simular que el archivo NO existe para no lanzar el proceso real
        with patch('os.path.exists', return_value=False):
            # Esta llamada fallaba antes por el NameError en 'os.path.join'
            vm._on_mount_success(result)
            # Si llegamos aquí, el NameError está corregido
