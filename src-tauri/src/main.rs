#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::menu::Menu;
use tauri_plugin_dialog::DialogExt;

const MAX_EXPORT_BYTES: usize = 128 * 1024 * 1024;
const MAX_EXPORT_HEADER_BYTES: usize = 4 * 1024;

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct ExportHeader {
    filename: String,
}

fn local_origin(scheme: &str, host: Option<&str>) -> bool {
    (scheme == "tauri" && host == Some("localhost"))
        || (matches!(scheme, "http" | "https") && host == Some("tauri.localhost"))
}

fn require_local(window: &tauri::WebviewWindow) -> Result<(), String> {
    let url = window.url().map_err(|error| error.to_string())?;
    if window.label() == "main" && local_origin(url.scheme(), url.host_str()) {
        Ok(())
    } else {
        Err("Only the local Synth window can use desktop commands".into())
    }
}

// Raw IPC carries a short length-prefixed JSON header and the original bytes.
fn parse_export_packet(packet: &[u8]) -> Result<(String, &[u8]), String> {
    let length = packet
        .first_chunk::<4>()
        .ok_or("Export packet is missing its header length")?;
    let header_bytes = u32::from_le_bytes(*length) as usize;
    if !(1..=MAX_EXPORT_HEADER_BYTES).contains(&header_bytes) {
        return Err("Export header must contain 1..4096 bytes".into());
    }
    let data_offset = length.len() + header_bytes;
    if data_offset > packet.len() {
        return Err("Export packet contains a truncated header".into());
    }
    let bytes = &packet[data_offset..];
    if bytes.len() > MAX_EXPORT_BYTES {
        return Err("Export exceeds 128 MiB".into());
    }
    let header: ExportHeader = serde_json::from_slice(&packet[length.len()..data_offset])
        .map_err(|error| format!("Invalid export header: {error}"))?;
    let name: String = header
        .filename
        .rsplit(['/', '\\'])
        .next()
        .unwrap_or("")
        .chars()
        .filter(|character| !character.is_control())
        .take(160)
        .collect();
    let filename = match name.as_str() {
        "" | "." | ".." => "export.bin".into(),
        _ => name,
    };
    Ok((filename, bytes))
}

#[tauri::command]
async fn save_export_binary(
    window: tauri::WebviewWindow,
    request: tauri::ipc::Request<'_>,
) -> Result<Option<String>, String> {
    require_local(&window)?;
    let tauri::ipc::InvokeBody::Raw(packet) = request.body() else {
        return Err("Export requires a binary file packet".into());
    };
    let (filename, bytes) = parse_export_packet(packet)?;
    let bytes = bytes.to_vec();
    tauri::async_runtime::spawn_blocking(move || {
        let chosen = window
            .dialog()
            .file()
            .set_parent(&window)
            .set_file_name(&filename)
            .blocking_save_file();
        let Some(chosen) = chosen else {
            return Ok(None);
        };
        let path = chosen.into_path().map_err(|error| error.to_string())?;
        std::fs::write(&path, bytes).map_err(|error| error.to_string())?;
        Ok(Some(path.to_string_lossy().into_owned()))
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
fn reload_window(window: tauri::WebviewWindow) -> Result<(), String> {
    require_local(&window)?;
    window.reload().map_err(|error| error.to_string())
}

#[tauri::command]
fn window_pin_state(window: tauri::WebviewWindow) -> Result<bool, String> {
    require_local(&window)?;
    window.is_always_on_top().map_err(|error| error.to_string())
}

#[tauri::command]
async fn set_window_pin(window: tauri::WebviewWindow, pinned: bool) -> Result<bool, String> {
    require_local(&window)?;
    tauri::async_runtime::spawn_blocking(move || {
        window
            .set_always_on_top(pinned)
            .map_err(|error| error.to_string())?;
        // Tao queues macOS window level changes on the main thread.
        for attempt in 0..100 {
            if window
                .is_always_on_top()
                .map_err(|error| error.to_string())?
                == pinned
            {
                return Ok(pinned);
            }
            if attempt < 99 {
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
        }
        Err("Window pin state did not change".into())
    })
    .await
    .map_err(|error| error.to_string())?
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri::plugin::Builder::<tauri::Wry>::new("synth-desktop")
                .js_init_script(include_str!("../../desktop/desktop-interface.js"))
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            save_export_binary,
            reload_window,
            window_pin_state,
            set_window_pin,
        ])
        .setup(|app| {
            tauri::WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?.build()?;
            app.set_menu(Menu::default(app.handle())?)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Tetorica Nitro DS Synth");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn desktop_commands_accept_only_packaged_origins() {
        assert!(local_origin("tauri", Some("localhost")));
        assert!(local_origin("http", Some("tauri.localhost")));
        assert!(local_origin("https", Some("tauri.localhost")));
        assert!(!local_origin("tauri", Some("remote")));
        assert!(!local_origin("http", Some("localhost")));
        assert!(!local_origin("https", Some("example.com")));
    }

    #[test]
    fn binary_export_borrows_bytes_and_keeps_only_the_filename() {
        let header =
            serde_json::to_vec(&serde_json::json!({"filename": "../音色.cassette.zip"})).unwrap();
        let mut packet = (header.len() as u32).to_le_bytes().to_vec();
        packet.extend_from_slice(&header);
        packet.extend_from_slice(&[0, 255, 128]);
        let (name, bytes) = parse_export_packet(&packet).unwrap();
        assert_eq!(name, "音色.cassette.zip");
        assert_eq!(bytes, [0, 255, 128]);
        assert_eq!(bytes.as_ptr(), packet[4 + header.len()..].as_ptr());
    }

    #[test]
    fn binary_export_rejects_invalid_headers() {
        assert!(parse_export_packet(&[0; 3]).is_err());
        assert!(parse_export_packet(&[0; 4]).is_err());
        assert!(parse_export_packet(&u32::MAX.to_le_bytes()).is_err());
        assert!(parse_export_packet(&[8, 0, 0, 0, b'{', b'}']).is_err());
        let header = br#"{"filename":"sample.wav","path":"/tmp"}"#;
        let mut packet = (header.len() as u32).to_le_bytes().to_vec();
        packet.extend_from_slice(header);
        assert!(parse_export_packet(&packet).is_err());
    }
}
