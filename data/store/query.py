"""DuckDB-backed query helpers over the processed Parquet partitions."""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
import pyarrow.parquet as pq
from pydantic import BaseModel

from data.store.parquet_writer import BOOK_DATASET, book_partition_dir, sanitize_symbol


class PartitionInfo(BaseModel):
    """Coverage entry for one venue/symbol/date partition."""

    venue: str
    symbol: str
    date: str
    files: int
    rows: int
    bytes: int


def load_book_range(
    processed_dir: Path,
    venue: str,
    symbol: str,
    start_ns: int | None = None,
    end_ns: int | None = None,
    kind: str | None = None,
) -> pl.DataFrame:
    """Book snapshots for a venue/symbol as a Polars frame, ordered by time.

    ``start_ns``/``end_ns`` bound ``ts_ns`` (half-open); ``kind`` filters to
    "event" or "interval" rows. Missing partitions yield an empty frame.
    """
    pattern = (
        processed_dir
        / BOOK_DATASET
        / f"venue={venue}"
        / f"symbol={sanitize_symbol(symbol)}"
        / "date=*"
        / "*.parquet"
    )
    if not list(pattern.parent.parent.glob(f"date=*/{pattern.name}")):
        return pl.DataFrame()
    conditions = ["true"]
    params: list[int | str] = []
    if start_ns is not None:
        conditions.append("ts_ns >= ?")
        params.append(start_ns)
    if end_ns is not None:
        conditions.append("ts_ns < ?")
        params.append(end_ns)
    if kind is not None:
        conditions.append("kind = ?")
        params.append(kind)
    query = (
        f"SELECT * FROM read_parquet('{pattern.as_posix()}') "
        f"WHERE {' AND '.join(conditions)} ORDER BY ts_ns"
    )
    with duckdb.connect() as con:
        result = con.execute(query, params).arrow()
    return pl.from_arrow(result)  # type: ignore[return-value]


def dataset_coverage(processed_dir: Path, dataset: str = BOOK_DATASET) -> list[PartitionInfo]:
    """Every venue/symbol/date partition with file count, row count, and bytes."""
    base = processed_dir / dataset
    if not base.is_dir():
        return []
    infos: list[PartitionInfo] = []
    for date_dir in sorted(base.glob("venue=*/symbol=*/date=*")):
        files = sorted(date_dir.glob("*.parquet"))
        if not files:
            continue
        rows = 0
        size = 0
        symbol = date_dir.parent.name.removeprefix("symbol=")
        for file in files:
            rows += pq.read_metadata(file).num_rows
            size += file.stat().st_size
            # Prefer the exact symbol from the data over the sanitized path value.
            head = pq.ParquetFile(file).read_row_group(0, columns=["symbol"])
            if head.num_rows:
                symbol = str(head.column("symbol")[0].as_py())
        infos.append(
            PartitionInfo(
                venue=date_dir.parent.parent.name.removeprefix("venue="),
                symbol=symbol,
                date=date_dir.name.removeprefix("date="),
                files=len(files),
                rows=rows,
                bytes=size,
            )
        )
    return infos


def on_disk_total(processed_dir: Path, dataset: str = BOOK_DATASET) -> int:
    """Total bytes on disk for a dataset."""
    return sum(info.bytes for info in dataset_coverage(processed_dir, dataset))


def partition_path(processed_dir: Path, venue: str, symbol: str, date: str) -> Path:
    """Convenience passthrough for callers that need the partition directory."""
    return book_partition_dir(processed_dir, venue, symbol, date)
