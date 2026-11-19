use std::collections::HashMap;
use std::sync::Mutex;
use std::thread;

use anyhow::{Context, Result, anyhow};
use tracing::{info, warn};

use super::config::{KEYRING_SERVICE, generate_random_hex_16};

const RC_PASS_KEY: &str = "rc_pass";
const GOOGLE_CLIENT_ID_KEY: &str = "google_client_id";
const GOOGLE_CLIENT_SECRET_KEY: &str = "google_client_secret";

/// Stored Google OAuth credentials.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GoogleCredentials {
    pub client_id: String,
    pub client_secret: String,
}

/// Storage backend abstraction for sensitive credentials.
pub trait SecretStore: Send + Sync {
    fn get(&self, key: &str) -> Result<Option<String>>;
    fn set(&self, key: &str, value: &str) -> Result<()>;
    fn delete(&self, key: &str) -> Result<()>;
}

/// System keyring backend backed by Secret Service / KDE Wallet under `"RcloneKDE"`.
#[derive(Debug, Default, Clone, Copy)]
pub struct KeyringSecretStore;

impl KeyringSecretStore {
    fn run_on_dedicated_thread<F, T>(op: F) -> Result<T>
    where
        F: FnOnce() -> Result<T> + Send + 'static,
        T: Send + 'static,
    {
        // `keyring` with `async-secret-service` + `tokio` uses an internal runtime
        // that can deadlock if invoked directly on a Tokio thread.
        thread::spawn(op)
            .join()
            .map_err(|_| anyhow!("Keyring worker thread panicked"))?
    }
}

impl SecretStore for KeyringSecretStore {
    fn get(&self, key: &str) -> Result<Option<String>> {
        let key_owned = key.to_string();
        Self::run_on_dedicated_thread(move || {
            let entry = keyring::Entry::new(KEYRING_SERVICE, &key_owned)
                .context("Failed to create keyring entry")?;
            match entry.get_password() {
                Ok(secret) => Ok(Some(secret)),
                Err(keyring::Error::NoEntry) => Ok(None),
                Err(err) => Err(err).context("Failed to read secret from keyring"),
            }
        })
    }

    fn set(&self, key: &str, value: &str) -> Result<()> {
        let key_owned = key.to_string();
        let value_owned = value.to_string();
        Self::run_on_dedicated_thread(move || {
            let entry = keyring::Entry::new(KEYRING_SERVICE, &key_owned)
                .context("Failed to create keyring entry")?;
            entry
                .set_password(&value_owned)
                .context("Failed to store secret in keyring")
        })
    }

    fn delete(&self, key: &str) -> Result<()> {
        let key_owned = key.to_string();
        Self::run_on_dedicated_thread(move || {
            let entry = keyring::Entry::new(KEYRING_SERVICE, &key_owned)
                .context("Failed to create keyring entry")?;
            match entry.delete_credential() {
                Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
                Err(err) => Err(err).context("Failed to delete secret from keyring"),
            }
        })
    }
}

/// In-memory secret store for deterministic unit testing.
#[derive(Debug, Default)]
pub struct InMemorySecretStore {
    entries: Mutex<HashMap<String, String>>,
    fail_operations: bool,
}

impl InMemorySecretStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn failing() -> Self {
        Self {
            entries: Mutex::new(HashMap::new()),
            fail_operations: true,
        }
    }
}

impl SecretStore for InMemorySecretStore {
    fn get(&self, key: &str) -> Result<Option<String>> {
        if self.fail_operations {
            return Err(anyhow!("Simulated keyring failure"));
        }
        let guard = self.entries.lock().expect("lock poisoned");
        Ok(guard.get(key).cloned())
    }

    fn set(&self, key: &str, value: &str) -> Result<()> {
        if self.fail_operations {
            return Err(anyhow!("Simulated keyring failure"));
        }
        let mut guard = self.entries.lock().expect("lock poisoned");
        guard.insert(key.to_string(), value.to_string());
        Ok(())
    }

    fn delete(&self, key: &str) -> Result<()> {
        if self.fail_operations {
            return Err(anyhow!("Simulated keyring failure"));
        }
        let mut guard = self.entries.lock().expect("lock poisoned");
        guard.remove(key);
        Ok(())
    }
}

/// High-level credential lifecycle manager for Rclone RC and Google OAuth.
#[derive(Debug)]
pub struct SecretManager<S: SecretStore = KeyringSecretStore> {
    store: S,
}

