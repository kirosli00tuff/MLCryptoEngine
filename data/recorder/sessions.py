"""Session lifecycle sidecar: when was a recorder process alive at all.

gaps.jsonl records disconnects the recorder *observed while running*; it is
structurally blind to periods where the process was not running (systemd
restarts, crashes, OOM kills, reboots, manual stops). Session markers close
that hole: a ``start`` marker is written on startup before connecting and an
``end`` marker on graceful shutdown, per venue, alongside gaps.jsonl.
Validation derives recorder-downtime gaps from the marker sequence — see
:mod:`data.validate.downtime`. A start following a start with no end between
them is the signature of an unclean termination.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import orjson
from pydantic import BaseModel

SESSIONS_FILE_NAME = "sessions.jsonl"

SessionEvent = Literal["start", "end"]


class SessionMarker(BaseModel):
    """One process lifecycle boundary for one venue."""

    venue: str
    event: SessionEvent
    ts_ns: int


class SessionLogger:
    """Appends session markers to ``venue=<venue>/sessions.jsonl``."""

    def __init__(self, raw_dir: Path, venue: str) -> None:
        self._venue = venue
        venue_dir = raw_dir / f"venue={venue}"
        venue_dir.mkdir(parents=True, exist_ok=True)
        self.path = venue_dir / SESSIONS_FILE_NAME

    def log(self, event: SessionEvent, ts_ns: int) -> SessionMarker:
        marker = SessionMarker(venue=self._venue, event=event, ts_ns=ts_ns)
        with self.path.open("ab") as fh:
            fh.write(orjson.dumps(marker.model_dump()) + b"\n")
        return marker


def read_sessions(raw_dir: Path, venue: str) -> list[SessionMarker]:
    """All session markers for a venue, in file order. Missing file means none."""
    path = raw_dir / f"venue={venue}" / SESSIONS_FILE_NAME
    if not path.is_file():
        return []
    markers: list[SessionMarker] = []
    with path.open("rb") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                markers.append(SessionMarker.model_validate(orjson.loads(stripped)))
    return markers
