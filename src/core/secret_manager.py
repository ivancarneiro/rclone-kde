import keyring
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GoogleCredentials:
    """Represents stored Google OAuth credentials."""
    client_id: str
    client_secret: str


class SecretManager:
    """
    Manages sensitive credentials via the system keyring (KDE Wallet / GNOME Keyring).
    Follows the same pattern as Config.get_rc_pass() in config.py.

    Service/username convention:
      - Service: "RcloneKDE"
      - Username: "google_client_id" / "google_client_secret"
    """

    _SERVICE_ID = "RcloneKDE"
    _CLIENT_ID_KEY = "google_client_id"
    _CLIENT_SECRET_KEY = "google_client_secret"

    # ------------------------------------------------------------------
    # Google OAuth credentials
    # ------------------------------------------------------------------

    @classmethod
    def get_google_credentials(cls) -> Optional[GoogleCredentials]:
        """Retrieve stored Google OAuth credentials from the keyring."""
        try:
            cid = keyring.get_password(cls._SERVICE_ID, cls._CLIENT_ID_KEY)
            secret = keyring.get_password(cls._SERVICE_ID, cls._CLIENT_SECRET_KEY)
            if cid and secret:
                logger.info("Google OAuth credentials loaded from system keyring.")
                return GoogleCredentials(client_id=cid, client_secret=secret)
            logger.info("No Google OAuth credentials found in keyring.")
            return None
        except Exception as e:
            logger.warning(f"Failed to read Google credentials from keyring: {e}")
            return None

    @classmethod
    def save_google_credentials(cls, client_id: str, client_secret: str) -> bool:
        """Persist Google OAuth credentials to the system keyring."""
        try:
            keyring.set_password(cls._SERVICE_ID, cls._CLIENT_ID_KEY, client_id)
            keyring.set_password(cls._SERVICE_ID, cls._CLIENT_SECRET_KEY, client_secret)
            logger.info("Google OAuth credentials saved to system keyring.")
            return True
        except Exception as e:
            logger.warning(f"Failed to save Google credentials to keyring: {e}")
            return False

    @classmethod
    def has_google_credentials(cls) -> bool:
        """Check if Google OAuth credentials exist in the keyring."""
        return cls.get_google_credentials() is not None

    @classmethod
    def delete_google_credentials(cls) -> bool:
        """Remove Google OAuth credentials from the system keyring."""
        try:
            keyring.delete_password(cls._SERVICE_ID, cls._CLIENT_ID_KEY)
            keyring.delete_password(cls._SERVICE_ID, cls._CLIENT_SECRET_KEY)
            logger.info("Google OAuth credentials deleted from system keyring.")
            return True
        except keyring.errors.PasswordDeleteError:
            logger.info("No stored Google credentials to delete.")
            return True  # nothing to delete is still a success
        except Exception as e:
            logger.warning(f"Failed to delete Google credentials from keyring: {e}")
            return False
