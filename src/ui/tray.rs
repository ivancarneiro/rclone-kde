use ksni::menu::StandardItem;
use ksni::{Handle, MenuItem, Tray, TrayMethods};
use tokio::sync::mpsc;
use tracing::{info, warn};

/// Actions triggered by the KDE StatusNotifierItem system tray.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrayAction {
    Show,
    Hide,
    Quit,
}

#[derive(Debug, Clone)]
pub struct RcloneTray {
    tx: mpsc::UnboundedSender<TrayAction>,
}

impl RcloneTray {
    pub fn new(tx: mpsc::UnboundedSender<TrayAction>) -> Self {
        Self { tx }
    }
}

impl Tray for RcloneTray {
    fn id(&self) -> String {
        "rclone-manager".to_string()
    }

    fn title(&self) -> String {
        "Rclone Manager".to_string()
    }

    fn icon_name(&self) -> String {
        "folder-cloud".to_string()
    }

    fn activate(&mut self, _x: i32, _y: i32) {
        let _ = self.tx.send(TrayAction::Show);
    }

    fn menu(&self) -> Vec<MenuItem<Self>> {
        vec![
            MenuItem::Standard(StandardItem {
                label: "Show Manager".to_string(),
                activate: Box::new(|tray: &mut Self| {
                    let _ = tray.tx.send(TrayAction::Show);
                }),
                ..Default::default()
            }),
            MenuItem::Standard(StandardItem {
                label: "Hide".to_string(),
                activate: Box::new(|tray: &mut Self| {
                    let _ = tray.tx.send(TrayAction::Hide);
                }),
                ..Default::default()
            }),
            MenuItem::Separator,
            MenuItem::Standard(StandardItem {
                label: "Exit".to_string(),
                activate: Box::new(|tray: &mut Self| {
                    let _ = tray.tx.send(TrayAction::Quit);
                }),
                ..Default::default()
            }),
        ]
    }
}

/// Spawns the KDE StatusNotifierItem tray over D-Bus. Returns `None` if unavailable.
pub async fn spawn_tray(tx: mpsc::UnboundedSender<TrayAction>) -> Option<Handle<RcloneTray>> {
    match RcloneTray::new(tx).assume_sni_available(true).spawn().await {
        Ok(handle) => {
            info!("System tray registered via StatusNotifierItem (ksni)");
            Some(handle)
        }
        Err(err) => {
            warn!("System tray unavailable over D-Bus: {err}");
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_tray_metadata_and_menu_actions() {
        let (tx, mut rx) = mpsc::unbounded_channel();
        let mut tray = RcloneTray::new(tx);

        assert_eq!(tray.id(), "rclone-manager");
        assert_eq!(tray.title(), "Rclone Manager");
        assert_eq!(tray.icon_name(), "folder-cloud");

        tray.activate(0, 0);
        assert_eq!(rx.try_recv().ok(), Some(TrayAction::Show));

        let items = tray.menu();
        assert_eq!(items.len(), 4);

        if let MenuItem::Standard(ref show_item) = items[0] {
            assert_eq!(show_item.label, "Show Manager");
        } else {
            panic!("expected Show Manager standard item");
        }

        if let MenuItem::Standard(ref hide_item) = items[1] {
            assert_eq!(hide_item.label, "Hide");
        } else {
            panic!("expected Hide standard item");
        }

        assert!(matches!(items[2], MenuItem::Separator));

        if let MenuItem::Standard(ref exit_item) = items[3] {
            assert_eq!(exit_item.label, "Exit");
            (exit_item.activate)(&mut tray);
        } else {
            panic!("expected Exit standard item");
        }

        assert_eq!(rx.try_recv().ok(), Some(TrayAction::Quit));
    }
}
