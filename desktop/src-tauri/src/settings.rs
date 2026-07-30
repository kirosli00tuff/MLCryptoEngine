//! User settings persisted to the OS app-config directory — never inside the
//! repository, so credentials can never leak into git history.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Serialize, Deserialize, Clone, Default)]
#[serde(default)]
pub struct ApiCredentials {
    pub kraken_api_key: String,
    pub kraken_api_secret: String,
    pub coinbase_api_key: String,
    pub coinbase_api_secret: String,
    pub databento_api_key: String,
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(default)]
pub struct Settings {
    /// Absolute path to the MLCryptoEngine repo. None = auto-detect.
    pub repo_root: Option<String>,
    pub record_kraken: bool,
    pub record_coinbase: bool,
    pub api: ApiCredentials,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            repo_root: None,
            record_kraken: true,
            record_coinbase: true,
            api: ApiCredentials::default(),
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
    serde_json::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))
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
