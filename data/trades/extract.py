"""Extract executed trades from raw capture into the processed trades dataset.

Single streaming pass per venue-day: raw NDJSON in, per-symbol Parquet out
via :class:`TradesDayWriter` (bounded memory, idempotent overwrite —
identical guarantees to the book replay). Deterministic part names mean
rerunning a day replaces its previous output.
"""

from __future__ import annotations

import time

import orjson

from data.config import AppConfig
from data.recorder.reader import iter_day_records
from data.store import TradesDayWriter
from data.trades.parse import PARSERS

PROGRESS_EVERY_MSGS = 1_000_000


def extract_trades_day(cfg: AppConfig, venue: str, date: str) -> dict[str, int]:
    """Extract one venue-day of trades; returns rows written per symbol."""
    if venue not in PARSERS:
        raise ValueError(f"No trade parser for venue '{venue}'")
    parse = PARSERS[venue]
    writers: dict[str, TradesDayWriter] = {}
    started = time.monotonic()
    msgs = 0
    for recv_ns, raw in iter_day_records(cfg.raw_dir, venue, date):
        msgs += 1
        if msgs % PROGRESS_EVERY_MSGS == 0:
            elapsed = time.monotonic() - started
            print(f"  trades {venue} {date}: {msgs:,} msgs · {elapsed:.0f}s elapsed", flush=True)
        message = orjson.loads(raw)
        if not isinstance(message, dict):
            continue
        for row in parse(message, recv_ns):
            symbol = str(row["symbol"])
            if symbol not in writers:
                writers[symbol] = TradesDayWriter(cfg.processed_dir, venue, symbol, date)
            writers[symbol].append([row])
    written = {}
    for symbol, writer in sorted(writers.items()):
        writer.close()
        written[symbol] = writer.rows_written
    return written
