"""Reconnect gap sidecar: downstream code treats these windows as untrustworthy."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import orjson
from pydantic import BaseModel, model_validator

GAPS_FILE_NAME = "gaps.jsonl"


class NegativeGapError(RuntimeError):
    """A gap window runs backwards in time; every number derived from it is wrong.

    A gap is a half-open ``[disconnect_ns, reconnect_ns)`` window, so its
    duration is non-negative by construction. A negative one is never a small
    numeric annoyance: it subtracts phantom time from coverage denominators,
    and :func:`merge_windows` silently drops inverted windows, so the gap
    disappears from the union while still being counted in its per-kind total
    — two numbers that disagree with nothing to show why. It also means
    whatever built it paired the wrong two timestamps, which is exactly what
    happens when session markers are read in file order instead of timestamp
    order. Same spirit as the Stage 1.6 span-clamping invariant: refuse to
    produce a number rather than produce a wrong one.

    Deliberately a ``RuntimeError`` and not a ``ValueError``: pydantic folds a
    ``ValueError`` raised inside a model validator into a ``ValidationError``,
    which would bury this behind a generic "1 validation error" and let a
    caller catching ``ValidationError`` for ordinary malformed input swallow a
    corruption signal.
    """


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
    """One window of missing data, distinguished by cause.

    ``kind`` separates causes that must never be conflated: a ``feed`` gap is
    the venue dropping us while the recorder ran (written to gaps.jsonl at
    reconnect); a ``downtime`` gap is the recorder not running between a clean
    session end and the next start; ``unclean`` is downtime after a
    termination that wrote no session-end marker (crash, OOM kill, power
    loss), measured from last observed activity. Downtime kinds are derived
    from session markers at validation time — see
    :mod:`data.validate.downtime`. Legacy records carry no ``kind`` field and
    default to ``feed``.
    """

    venue: str
    disconnect_ns: int
    reconnect_ns: int
    duration_ms: int
    reason: str
    kind: Literal["feed", "downtime", "unclean"] = "feed"

    @model_validator(mode="after")
    def _window_runs_forwards(self) -> GapRecord:
        """Every gap, from any source, is a forwards window. No exceptions.

        Enforced on the model rather than at each producer so a new derivation
        cannot reintroduce the defect by forgetting to check. Zero-length is
        allowed — a restart fast enough to reconnect within the timestamp
        resolution is real — but backwards never is.
        """
        if self.reconnect_ns < self.disconnect_ns:
            raise NegativeGapError(
                f"{self.venue} {self.kind} gap ends {self.disconnect_ns - self.reconnect_ns} ns "
                f"before it starts (disconnect {self.disconnect_ns}, reconnect "
                f"{self.reconnect_ns}). A gap cannot run backwards; whatever produced this "
                "paired the wrong two timestamps and its output must not be trusted."
            )
        return self

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
