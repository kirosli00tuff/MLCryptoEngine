"""Reconnect gap sidecar: downstream code treats these windows as untrustworthy."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import orjson
from pydantic import BaseModel

GAPS_FILE_NAME = "gaps.jsonl"


def merge_windows(windows: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Union half-open ``[start, end)`` windows.

    Overlapping, touching, and duplicate windows collapse into one, so summing
    the result never double-counts a nanosecond. Empty/inverted windows are
    dropped. This is the only sanctioned way to aggregate gap durations.
    """
    ordered = sorted((start, end) for start, end in windows if end > start)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


class GapRecord(BaseModel):
    """One disconnect→reconnect window during recording."""

    venue: str
    disconnect_ns: int
    reconnect_ns: int
    duration_ms: int
    reason: str

    def overlaps_ns(self, start_ns: int, end_ns: int) -> bool:
        """True if this gap intersects the half-open window ``[start_ns, end_ns)``."""
        return self.disconnect_ns < end_ns and self.reconnect_ns > start_ns


class GapLogger:
    """Appends gap events to ``venue=<venue>/gaps.jsonl`` under the raw data root."""

    def __init__(self, raw_dir: Path, venue: str) -> None:
        self._venue = venue
        venue_dir = raw_dir / f"venue={venue}"
        venue_dir.mkdir(parents=True, exist_ok=True)
        self.path = venue_dir / GAPS_FILE_NAME

    def log_gap(self, disconnect_ns: int, reconnect_ns: int, reason: str) -> GapRecord:
        record = GapRecord(
            venue=self._venue,
            disconnect_ns=disconnect_ns,
            reconnect_ns=reconnect_ns,
            duration_ms=(reconnect_ns - disconnect_ns) // 1_000_000,
            reason=reason,
        )
        with self.path.open("ab") as fh:
            fh.write(orjson.dumps(record.model_dump()) + b"\n")
        return record


def read_gaps(raw_dir: Path, venue: str) -> list[GapRecord]:
    """All recorded gaps for a venue, oldest first. Missing file means no gaps."""
    path = raw_dir / f"venue={venue}" / GAPS_FILE_NAME
    if not path.is_file():
        return []
    records: list[GapRecord] = []
    with path.open("rb") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                records.append(GapRecord.model_validate(orjson.loads(stripped)))
    return records
