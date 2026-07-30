//! Filesystem scan of recorded (raw) and processed datasets. Read-only.

use std::path::Path;

use serde::Serialize;

#[derive(Serialize)]
pub struct RawDate {
    pub date: String,
    pub hours: u32,
    pub bytes: u64,
}

#[derive(Serialize)]
pub struct VenueRaw {
    pub venue: String,
    pub total_bytes: u64,
    pub gap_events: u64,
    pub dates: Vec<RawDate>,
}

#[derive(Serialize)]
pub struct ProcessedPartition {
    pub dataset: String,
    pub venue: String,
    pub symbol: Option<String>,
    pub date: String,
    pub files: u32,
    pub bytes: u64,
}

#[derive(Serialize, Default)]
pub struct Inventory {
    pub raw: Vec<VenueRaw>,
    pub processed: Vec<ProcessedPartition>,
    pub raw_total_bytes: u64,
    pub processed_total_bytes: u64,
}

fn dir_names(path: &Path, prefix: &str) -> Vec<(String, std::path::PathBuf)> {
    let Ok(entries) = std::fs::read_dir(path) else {
        return Vec::new();
    };
    let mut out: Vec<(String, std::path::PathBuf)> = entries
        .filter_map(|entry| entry.ok())
        .filter(|entry| entry.path().is_dir())
        .filter_map(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            name.strip_prefix(prefix)
                .map(|v| (v.to_string(), entry.path()))
        })
        .collect();
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}

fn file_bytes(path: &Path) -> u64 {
    std::fs::metadata(path).map(|m| m.len()).unwrap_or(0)
}

fn line_count(path: &Path) -> u64 {
    std::fs::read_to_string(path)
        .map(|text| text.lines().filter(|l| !l.trim().is_empty()).count() as u64)
        .unwrap_or(0)
}

fn dir_file_bytes(path: &Path, extension: &str) -> (u32, u64) {
    let Ok(entries) = std::fs::read_dir(path) else {
        return (0, 0);
    };
    let mut files = 0u32;
    let mut bytes = 0u64;
    for entry in entries.filter_map(|e| e.ok()) {
        let p = entry.path();
        if p.is_file() && p.extension().map(|e| e == extension).unwrap_or(false) {
            files += 1;
            bytes += file_bytes(&p);
        }
    }
    (files, bytes)
}

pub fn scan(repo_root: &Path) -> Inventory {
    let mut inventory = Inventory::default();

    // Raw: data/raw/venue=<v>/date=<d>/hour=<h>/*.zst (+ gaps.jsonl sidecar)
    let raw_root = repo_root.join("data").join("raw");
    for (venue, venue_path) in dir_names(&raw_root, "venue=") {
        let mut venue_total = 0u64;
        let mut dates = Vec::new();
        for (date, date_path) in dir_names(&venue_path, "date=") {
            let mut hours = 0u32;
            let mut date_bytes = 0u64;
            for (_hour, hour_path) in dir_names(&date_path, "hour=") {
                let (files, bytes) = dir_file_bytes(&hour_path, "zst");
                if files > 0 {
                    hours += 1;
                    date_bytes += bytes;
                }
            }
            venue_total += date_bytes;
            dates.push(RawDate {
                date,
                hours,
                bytes: date_bytes,
            });
        }
        inventory.raw_total_bytes += venue_total;
        inventory.raw.push(VenueRaw {
            gap_events: line_count(&venue_path.join("gaps.jsonl")),
            venue,
            total_bytes: venue_total,
            dates,
        });
    }

    // Processed: data/processed/<dataset>/venue=<v>[/symbol=<s>]/date=<d>/*.parquet
    let processed_root = repo_root.join("data").join("processed");
    if let Ok(datasets) = std::fs::read_dir(&processed_root) {
        for dataset_entry in datasets.filter_map(|e| e.ok()) {
            let dataset_path = dataset_entry.path();
            if !dataset_path.is_dir() {
                continue;
            }
            let dataset = dataset_entry.file_name().to_string_lossy().into_owned();
            for (venue, venue_path) in dir_names(&dataset_path, "venue=") {
                // Either venue/symbol/date or venue/date layouts.
                for (symbol, symbol_path) in dir_names(&venue_path, "symbol=") {
                    for (date, date_path) in dir_names(&symbol_path, "date=") {
                        let (files, bytes) = dir_file_bytes(&date_path, "parquet");
                        inventory.processed_total_bytes += bytes;
                        inventory.processed.push(ProcessedPartition {
                            dataset: dataset.clone(),
                            venue: venue.clone(),
                            symbol: Some(symbol.clone()),
                            date,
                            files,
                            bytes,
                        });
                    }
                }
                for (date, date_path) in dir_names(&venue_path, "date=") {
                    let (files, bytes) = dir_file_bytes(&date_path, "parquet");
                    inventory.processed_total_bytes += bytes;
                    inventory.processed.push(ProcessedPartition {
                        dataset: dataset.clone(),
                        venue: venue.clone(),
                        symbol: None,
                        date,
                        files,
                        bytes,
                    });
                }
            }
        }
    }

    inventory
}
