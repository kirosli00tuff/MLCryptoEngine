//! User settings persisted to the OS app-config directory — never inside the
//! repository, so credentials can never leak into git history.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Serialize, Deserialize, Clone)]
#[serde(default)]
pub struct Settings {
    /// Absolute path to the MLCryptoEngine repo. None = auto-detect.
    pub repo_root: Option<String>,
    pub record_kraken: bool,
    pub record_coinbase: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            repo_root: None,
            record_kraken: true,
            record_coinbase: true,
        }
    }
}

impl Settings {
    pub fn enabled_venues(&self) -> Vec<String> {
        let mut venues = Vec::new();
        if self.record_kraken {
            venues.push("kraken".to_string());
        }
        if self.record_coinbase {
            venues.push("coinbase".to_string());
        }
        venues
    }
}

fn settings_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("resolve config dir: {e}"))?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("create {}: {e}", dir.display()))?;
    Ok(dir.join("settings.json"))
}

pub fn load(app: &AppHandle) -> Result<Settings, String> {
    let path = settings_path(app)?;
    if !path.is_file() {
        return Ok(Settings::default());
    }
    let text =
        std::fs::read_to_string(&path).map_err(|e| format!("read {}: {e}", path.display()))?;
    let mut value: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))?;
    // Migration (Stage 1.5): the app no longer stores credentials. A settings
    // file written by an earlier build may carry a plaintext `api` object;
    // strip it and rewrite the file immediately so no secret lingers on disk.
    if let Some(object) = value.as_object_mut() {
        if object.remove("api").is_some() {
            let settings: Settings = serde_json::from_value(value)
                .map_err(|e| format!("parse {}: {e}", path.display()))?;
            save(app, &settings)?;
            eprintln!(
                "mlcryptoengine: removed legacy plaintext api credentials from {}",
                path.display()
            );
            return Ok(settings);
        }
    }
    serde_json::from_value(value).map_err(|e| format!("parse {}: {e}", path.display()))
}

pub fn save(app: &AppHandle, settings: &Settings) -> Result<(), String> {
    let path = settings_path(app)?;
    let text = serde_json::to_string_pretty(settings).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| format!("write {}: {e}", path.display()))
}

/// The repo root is either configured explicitly or found by walking up from
/// the current directory looking for the pyproject + data markers.
pub fn resolve_repo_root(settings: &Settings) -> Result<PathBuf, String> {
    if let Some(configured) = &settings.repo_root {
        let path = PathBuf::from(configured);
        if path.join("pyproject.toml").is_file() {
            return Ok(path);
        }
        return Err(format!(
            "Configured repository path {configured} has no pyproject.toml. Fix it in Settings."
        ));
    }
    let mut dir = std::env::current_dir().map_err(|e| format!("current dir: {e}"))?;
    loop {
        if dir.join("pyproject.toml").is_file() && dir.join("data").is_dir() {
            return Ok(dir);
        }
        if !dir.pop() {
            break;
        }
    }
    Err(
        "Could not find the MLCryptoEngine repository automatically. \
         Set the repository path in Settings."
            .to_string(),
    )
}
