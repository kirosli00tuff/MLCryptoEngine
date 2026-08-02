"""Read validated Parquet into a merged, local-clock-ordered event stream.

Book state comes from the Phase A ``book_snapshots`` dataset (``event`` rows
only — ``interval`` rows are cadence duplicates for coverage accounting, not
new information). Trades come from the ``trades`` dataset. Both are read in
Arrow batches, so a full day streams in bounded memory.

Day boundary: the book parquet for day D is already warm-started by the
Phase A replay (ADR-006), so the first row of D reflects the previous
session's book state. Rolling *feature* state additionally warms from the
previous day's parquet tail — the same approach as data/validate/warmup.py,
reused at the dataset level — with those events flagged ``is_warmup`` so
nothing before the day is ever sampled, labeled, or trained on.

Gap windows (feed gaps plus recorder downtime derived from session markers —
the same machinery validation uses) are exposed so samplers and labelers can
invalidate anything whose lookback or horizon touches missing data.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq

from data.recorder.gaps import merge_windows, read_gaps
from data.recorder.sessions import read_sessions
from data.store import book_partition_dir, trade_partition_dir
from data.store.parquet_writer import PART_NAME
from data.validate.downtime import derive_downtime_gaps, last_activity_ns
from research.stream.events import Bbo, BookState, StreamEvent, Trade

BATCH_ROWS = 32_768
DEFAULT_WARMUP_S = 120
NS_PER_S = 1_000_000_000


def previous_date(date: str) -> str:
    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    return (day - timedelta(days=1)).strftime("%Y-%m-%d")


def _part_file(partition: Path) -> Path | None:
    path = partition / PART_NAME
    return path if path.is_file() else None


def iter_book_events(
    processed_dir: Path,
    venue: str,
    symbol: str,
    date: str,
    min_ns: int = 0,
    is_warmup: bool = False,
) -> Iterator[StreamEvent]:
    """Book ``event`` rows for one venue/symbol/day, in file (= time) order."""
    path = _part_file(book_partition_dir(processed_dir, venue, symbol, date))
    if path is None:
        return
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=BATCH_ROWS):
        for row in batch.to_pylist():
            if row["ts_ns"] < min_ns:
                continue
            if row["kind"] == "bbo":
                yield StreamEvent(
                    venue=venue,
                    symbol=symbol,
                    local_ns=row["ts_ns"],
                    exchange_ns=None,
                    book=None,
                    trade=None,
                    is_warmup=is_warmup,
                    bbo=Bbo(
                        best_bid=row["best_bid"],
                        bid_qty=row["bid_qty"],
                        best_ask=row["best_ask"],
                        ask_qty=row["ask_qty"],
                        mid=row["mid"],
                        microprice=row["microprice"],
                        bid_n=row.get("bid_n"),
                        ask_n=row.get("ask_n"),
                    ),
                )
                continue
            if row["kind"] != "event":
                continue  # "interval" rows are cadence duplicates
            yield StreamEvent(
                venue=venue,
                symbol=symbol,
                local_ns=row["ts_ns"],
                exchange_ns=None,
                book=BookState(
                    best_bid=row["best_bid"],
                    bid_qty=row["bid_qty"],
                    best_ask=row["best_ask"],
                    ask_qty=row["ask_qty"],
                    mid=row["mid"],
                    microprice=row["microprice"],
                    bid_prices=tuple(row["bid_prices"] or ()),
                    bid_qtys=tuple(row["bid_qtys"] or ()),
                    ask_prices=tuple(row["ask_prices"] or ()),
                    ask_qtys=tuple(row["ask_qtys"] or ()),
                    valid=bool(row["valid"]),
                ),
                trade=None,
                is_warmup=is_warmup,
            )


def iter_trades(
    processed_dir: Path,
    venue: str,
    symbol: str,
    date: str,
    min_ns: int = 0,
    is_warmup: bool = False,
) -> Iterator[StreamEvent]:
    """Trade rows for one venue/symbol/day, in file (= time) order."""
    path = _part_file(trade_partition_dir(processed_dir, venue, symbol, date))
    if path is None:
        return
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=BATCH_ROWS):
        for row in batch.to_pylist():
            if row["ts_ns"] < min_ns:
                continue
            yield StreamEvent(
                venue=venue,
                symbol=symbol,
                local_ns=row["ts_ns"],
                exchange_ns=row["exchange_ns"],
                book=None,
                trade=Trade(price=row["price"], qty=row["qty"], venue_side=row["venue_side"]),
                is_warmup=is_warmup,
            )


def _merge(*streams: Iterator[StreamEvent]) -> Iterator[StreamEvent]:
    # Books sort before trades at equal local_ns, so a same-instant book
    # update and trade always replay in one deterministic order.
    return heapq.merge(*streams, key=lambda e: (e.local_ns, 0 if e.book is not None else 1))


def merged_stream(
    processed_dir: Path,
    venue: str,
    symbol: str,
    date: str,
    warmup_s: int = DEFAULT_WARMUP_S,
) -> Iterator[StreamEvent]:
    """Warm-up tail (previous day, flagged) followed by the day's merged events."""
    day_start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    day_start_ns = int(day_start.timestamp()) * NS_PER_S
    if warmup_s > 0:
        prev = previous_date(date)
        cutoff = day_start_ns - warmup_s * NS_PER_S
        yield from _merge(
            iter_book_events(processed_dir, venue, symbol, prev, min_ns=cutoff, is_warmup=True),
            iter_trades(processed_dir, venue, symbol, prev, min_ns=cutoff, is_warmup=True),
        )
    yield from _merge(
        iter_book_events(processed_dir, venue, symbol, date),
        iter_trades(processed_dir, venue, symbol, date),
    )


def gap_windows(raw_dir: Path, venue: str) -> list[tuple[int, int]]:
    """Unioned missing-data windows: feed gaps plus derived recorder downtime.

    The same sources validation uses (ADR-007), so training exclusions can
    never disagree with coverage accounting about where the holes are.
    """
    gaps = read_gaps(raw_dir, venue) + derive_downtime_gaps(
        read_sessions(raw_dir, venue),
        lambda before_ns: last_activity_ns(raw_dir, venue, before_ns),
    )
    return merge_windows((g.disconnect_ns, g.reconnect_ns) for g in gaps)
