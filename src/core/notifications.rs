use std::thread;

use notify_rust::{Notification, Timeout, Urgency};
use tracing::debug;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UrgencyLevel {
    Low,
    Normal,
    Critical,
}

impl From<UrgencyLevel> for Urgency {
    fn from(level: UrgencyLevel) -> Self {
        match level {
            UrgencyLevel::Low => Urgency::Low,
            UrgencyLevel::Normal => Urgency::Normal,
            UrgencyLevel::Critical => Urgency::Critical,
        }
    }
}

/// Sends a desktop notification over D-Bus without blocking the caller thread.
/// Failures in headless environments are logged at debug level and ignored.
pub fn send_notification(title: &str, body: &str, urgency: UrgencyLevel) {
    let title_owned = title.to_string();
    let body_owned = body.to_string();

    thread::spawn(move || {
        let res = Notification::new()
            .appname("Rclone Manager")
            .summary(&title_owned)
            .body(&body_owned)
            .urgency(urgency.into())
            .timeout(Timeout::Milliseconds(10_000))
            .show();

        if let Err(err) = res {
            debug!("Desktop notification failed (expected in headless env): {err}");
        }
    });
}
