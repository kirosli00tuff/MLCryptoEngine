"""Parquet writer for processed datasets.

Layout: ``data/processed/book_snapshots/venue=<v>/symbol=<s>/date=<YYYY-MM-DD>/part-000.parquet``

The part name is deterministic, so reprocessing a day overwrites its previous
output — the processing entry point is idempotent and safe to rerun. Raw data
is never touched by this module; processed outputs are always regenerable.

Schema (``BOOK_SNAPSHOT_SCHEMA``):

- ``venue``/``symbol``/``kind`` — dictionary-encoded strings (kind: event | interval)
- ``ts_ns`` — int64 receive timestamp (event) or interval boundary (interval)
- ``valid``/``crossed``/``locked`` — book health flags at emission
- ``best_bid``/``bid_qty``/``best_ask``/``ask_qty``/``mid``/``microprice`` — float64
- ``bid_prices``/``bid_qtys``/``ask_prices``/``ask_qtys`` — list<float64> depth arrays
- ``seq`` — venue sequence number when the venue provides one
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

BOOK_DATASET = "book_snapshots"
PART_NAME = "part-000.parquet"

BOOK_SNAPSHOT_SCHEMA = pa.schema(
    [
        pa.field("venue", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("ts_ns", pa.int64()),
        pa.field("kind", pa.string()),
        pa.field("valid", pa.bool_()),
        pa.field("crossed", pa.bool_()),
        pa.field("locked", pa.bool_()),
        pa.field("best_bid", pa.float64()),
        pa.field("bid_qty", pa.float64()),
        pa.field("best_ask", pa.float64()),
        pa.field("ask_qty", pa.float64()),
        pa.field("mid", pa.float64()),
        pa.field("microprice", pa.float64()),
        pa.field("bid_prices", pa.list_(pa.float64())),
        pa.field("bid_qtys", pa.list_(pa.float64())),
        pa.field("ask_prices", pa.list_(pa.float64())),
        pa.field("ask_qtys", pa.list_(pa.float64())),
        pa.field("seq", pa.int64()),
    ]
)


def sanitize_symbol(symbol: str) -> str:
    """Filesystem-safe partition value; the exact symbol stays in the column."""
    return symbol.replace("/", "-")


def book_partition_dir(processed_dir: Path, venue: str, symbol: str, date: str) -> Path:
    return (
        processed_dir
        / BOOK_DATASET
        / f"venue={venue}"
        / f"symbol={sanitize_symbol(symbol)}"
        / f"date={date}"
    )


def write_book_day(
    processed_dir: Path,
    venue: str,
    symbol: str,
    date: str,
    rows: list[dict[str, Any]],
) -> Path:
    """Write one venue/symbol/day of book snapshot rows; overwrites prior output."""
    directory = book_partition_dir(processed_dir, venue, symbol, date)
    directory.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=BOOK_SNAPSHOT_SCHEMA)
    path = directory / PART_NAME
    pq.write_table(
        table,
        path,
        compression="zstd",
        use_dictionary=["venue", "symbol", "kind"],
    )
    return path
