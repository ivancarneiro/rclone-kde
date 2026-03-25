import keyring
import secrets
import logging
import os

class Config:
    APP_NAME = "RcloneKDE"
    VERSION = "1.2.1"
    
    # Rclone RC Defaults
    RC_ADDR = "localhost:5572"
    RC_USER = "rclone"
    
    # Secure Password Retrieval
    _SERVICE_ID = "RcloneKDE"
    _USER_ID = "rc_pass"
    
    @property
    def RC_PASS(self):
        # Intentar obtener del keyring
        try:
            password = keyring.get_password(Config._SERVICE_ID, Config._USER_ID)
            if password:
                return password
            
            # Si no existe, generar nuevo y guardar
            logging.info("Generating new secure Rclone RC password...")
            new_pass = secrets.token_hex(16)
            keyring.set_password(Config._SERVICE_ID, Config._USER_ID, new_pass)
            return new_pass
            
        except Exception as e:
            logging.warning(f"Keyring failed: {e}. Using temporary memory password.")
            if not hasattr(Config, "_temp_pass"):
                Config._temp_pass = secrets.token_hex(16)
            return Config._temp_pass

    # Para acceder como propiedad estática, instanciamos o usamos classmethod.
    # Dado que era estática antes, hagamos un getter estático o "class property"
    
    @classmethod
    def get_rc_pass(cls):
        # Simple wrapper for the property logic above adapted to class context
        # Or just implement logic here
        try:
            password = keyring.get_password(cls._SERVICE_ID, cls._USER_ID)
            if password:
                return password
            
            new_pass = secrets.token_hex(16)
            keyring.set_password(cls._SERVICE_ID, cls._USER_ID, new_pass)
            return new_pass
        except Exception as e:
            logging.warning(f"Keyring error: {e}")
            return "temporary_secure_password_fallback"

    # Rutas
    HOME_DIR = os.path.expanduser("~")
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Production: Use system standard configuration
    # This allows the app to see existing user remotes.
    RCLONE_CONF = os.path.join(HOME_DIR, ".config", "rclone", "rclone.conf")
    mount_dir = os.path.join(HOME_DIR, "RcloneMounts")

    @staticmethod
    def get_rc_url():
        return f"http://{Config.RC_ADDR}"
