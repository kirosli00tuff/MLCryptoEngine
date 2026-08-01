"""Warm-start replay: bring order books live across the day boundary.

Continuous recording keeps one WebSocket session running for days, so a
calendar day usually starts mid-session — its opening book snapshot was
recorded on the *previous* date. Replayed cold, such a day leaves every book
invalid until the first intra-day reconnect and scores hours of perfectly
recorded data as uncovered. The recorder encloses a target day with margin
precisely so the pre-midnight snapshot exists on disk; this module finds the
previous day's last snapshot per symbol and replays that tail through
midnight, building book state only. Nothing replayed here is scored: the
caller resets all counters at the boundary, so metrics describe the target
day alone while sequence continuity still spans midnight.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import orjson

from data.book import BookBuilder, SequenceTracker
from data.book.coinbase_parse import envelope_sequence
from data.book.types import BookEvent
from data.recorder.reader import hour_files, iter_raw_records

ParseFn = Callable[[dict[str, Any], int], list[BookEvent]]

NS_PER_S = 1_000_000_000
PROGRESS_EVERY_MSGS = 1_000_000


class WarmupResult(NamedTuple):
    """Outcome of a warm-up attempt.

    ``start_ns`` is the receive timestamp of the earliest snapshot the warm-up
    replayed from, or ``None`` when the previous day has no usable snapshot
    (no data, or none for any configured symbol) and the day replays cold.
    """

    start_ns: int | None
    messages_replayed: int


def previous_date(date: str) -> str:
    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    return (day - timedelta(days=1)).strftime("%Y-%m-%d")


def _hhmmss(ns: int) -> str:
    return datetime.fromtimestamp(ns / NS_PER_S, tz=UTC).strftime("%H:%M:%S")


def _hour_of(path: Path) -> int:
    return int(path.parent.name.removeprefix("hour="))


def _last_snapshot_per_symbol(
    files: list[Path], symbols: list[str], parse: ParseFn
) -> dict[str, int]:
    """Receive timestamp of each symbol's last snapshot, scanning newest hour first.

    The first hour (in reverse order) containing a snapshot for a symbol holds
    that symbol's last one; forward iteration within the hour keeps the latest.
    Stops as soon as every configured symbol is found. The substring prefilter
    is only an optimization — candidates are confirmed through the real parser.
    """
    remaining = set(symbols)
    last_snap: dict[str, int] = {}
    for path in reversed(files):
        found_this_hour: dict[str, int] = {}
        for recv_ns, raw in iter_raw_records(path):
            if "snapshot" not in raw:
                continue
            message = orjson.loads(raw)
            if not isinstance(message, dict):
                continue
            for event in parse(message, recv_ns):
                if event.is_snapshot and event.symbol in remaining:
                    found_this_hour[event.symbol] = recv_ns
        last_snap.update(found_this_hour)
        remaining -= set(found_this_hour)
        if not remaining:
            break
    return last_snap


def warm_up(
    raw_dir: Path,
    venue: str,
    date: str,
    symbols: list[str],
    parse: ParseFn,
    builder_for: Callable[[str], BookBuilder],
    tracker: SequenceTracker,
    seq_applies: bool,
) -> WarmupResult:
    """Replay the previous day's tail so ``date`` starts with live books.

    Applies events through ``builder_for`` exactly as the scored replay does —
    including sequence observation and checksum verification, so a corrupt
    warm-up leaves the book invalid rather than trustingly valid — but emits
    no rows and accounts nothing. The caller must reset builder and tracker
    counters afterwards.
    """
    prev = previous_date(date)
    files = hour_files(raw_dir, venue, prev)
    if not files:
        return WarmupResult(None, 0)

    last_snap = _last_snapshot_per_symbol(files, symbols, parse)
    if not last_snap:
        return WarmupResult(None, 0)
    start_ns = min(last_snap.values())
    start_hour = datetime.fromtimestamp(start_ns / NS_PER_S, tz=UTC).hour

    started = time.monotonic()
    print(
        f"  {venue} {date}: warm start — replaying {prev} tail from {_hhmmss(start_ns)}Z",
        flush=True,
    )
    replayed = 0
    for path in files:
        if _hour_of(path) < start_hour:
            continue
        for recv_ns, raw in iter_raw_records(path):
            if recv_ns < start_ns:
                continue
            message = orjson.loads(raw)
            if not isinstance(message, dict):
                continue
            seq = envelope_sequence(message) if seq_applies else None
            seq_ok = tracker.observe(seq) if seq is not None else True
            for event in parse(message, recv_ns):
                builder_for(event.symbol).apply(event, seq_ok=seq_ok)
            replayed += 1
            if replayed % PROGRESS_EVERY_MSGS == 0:
                elapsed = time.monotonic() - started
                print(
                    f"  {venue} {date}: warm-up {replayed:,} msgs · {elapsed:.0f}s elapsed",
                    flush=True,
                )
    elapsed = time.monotonic() - started
    print(
        f"  {venue} {date}: warm start complete — {replayed:,} messages replayed ({elapsed:.0f}s)",
        flush=True,
    )
    return WarmupResult(start_ns, replayed)
