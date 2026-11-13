use std::collections::HashMap;
use std::process::Stdio;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::process::Command;
use tokio::time::timeout;
use tracing::{debug, error};

use super::config::{augmented_path_env, resolve_binary};

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct AboutQuota {
    pub total: Option<u64>,
    pub used: Option<u64>,
    pub free: Option<u64>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct MountPointInfo {
    #[serde(rename = "Fs", default)]
    pub fs: String,
    #[serde(rename = "MountPoint", default)]
    pub mount_point: String,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TransferItem {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub size: u64,
    #[serde(default)]
    pub bytes: u64,
    #[serde(default)]
    pub percentage: f64,
    #[serde(default)]
    pub speed: f64,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct TransferredItem {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub size: u64,
    #[serde(default)]
    pub bytes: u64,
    #[serde(default)]
    pub error: String,
    #[serde(default, rename = "completed_at")]
    pub completed_at: String,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct CoreStats {
    #[serde(default)]
    pub speed: f64,
    #[serde(default)]
    pub bytes: u64,
    #[serde(default)]
    pub errors: u64,
    #[serde(default)]
    pub transferring: Vec<TransferItem>,
    #[serde(default)]
    pub transferred: Vec<TransferredItem>,
}

#[derive(Debug, Deserialize)]
struct ListRemotesResponse {
    #[serde(default)]
    remotes: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct ListMountsResponse {
    #[serde(rename = "mountPoints", default)]
    mount_points: Vec<MountPointInfo>,
}

/// Async HTTP client for Rclone's Remote Control (`rclone rcd`) API.
#[derive(Debug, Clone)]
pub struct RcloneClient {
    base_url: String,
    user: String,
    password: String,
    http: Client,
}

impl RcloneClient {
    pub fn new(base_url: &str, user: &str, password: &str) -> Self {
        let http = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .unwrap_or_else(|_| Client::new());

        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            user: user.to_string(),
            password: password.to_string(),
            http,
        }
    }

    /// Sends a JSON `POST` request to `{base_url}/{endpoint}` with Basic Auth if configured.
    pub async fn rc_call(&self, endpoint: &str, params: Option<Value>) -> Result<Value> {
        let endpoint_clean = endpoint.trim_start_matches('/');
        let url = format!("{}/{}", self.base_url, endpoint_clean);
        let body = params.unwrap_or_else(|| json!({}));

        let mut req = self.http.post(&url).json(&body);
        if !self.user.is_empty() && !self.password.is_empty() {
            req = req.basic_auth(&self.user, Some(&self.password));
        }

        let resp = req
            .send()
            .await
            .with_context(|| format!("Failed to reach rclone RC endpoint {url}"))?;

        let status = resp.status();
        let text = resp
            .text()
            .await
            .context("Failed reading rclone RC response body")?;

        if !status.is_success() {
            error!("Rclone RC API error ({status}) at {endpoint_clean}: {text}");
            bail!("Rclone RC API error ({status}): {text}");
        }

        if text.trim().is_empty() {
            return Ok(json!({}));
        }

        serde_json::from_str(&text)
            .with_context(|| format!("Invalid JSON response from rclone RC {endpoint_clean}"))
    }

    pub async fn noop(&self) -> Result<bool> {
        match self.rc_call("rc/noop", None).await {
            Ok(_) => Ok(true),
            Err(err) => {
                debug!("Rclone RC noop failed: {err}");
                Ok(false)
            }
        }
    }

    pub async fn version(&self) -> Result<Value> {
        self.rc_call("core/version", None).await
    }

    pub async fn list_remotes(&self) -> Result<Vec<String>> {
        let val = self.rc_call("config/listremotes", None).await?;
        let parsed: ListRemotesResponse =
            serde_json::from_value(val).context("Failed to parse config/listremotes response")?;
        Ok(parsed.remotes)
    }

    pub async fn config_dump(&self) -> Result<HashMap<String, Value>> {
        let val = self
            .rc_call("config/dump", Some(json!({ "long": true })))
            .await?;
        serde_json::from_value(val).context("Failed to parse config/dump response")
    }

    pub async fn about(&self, fs: &str) -> Result<AboutQuota> {
        let val = self
            .rc_call("operations/about", Some(json!({ "fs": fs })))
            .await?;
        serde_json::from_value(val).context("Failed to parse operations/about response")
    }

    pub async fn list_mounts(&self) -> Result<Vec<MountPointInfo>> {
        let val = self.rc_call("mount/listmounts", None).await?;
        let parsed: ListMountsResponse =
            serde_json::from_value(val).context("Failed to parse mount/listmounts response")?;
        Ok(parsed.mount_points)
    }

    pub async fn core_stats(&self) -> Result<CoreStats> {
        let val = self.rc_call("core/stats", None).await?;
        serde_json::from_value(val).context("Failed to parse core/stats response")
    }

    pub async fn config_create(
        &self,
        name: &str,
        remote_type: &str,
        parameters: &Value,
    ) -> Result<()> {
        self.rc_call(
            "config/create",
            Some(json!({
                "name": name,
                "type": remote_type,
                "parameters": parameters,
            })),
        )
        .await?;
        Ok(())
    }

    pub async fn config_update(
        &self,
        name: &str,
        parameters: &Value,
        opt: Option<&Value>,
    ) -> Result<()> {
        let mut payload = json!({
            "name": name,
            "parameters": parameters,
        });
        if let Some(options) = opt {
            payload["opt"] = options.clone();
        }
        self.rc_call("config/update", Some(payload)).await?;
        Ok(())
    }

    pub async fn config_delete(&self, name: &str) -> Result<()> {
        self.rc_call("config/delete", Some(json!({ "name": name })))
            .await?;
        Ok(())
    }
}

/// Extracts and validates the JSON OAuth token object from `rclone authorize` stdout.
pub fn extract_oauth_token_json(stdout: &str) -> Result<String> {
    let trimmed = stdout.trim();
    if serde_json::from_str::<Value>(trimmed).is_ok() && trimmed.starts_with('{') {
        return Ok(trimmed.to_string());
    }

    let start = trimmed
        .find('{')
        .ok_or_else(|| anyhow!("No JSON object found in rclone authorize output"))?;
    let end = trimmed
        .rfind('}')
        .ok_or_else(|| anyhow!("Unterminated JSON object in rclone authorize output"))?;

    if end < start {
        bail!("Malformed JSON braces in rclone authorize output");
    }

    let candidate = &trimmed[start..=end];
    serde_json::from_str::<Value>(candidate).context("Extracted OAuth token is not valid JSON")?;
    Ok(candidate.to_string())
}

/// Runs `rclone authorize drive [client_id] [client_secret]` and extracts the JSON token.
pub async fn authorize_drive(
    client_id: Option<&str>,
    client_secret: Option<&str>,
    timeout_secs: u64,
) -> Result<String> {
    let rclone_bin = resolve_binary("rclone");
    let mut cmd = Command::new(rclone_bin);
    cmd.env("PATH", augmented_path_env())
        .arg("authorize")
        .arg("drive")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);

    if let Some(id) = client_id.filter(|s| !s.is_empty()) {
        cmd.arg(id);
        if let Some(secret) = client_secret.filter(|s| !s.is_empty()) {
            cmd.arg(secret);
        }
    }

    let child = cmd
        .spawn()
        .context("Failed to spawn `rclone authorize drive`")?;

    let output = timeout(Duration::from_secs(timeout_secs), child.wait_with_output())
        .await
        .map_err(|_| anyhow!("Authorization timed out after {timeout_secs}s"))?
        .context("Failed waiting for `rclone authorize drive`")?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("Authorization failed: {}", stderr.trim());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    extract_oauth_token_json(&stdout)
}

/// Formats a byte count into binary IEC units (`B`, `KiB`, `MiB`, `GiB`, `TiB`).
pub fn format_bytes(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KiB", "MiB", "GiB", "TiB"];
    if bytes < 1024 {
        return format!("{bytes} B");
    }

    let mut value = bytes as f64;
    let mut idx = 0;
    while value >= 1024.0 && idx < UNITS.len() - 1 {
        value /= 1024.0;
        idx += 1;
    }
    format!("{value:.1} {}", UNITS[idx])
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    async fn spawn_mock_rc_server() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind mock");
        let addr = listener.local_addr().expect("local addr");

        tokio::spawn(async move {
            loop {
                let Ok((mut socket, _)) = listener.accept().await else {
                    break;
                };
                tokio::spawn(async move {
                    let mut buf = [0u8; 4096];
                    let Ok(n) = socket.read(&mut buf).await else {
                        return;
                    };
                    let req = String::from_utf8_lossy(&buf[..n]);
                    let first_line = req.lines().next().unwrap_or("");
                    let has_basic_auth = req.lines().any(|line| {
                        line.to_ascii_lowercase()
                            .starts_with("authorization: basic ")
                    });

                    let (status, body) = if !has_basic_auth {
                        ("401 Unauthorized", r#"{"error":"unauthorized"}"#)
                    } else if first_line.starts_with("POST /rc/noop ") {
                        ("200 OK", r#"{}"#)
                    } else if first_line.starts_with("POST /config/listremotes ") {
                        ("200 OK", r#"{"remotes":["gdrive","work"]}"#)
                    } else if first_line.starts_with("POST /operations/about ") {
                        (
                            "200 OK",
                            r#"{"total":16106127360,"used":2147483648,"free":13958643712}"#,
                        )
                    } else if first_line.starts_with("POST /core/stats ") {
                        (
                            "200 OK",
                            r#"{"speed":1024.5,"bytes":4096,"errors":0,"transferring":[{"name":"doc.pdf","size":1000,"bytes":500,"percentage":50.0,"speed":512.0}],"transferred":[]}"#,
                        )
                    } else {
                        ("404 Not Found", r#"{"error":"not found"}"#)
                    };

                    let resp = format!(
                        "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                        body.len()
                    );
                    let _ = socket.write_all(resp.as_bytes()).await;
                });
            }
        });

        format!("http://{addr}")
    }

    #[tokio::test]
    async fn rc_client_parses_endpoints_with_basic_auth() {
        let base_url = spawn_mock_rc_server().await;
        let client = RcloneClient::new(&base_url, "rclone", "test_rc_credential");

        assert!(client.noop().await.expect("noop"));
        assert_eq!(
            client.list_remotes().await.expect("list_remotes"),
            vec!["gdrive".to_string(), "work".to_string()]
        );

        let quota = client.about("gdrive:").await.expect("about");
        assert_eq!(quota.total, Some(16_106_127_360));
        assert_eq!(quota.used, Some(2_147_483_648));

        let stats = client.core_stats().await.expect("core_stats");
        assert_eq!(stats.bytes, 4096);
        assert_eq!(stats.transferring.len(), 1);
        assert_eq!(stats.transferring[0].name, "doc.pdf");

        let unauth = RcloneClient::new(&base_url, "", "");
        assert!(!unauth.noop().await.expect("unauth noop"));
    }

    #[test]
    fn extracts_oauth_token_json_from_noisy_stdout() {
        let sample = "Paste the following into your remote machine --->\n{\"access_token\":\"abc\",\"expiry\":\"2026-01-01T00:00:00Z\"}\n<---End paste\n";
        let extracted = extract_oauth_token_json(sample).expect("extract token");
        assert_eq!(
            extracted,
            "{\"access_token\":\"abc\",\"expiry\":\"2026-01-01T00:00:00Z\"}"
        );

        assert!(extract_oauth_token_json("no json here").is_err());
        assert!(extract_oauth_token_json("{not valid json}").is_err());
    }

    #[test]
    fn formats_bytes_human_readably() {
        assert_eq!(format_bytes(512), "512 B");
        assert_eq!(format_bytes(1024), "1.0 KiB");
        assert_eq!(format_bytes(2 * 1024 * 1024), "2.0 MiB");
        assert_eq!(format_bytes(3 * 1024 * 1024 * 1024), "3.0 GiB");
    }
}
