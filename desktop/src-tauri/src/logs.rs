//! Structured log tailing: one background thread per file, new lines streamed
//! to the frontend as `log-line` events.

use std::fs::File;
use std::io::{BufRead, BufReader, Seek, SeekFrom};
use std::path::PathBuf;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter};

const POLL_INTERVAL: Duration = Duration::from_millis(500);

#[derive(Clone, Serialize)]
struct LogLine {
    source: String,
    line: String,
}

/// Tail `path` forever, emitting appended lines. Starts at the current end of
/// file (history is on disk if the user wants it); survives truncation and
/// the file not existing yet.
pub fn spawn_tailer(app: AppHandle, source: String, path: PathBuf) {
    std::thread::spawn(move || {
        let mut position: u64 = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
        loop {
            std::thread::sleep(POLL_INTERVAL);
            let Ok(meta) = std::fs::metadata(&path) else {
                continue;
            };
            let len = meta.len();
            if len < position {
                // File was truncated or rotated: start over from the top.
                position = 0;
            }
            if len == position {
                continue;
            }
            let Ok(mut file) = File::open(&path) else {
                continue;
            };
            if file.seek(SeekFrom::Start(position)).is_err() {
                continue;
            }
            let mut reader = BufReader::new(file);
            let mut buf = String::new();
            loop {
                buf.clear();
                match reader.read_line(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        position += n as u64;
                        let line = buf.trim_end().to_string();
                        if !line.is_empty() {
                            let _ = app.emit(
                                "log-line",
                                LogLine {
                                    source: source.clone(),
                                    line,
                                },
                            );
                        }
                    }
                    Err(_) => break,
                }
            }
        }
    });
}
