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
COMPRESSION = "zstd"
DICTIONARY_COLUMNS = ["venue", "symbol", "kind"]
# Rows buffered before each streamed row-group flush. Sized so the buffer of
# Python dicts (~2.3 KB each measured on real tick data) stays around 100 MB.
DEFAULT_FLUSH_ROWS = 50_000
_INPROGRESS_SUFFIX = ".inprogress"

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


class StreamingPartWriter:
    """Streams rows to one Parquet part file in bounded memory.

    Rows are buffered and written out as a row group every ``flush_rows`` rows,
    so a dataset of any size passes through bounded memory — the fix for the
    2026-07-31 OOM, where a full day of retained rows reached 12.8 GB RSS.
    Output goes to a temporary name inside the target directory and is renamed
    to the deterministic final name by :meth:`close`, so reprocessing stays
    idempotent and a crashed run never leaves a partial file at the final
    path; the leftover temporary is overwritten by the next run.
    """

    def __init__(
        self,
        path: Path,
        schema: pa.Schema,
        flush_rows: int = DEFAULT_FLUSH_ROWS,
        use_dictionary: list[str] | None = None,
    ) -> None:
        if flush_rows <= 0:
            raise ValueError(f"flush_rows must be positive, got {flush_rows}")
        self._final_path = path
        self._tmp_path = path.with_name(path.name + _INPROGRESS_SUFFIX)
        self._schema = schema
        self._use_dictionary = use_dictionary
        self._flush_rows = flush_rows
        self._buffer: list[dict[str, Any]] = []
        self._writer: pq.ParquetWriter | None = None
        # Rows appended so far; all of them are on disk once close() returns.
        self.rows_written = 0

    def append(self, rows: list[dict[str, Any]]) -> None:
        self._buffer.extend(rows)
        self.rows_written += len(rows)
        if len(self._buffer) >= self._flush_rows:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        if self._writer is None:
            self._final_path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(
                self._tmp_path,
                self._schema,
                compression=COMPRESSION,
                use_dictionary=self._use_dictionary if self._use_dictionary is not None else True,
            )
        self._writer.write_table(pa.Table.from_pylist(self._buffer, schema=self._schema))
        self._buffer = []

    def close(self) -> Path | None:
        """Flush the remainder and rename into place; None when nothing was appended.

        Safe to call more than once — later calls find nothing to write.
        """
        self._flush()
        if self._writer is None:
            return None
        self._writer.close()
        self._writer = None
        self._tmp_path.replace(self._final_path)
        return self._final_path


class BookDayWriter(StreamingPartWriter):
    """Streams one venue/symbol/day of book snapshot rows to Parquet."""

    def __init__(
        self,
        processed_dir: Path,
        venue: str,
        symbol: str,
        date: str,
        flush_rows: int = DEFAULT_FLUSH_ROWS,
    ) -> None:
        super().__init__(
            book_partition_dir(processed_dir, venue, symbol, date) / PART_NAME,
            BOOK_SNAPSHOT_SCHEMA,
            flush_rows=flush_rows,
            use_dictionary=DICTIONARY_COLUMNS,
        )


TRADES_DATASET = "trades"

# Executed trades extracted losslessly from raw capture. ``ts_ns`` is the
# recorder's local receive timestamp (ordering and horizons use this);
# ``exchange_ns`` is what the venue claims — kept, never used for ordering.
# ``venue_side`` is the venue-reported side string verbatim; its aggressor
# semantics differ per venue and are resolved downstream (see
# research/features/signing.py).
TRADE_SCHEMA = pa.schema(
    [
        pa.field("venue", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("ts_ns", pa.int64()),
        pa.field("exchange_ns", pa.int64()),
        pa.field("price", pa.float64()),
        pa.field("qty", pa.float64()),
        pa.field("venue_side", pa.string()),
        pa.field("trade_id", pa.string()),
    ]
)


def trade_partition_dir(processed_dir: Path, venue: str, symbol: str, date: str) -> Path:
    return (
        processed_dir
        / TRADES_DATASET
        / f"venue={venue}"
        / f"symbol={sanitize_symbol(symbol)}"
        / f"date={date}"
    )


class TradesDayWriter(StreamingPartWriter):
    """Streams one venue/symbol/day of executed trades to Parquet."""

    def __init__(
        self,
        processed_dir: Path,
        venue: str,
        symbol: str,
        date: str,
        flush_rows: int = DEFAULT_FLUSH_ROWS,
    ) -> None:
        super().__init__(
            trade_partition_dir(processed_dir, venue, symbol, date) / PART_NAME,
            TRADE_SCHEMA,
            flush_rows=flush_rows,
            use_dictionary=["venue", "symbol", "venue_side"],
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
        compression=COMPRESSION,
        use_dictionary=DICTIONARY_COLUMNS,
    )
    return path
