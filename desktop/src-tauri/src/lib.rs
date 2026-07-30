//! MLCryptoEngine desktop backend: supervises the Python recorder and telemetry
//! processes, tails their structured logs, reads dataset inventory and status
//! files, and persists user settings. All heavy lifting stays in Python; this
//! shell only orchestrates and reports.

mod inventory;
mod logs;
mod process;
mod settings;

use std::collections::HashSet;
use std::sync::Mutex;

use tauri::{AppHandle, Manager, State, WindowEvent};

use process::{ProcKind, ProcessManager, ProcessStatus};
use settings::Settings;

struct AppState {
    processes: Mutex<ProcessManager>,
    log_streams: Mutex<HashSet<String>>,
}

fn repo_root(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let stored = settings::load(app)?;
    settings::resolve_repo_root(&stored)
}

#[tauri::command]
fn get_settings(app: AppHandle) -> Result<Settings, String> {
    settings::load(&app)
}

#[tauri::command]
fn set_settings(app: AppHandle, new_settings: Settings) -> Result<(), String> {
    settings::save(&app, &new_settings)
}

#[tauri::command]
fn repo_info(app: AppHandle) -> Result<serde_json::Value, String> {
    let root = repo_root(&app)?;
    Ok(serde_json::json!({
        "repo_root": root,
        "logs_dir": root.join("logs"),
        "data_dir": root.join("data"),
    }))
}

#[tauri::command]
fn process_status(state: State<'_, AppState>) -> Result<Vec<ProcessStatus>, String> {
    Ok(state.processes.lock().map_err(|e| e.to_string())?.status())
}

#[tauri::command]
fn start_process(
    app: AppHandle,
    state: State<'_, AppState>,
    kind: ProcKind,
) -> Result<u32, String> {
    let root = repo_root(&app)?;
    let stored = settings::load(&app)?;
    let venues = stored.enabled_venues();
    if kind == ProcKind::Recorder && venues.is_empty() {
        return Err("No venues enabled. Enable at least one venue in Settings.".into());
    }
    state
        .processes
        .lock()
        .map_err(|e| e.to_string())?
        .start(&root, kind, &venues)
}

#[tauri::command]
fn stop_process(state: State<'_, AppState>, kind: ProcKind) -> Result<(), String> {
    state.processes.lock().map_err(|e| e.to_string())?.stop(kind)
}

#[tauri::command]
fn dataset_inventory(app: AppHandle) -> Result<inventory::Inventory, String> {
    Ok(inventory::scan(&repo_root(&app)?))
}

#[tauri::command]
fn read_status_file(app: AppHandle, name: String) -> Result<String, String> {
    let file = match name.as_str() {
        "validation_summary" => "validation_summary.json",
        "telemetry_latest" => "telemetry_latest.json",
        _ => return Err(format!("unknown status file: {name}")),
    };
    let path = repo_root(&app)?.join("logs").join(file);
    if !path.is_file() {
        return Ok(String::new());
    }
    std::fs::read_to_string(&path).map_err(|e| format!("read {}: {e}", path.display()))
}

#[tauri::command]
fn start_log_stream(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
) -> Result<(), String> {
    let file = match name.as_str() {
        "recorder" => "recorder.log",
        "telemetry" => "telemetry.log",
        _ => return Err(format!("unknown log stream: {name}")),
    };
    {
        let mut streams = state.log_streams.lock().map_err(|e| e.to_string())?;
        if !streams.insert(name.clone()) {
            return Ok(()); // already streaming
        }
    }
    let path = repo_root(&app)?.join("logs").join(file);
    logs::spawn_tailer(app, name, path);
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .manage(AppState {
            processes: Mutex::new(ProcessManager::default()),
            log_streams: Mutex::new(HashSet::new()),
        })
        .invoke_handler(tauri::generate_handler![
            get_settings,
            set_settings,
            repo_info,
            process_status,
            start_process,
            stop_process,
            dataset_inventory,
            read_status_file,
            start_log_stream,
        ])
        .on_window_event(|window, event| {
            // The desktop shell owns its children: never leave an orphaned
            // recorder writing to disk after the window is gone.
            if matches!(event, WindowEvent::Destroyed) {
                if let Some(state) = window.app_handle().try_state::<AppState>() {
                    if let Ok(mut manager) = state.processes.lock() {
                        manager.stop_all();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running MLCryptoEngine desktop");
}
