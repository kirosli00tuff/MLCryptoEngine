"""Read raw capture files back: the exact inverse of :mod:`data.recorder.writer`."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import orjson
import zstandard

from data.recorder.writer import RAW_FILE_NAME


def iter_raw_records(path: Path) -> Iterator[tuple[int, str]]:
    """Yield ``(recv_ns, raw_message)`` from one zstd NDJSON file.

    Files may contain multiple concatenated zstd frames (one per recorder
    session), so decompression reads across frame boundaries.
    """
    dctx = zstandard.ZstdDecompressor()
    with path.open("rb") as fh, dctx.stream_reader(fh, read_across_frames=True) as reader:
        text = io.TextIOWrapper(reader, encoding="utf-8")
        for line in text:
            stripped = line.strip()
            if not stripped:
                continue
            record = orjson.loads(stripped)
            yield int(record["recv_ns"]), str(record["raw"])


def hour_files(raw_dir: Path, venue: str, date: str) -> list[Path]:
    """All hour files for a venue and ISO date, in hour order."""
    base = raw_dir / f"venue={venue}" / f"date={date}"
    return sorted(base.glob(f"hour=*/{RAW_FILE_NAME}"))


def iter_day_records(raw_dir: Path, venue: str, date: str) -> Iterator[tuple[int, str]]:
    """Yield every record for a venue-day across all hour files, in file order."""
    for path in hour_files(raw_dir, venue, date):
        yield from iter_raw_records(path)


def available_dates(raw_dir: Path, venue: str) -> list[str]:
    """ISO dates that have at least one recorded hour for the venue."""
    venue_dir = raw_dir / f"venue={venue}"
    if not venue_dir.is_dir():
        return []
    return sorted(
        p.name.removeprefix("date=")
        for p in venue_dir.glob("date=*")
        if p.is_dir() and any(p.glob(f"hour=*/{RAW_FILE_NAME}"))
    )