impl SecretManager<KeyringSecretStore> {
    pub fn system() -> Self {
        Self {
            store: KeyringSecretStore,
        }
    }
}

impl<S: SecretStore> SecretManager<S> {
    pub fn new(store: S) -> Self {
        Self { store }
    }

    /// Retrieves the persisted RC password or generates/persists a new 16-byte hex token.
    /// Falls back to an ephemeral token in memory if the system keyring is unavailable.
    pub fn get_or_create_rc_pass(&self) -> String {
        match self.store.get(RC_PASS_KEY) {
            Ok(Some(existing)) if !existing.is_empty() => return existing,
            Ok(_) => {}
            Err(err) => {
                warn!("Keyring read failed for rc_pass: {err}. Using ephemeral password.");
                return generate_random_hex_16()
                    .unwrap_or_else(|_| "ephemeral_rclone_rc_fallback".to_string());
            }
        }

        info!("Generating new Rclone RC password...");
        let generated =
            generate_random_hex_16().unwrap_or_else(|_| "ephemeral_rclone_rc_fallback".to_string());

        if let Err(err) = self.store.set(RC_PASS_KEY, &generated) {
            warn!("Could not persist rc_pass in keyring: {err}. Continuing with memory password.");
        }
        generated
    }

    /// Reads stored Google OAuth credentials, returning `None` if absent or incomplete.
    pub fn get_google_credentials(&self) -> Option<GoogleCredentials> {
        let client_id = match self.store.get(GOOGLE_CLIENT_ID_KEY) {
            Ok(Some(val)) if !val.is_empty() => val,
            Ok(_) => return None,
            Err(err) => {
                warn!("Failed to read Google client_id from keyring: {err}");
                return None;
            }
        };

        let client_secret = match self.store.get(GOOGLE_CLIENT_SECRET_KEY) {
            Ok(Some(val)) if !val.is_empty() => val,
            Ok(_) => return None,
            Err(err) => {
                warn!("Failed to read Google client_secret from keyring: {err}");
                return None;
            }
        };

        Some(GoogleCredentials {
            client_id,
            client_secret,
        })
    }

    pub fn save_google_credentials(&self, client_id: &str, client_secret: &str) -> Result<()> {
        self.store.set(GOOGLE_CLIENT_ID_KEY, client_id)?;
        self.store.set(GOOGLE_CLIENT_SECRET_KEY, client_secret)?;
        info!("Google OAuth credentials saved to secret store.");
        Ok(())
    }

    pub fn has_google_credentials(&self) -> bool {
        self.get_google_credentials().is_some()
    }

    pub fn delete_google_credentials(&self) -> Result<()> {
        self.store.delete(GOOGLE_CLIENT_ID_KEY)?;
        self.store.delete(GOOGLE_CLIENT_SECRET_KEY)?;
        info!("Google OAuth credentials deleted from secret store.");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_and_persists_rc_pass_once() {
        let manager = SecretManager::new(InMemorySecretStore::new());

        let first = manager.get_or_create_rc_pass();
        let second = manager.get_or_create_rc_pass();

        assert_eq!(first.len(), 32);
        assert_eq!(first, second);
    }

    #[test]
    fn falls_back_gracefully_when_keyring_fails() {
        let manager = SecretManager::new(InMemorySecretStore::failing());

        let token = manager.get_or_create_rc_pass();
        assert!(!token.is_empty());
        assert!(!manager.has_google_credentials());
    }

    #[test]
    fn manages_google_credentials_crud_lifecycle() {
        let manager = SecretManager::new(InMemorySecretStore::new());
        assert!(!manager.has_google_credentials());
        assert_eq!(manager.get_google_credentials(), None);

        manager
            .save_google_credentials("test_id_alpha", "test_val_beta")
            .expect("save credentials");

        assert!(manager.has_google_credentials());
        assert_eq!(
            manager.get_google_credentials(),
            Some(GoogleCredentials {
                client_id: "test_id_alpha".to_string(),
                client_secret: "test_val_beta".to_string(),
            })
        );

        manager
            .delete_google_credentials()
            .expect("delete credentials");
        assert!(!manager.has_google_credentials());
        assert_eq!(manager.get_google_credentials(), None);
        // Deleting again must remain idempotent
        manager
            .delete_google_credentials()
            .expect("idempotent delete");
    }
}
