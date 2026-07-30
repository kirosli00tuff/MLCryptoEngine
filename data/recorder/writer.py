"""Lossless raw message capture: zstd-compressed NDJSON, rotated hourly.

Each line is ``{"recv_ns": <int>, "raw": <exchange message text>}``. The exchange
message is stored verbatim as a JSON string — no field is parsed, dropped, or
reordered — so any later processing stage can always reprocess from raw.

Files are appended as independent zstd frames, so a recorder restart within the
same hour never corrupts earlier data; readers must decompress across frames.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import IO

import orjson
import zstandard

RAW_FILE_NAME = "messages.ndjson.zst"


class RawFileWriter:
    """Writes raw exchange messages for one venue, partitioned venue/date/hour."""

    def __init__(self, raw_dir: Path, venue: str, level: int = 6) -> None:
        self._venue_dir = raw_dir / f"venue={venue}"
        self._cctx = zstandard.ZstdCompressor(level=level)
        self._hour_key: tuple[str, str] | None = None
        self._fh: IO[bytes] | None = None
        self._writer: zstandard.ZstdCompressionWriter | None = None
        self.raw_bytes_total = 0
        self.messages_total = 0

    @property
    def current_path(self) -> Path | None:
        """Path of the file currently being written, if any."""
        if self._hour_key is None:
            return None
        date_part, hour_part = self._hour_key
        return self._venue_dir / f"date={date_part}" / f"hour={hour_part}" / RAW_FILE_NAME

    @property
    def bytes_on_disk_hour(self) -> int:
        """Compressed bytes written to the current hour file so far."""
        if self._fh is None or self._fh.closed:
            return 0
        return self._fh.tell()

    def write(self, recv_ns: int, raw: str) -> None:
        """Append one raw message with its local receive timestamp (nanoseconds)."""
        stamp = datetime.fromtimestamp(recv_ns / 1_000_000_000, tz=UTC)
        hour_key = (stamp.strftime("%Y-%m-%d"), stamp.strftime("%H"))
        if hour_key != self._hour_key:
            self._rotate(hour_key)
        if self._writer is None:  # pragma: no cover - guarded by _rotate
            raise RuntimeError("writer not open")
        line = orjson.dumps({"recv_ns": recv_ns, "raw": raw}) + b"\n"
        self._writer.write(line)
        # Flush the zstd block on every message so a crash loses at most the
        # final partial block, never the whole hour.
        self._writer.flush(zstandard.FLUSH_BLOCK)
        self.raw_bytes_total += len(line)
        self.messages_total += 1

    def _rotate(self, hour_key: tuple[str, str]) -> None:
        self.close()
        self._hour_key = hour_key
        path = self.current_path
        if path is None:  # pragma: no cover - hour_key was just set
            raise RuntimeError("rotation without hour key")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("ab")
        self._writer = self._cctx.stream_writer(self._fh, closefd=False)

    def close(self) -> None:
        """Finish the current zstd frame and close the file. Safe to call twice."""
        if self._writer is not None:
            self._writer.close()  # type: ignore[no-untyped-call]
            self._writer = None
        if self._fh is not None:
            self._fh.close()
            self._fh = None
