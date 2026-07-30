"""Parquet round-trip: schema stability, value fidelity, idempotent rewrite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson
import pyarrow.parquet as pq

from data.book import BookBuilder, SnapshotEmitter, parse_kraken
from data.book.kraken_checksum import checksum_fn_for
from data.store import (
    BOOK_SNAPSHOT_SCHEMA,
    book_partition_dir,
    dataset_coverage,
    load_book_range,
    write_book_day,
)
from tests.conftest import FIXTURES_DIR

DATE = "2026-07-30"


def _rows_from_fixture() -> list[dict[str, Any]]:
    builder = BookBuilder("kraken", "BTC/USD", depth=100, checksum_fn=checksum_fn_for(1, 8))
    emitter = SnapshotEmitter(builder, interval_ms=1000, depth=5)
    rows: list[dict[str, Any]] = []
    base_ns = 1_785_424_678_000_000_000
    text = (FIXTURES_DIR / "kraken_messages.ndjson").read_text(encoding="utf-8")
    for offset, line in enumerate(line for line in text.splitlines() if line.strip()):
        recv_ns = base_ns + offset * 50_000_000
        for event in parse_kraken(orjson.loads(line), recv_ns):
            builder.apply(event)
            rows.extend(emitter.on_event(recv_ns))
    return rows


def test_roundtrip_preserves_schema_and_values(tmp_path: Path) -> None:
    rows = _rows_from_fixture()
    assert len(rows) > 60

    path = write_book_day(tmp_path, "kraken", "BTC/USD", DATE, rows)

    # Schema stability: what is on disk is exactly the documented schema.
    assert pq.read_table(path).schema.equals(BOOK_SNAPSHOT_SCHEMA)

    frame = load_book_range(tmp_path, "kraken", "BTC/USD")
    assert frame.height == len(rows)
    assert frame["ts_ns"].is_sorted()
    first = frame.row(0, named=True)
    assert first["venue"] == "kraken"
    assert first["symbol"] == "BTC/USD"
    assert first["kind"] in ("event", "interval")
    assert first["best_bid"] is not None and first["best_ask"] is not None
    assert len(first["bid_prices"]) <= 5

    event_rows = load_book_range(tmp_path, "kraken", "BTC/USD", kind="event")
    assert 0 < event_rows.height <= frame.height


def test_time_range_filter_bounds_rows(tmp_path: Path) -> None:
    rows = _rows_from_fixture()
    write_book_day(tmp_path, "kraken", "BTC/USD", DATE, rows)
    mid_ns = int(rows[len(rows) // 2]["ts_ns"])

    frame = load_book_range(tmp_path, "kraken", "BTC/USD", start_ns=mid_ns)

    assert 0 < frame.height < len(rows)
    minimum = frame["ts_ns"].min()
    assert isinstance(minimum, int)
    assert minimum >= mid_ns


def test_rewrite_is_idempotent(tmp_path: Path) -> None:
    rows = _rows_from_fixture()
    first_path = write_book_day(tmp_path, "kraken", "BTC/USD", DATE, rows)
    second_path = write_book_day(tmp_path, "kraken", "BTC/USD", DATE, rows)

    assert first_path == second_path
    partition = book_partition_dir(tmp_path, "kraken", "BTC/USD", DATE)
    assert len(list(partition.glob("*.parquet"))) == 1

    coverage = dataset_coverage(tmp_path)
    assert len(coverage) == 1
    info = coverage[0]
    assert (info.venue, info.symbol, info.date) == ("kraken", "BTC/USD", DATE)
    assert info.rows == len(rows)
    assert info.files == 1
