"""Persist latency samples: Parquet per venue-day plus a latest-state JSON.

Parquet layout mirrors the book store: ``data/processed/latency/venue=<v>/date=<d>/part-000.parquet``.
Each flush rewrites the day from the in-memory buffer (seeded from disk at
startup), so restarts never lose or duplicate rows and reruns are idempotent.
``logs/telemetry_latest.json`` carries current percentiles and recent history
for the desktop app's latency chart.
"""

from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
import pyarrow as pa
import pyarrow.parquet as pq

LATENCY_DATASET = "latency"
PART_NAME = "part-000.parquet"
HISTORY_LIMIT = 720

LATENCY_SCHEMA = pa.schema(
    [
        pa.field("ts_ns", pa.int64()),
        pa.field("venue", pa.string()),
        pa.field("rtt_ms", pa.float64()),
        pa.field("ok", pa.bool_()),
        pa.field("error", pa.string()),
        pa.field("p50_ms", pa.float64()),
        pa.field("p95_ms", pa.float64()),
        pa.field("p99_ms", pa.float64()),
    ]
)


def _date_of_ns(ts_ns: int) -> str:
    return datetime.fromtimestamp(ts_ns / 1e9, tz=UTC).strftime("%Y-%m-%d")


class TelemetryStore:
    """Buffers latency rows and flushes them to Parquet + latest-state JSON."""

    def __init__(self, processed_dir: Path, logs_dir: Path) -> None:
        self._processed_dir = processed_dir
        self._logs_dir = logs_dir
        self._buffers: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def _partition(self, venue: str, date: str) -> Path:
        return self._processed_dir / LATENCY_DATASET / f"venue={venue}" / f"date={date}"

    def _seed_from_disk(self, venue: str, date: str) -> None:
        buffer_key = (venue, date)
        if self._buffers[buffer_key]:
            return
        path = self._partition(venue, date) / PART_NAME
        if path.is_file():
            existing = pq.read_table(path)
            self._buffers[buffer_key] = existing.to_pylist()

    def add(self, row: dict[str, Any]) -> None:
        venue = str(row["venue"])
        date = _date_of_ns(int(row["ts_ns"]))
        self._seed_from_disk(venue, date)
        self._buffers[(venue, date)].append(row)

    def flush_parquet(self) -> list[Path]:
        written: list[Path] = []
        for (venue, date), rows in self._buffers.items():
            if not rows:
                continue
            directory = self._partition(venue, date)
            directory.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist(rows, schema=LATENCY_SCHEMA)
            path = directory / PART_NAME
            pq.write_table(table, path, compression="zstd", use_dictionary=["venue"])
            written.append(path)
        # Drop buffers for past days so memory stays bounded on long runs.
        today = _date_of_ns(int(datetime.now(UTC).timestamp() * 1e9))
        for buffer_key in [k for k in self._buffers if k[1] != today]:
            del self._buffers[buffer_key]
        return written

    def write_latest_json(self) -> Path:
        venues: dict[str, Any] = {}
        for (venue, _date), rows in sorted(self._buffers.items()):
            if not rows:
                continue
            last = rows[-1]
            history = [
                {
                    "ts_ns": r["ts_ns"],
                    "rtt_ms": r["rtt_ms"],
                    "p50_ms": r["p50_ms"],
                    "p95_ms": r["p95_ms"],
                    "p99_ms": r["p99_ms"],
                    "ok": r["ok"],
                }
                for r in rows[-HISTORY_LIMIT:]
            ]
            venues[venue] = {
                "last_ms": last["rtt_ms"],
                "ok": last["ok"],
                "error": last["error"],
                "p50_ms": last["p50_ms"],
                "p95_ms": last["p95_ms"],
                "p99_ms": last["p99_ms"],
                "samples": len(rows),
                "history": history,
            }
        payload = {"generated_at": datetime.now(UTC).isoformat(), "venues": venues}
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        path = self._logs_dir / "telemetry_latest.json"
        fd, tmp_name = tempfile.mkstemp(dir=self._logs_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
            Path(tmp_name).replace(path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return path
