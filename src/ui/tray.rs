use std::io::Cursor;
use std::sync::OnceLock;

use ksni::menu::StandardItem;
use ksni::{Handle, Icon, MenuItem, Tray, TrayMethods};
use tokio::sync::mpsc;
use tracing::{info, warn};

const TRAY_ICON_PNG: &[u8] = include_bytes!("../../assets/icon.png");

fn decode_tray_icon_pixmap() -> Vec<Icon> {
    let mut decoder = png::Decoder::new(Cursor::new(TRAY_ICON_PNG));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);

    let Ok(mut reader) = decoder.read_info() else {
        warn!("Failed to read tray icon PNG header");
        return Vec::new();
    };
    let mut rgba = vec![0; reader.output_buffer_size().unwrap_or(0)];
    let Ok(info) = reader.next_frame(&mut rgba) else {
        warn!("Failed to decode tray icon PNG frame");
        return Vec::new();
    };
    rgba.truncate(info.buffer_size());

    let argb = match info.color_type {
        png::ColorType::Rgba => {
            let mut out = Vec::with_capacity(rgba.len());
            for px in rgba.as_chunks::<4>().0 {
                out.extend_from_slice(&[px[3], px[0], px[1], px[2]]);
            }
            out
        }
        png::ColorType::Rgb => {
            let mut out = Vec::with_capacity((rgba.len() / 3) * 4);
            for px in rgba.as_chunks::<3>().0 {
                out.extend_from_slice(&[0xff, px[0], px[1], px[2]]);
            }
            out
        }
        other => {
            warn!("Unsupported tray icon PNG color type: {other:?}");
            return Vec::new();
        }
    };

    vec![Icon {
        width: info.width as i32,
        height: info.height as i32,
        data: argb,
    }]
}

fn tray_icon_pixmap() -> Vec<Icon> {
    static PIXMAP: OnceLock<Vec<Icon>> = OnceLock::new();
    PIXMAP.get_or_init(decode_tray_icon_pixmap).clone()
}

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
        String::new()
    }

    fn icon_pixmap(&self) -> Vec<Icon> {
        tray_icon_pixmap()
    }

    fn activate(&mut self, _x: i32, _y: i32) {
        info!("Tray action: Show main window");
        let _ = self.tx.send(TrayAction::Show);
    }

    fn menu(&self) -> Vec<MenuItem<Self>> {
        vec![
            MenuItem::Standard(StandardItem {
                label: "Show Manager".to_string(),
                activate: Box::new(|tray: &mut Self| {
                    info!("Tray action: Show main window");
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
        assert_eq!(tray.icon_name(), "");
        let pixmap = tray.icon_pixmap();
        assert_eq!(pixmap.len(), 1);
        assert_eq!(pixmap[0].width, 64);
        assert_eq!(pixmap[0].height, 64);
        assert_eq!(pixmap[0].data.len(), 64 * 64 * 4);

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
