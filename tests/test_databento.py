"""Databento adapter: schema mapping round-trip, clock provenance, sequence audit."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from data.databento.adapter import NULL_PRICE, SequenceAudit, map_mbp10, map_trade
from data.store import BOOK_SNAPSHOT_SCHEMA, BookDayWriter, TradesDayWriter

DATE = "2026-07-30"
TS_EVENT = 1_785_412_800_000_000_111  # exchange clock
TS_RECV = 1_785_412_800_000_050_222  # Databento capture hardware clock


def _mbp10_record() -> dict[str, object]:
    levels: list[dict[str, int]] = [
        {
            "bid_px": int((6_400.00 - i * 0.25) * 1e9),
            "ask_px": int((6_400.25 + i * 0.25) * 1e9),
            "bid_sz": 10 + i,
            "ask_sz": 20 + i,
        }
        for i in range(9)
    ]
    # Tenth level absent on both sides: Databento's null sentinel.
    levels.append({"bid_px": NULL_PRICE, "ask_px": NULL_PRICE, "bid_sz": 0, "ask_sz": 0})
    return {"ts_event": TS_EVENT, "ts_recv": TS_RECV, "sequence": 42, "levels": levels}


def test_mbp10_maps_to_canonical_row_with_vendor_clocks(tmp_path: Path) -> None:
    row = map_mbp10(_mbp10_record(), "MES")

    assert row["source"] == "databento", "the source column propagates downstream"
    assert row["ts_ns"] == TS_RECV, "ts_ns is the source's capture clock, never ours"
    assert row["exchange_ns"] == TS_EVENT
    assert row["best_bid"] == 6_400.00 and row["best_ask"] == 6_400.25
    assert row["mid"] == 6_400.125
    assert len(row["bid_prices"]) == 9, "null-sentinel levels are dropped, not zeroed"
    assert row["valid"] and not row["crossed"] and not row["locked"]
    assert row["seq"] == 42

    # Round-trip through the canonical writer: schema-stable on disk.
    writer = BookDayWriter(tmp_path, "cme", "MES", DATE)
    writer.append([row])
    path = writer.close()
    assert path is not None
    table = pq.read_table(path)
    assert table.schema.equals(BOOK_SNAPSHOT_SCHEMA)
    stored = table.to_pylist()[0]
    assert stored["source"] == "databento" and stored["exchange_ns"] == TS_EVENT


def test_trade_maps_with_aggressor_side_and_scaled_price(tmp_path: Path) -> None:
    record = {
        "ts_event": TS_EVENT,
        "ts_recv": TS_RECV,
        "sequence": 7,
        "price": int(6_400.25 * 1e9),
        "size": 3,
        "side": "A",
    }

    row = map_trade(record, "MBT")

    assert row["venue_side"] == "sell", "'A' is the ask-side aggressor"
    assert row["price"] == 6_400.25 and row["qty"] == 3.0
    assert (row["ts_ns"], row["exchange_ns"]) == (TS_RECV, TS_EVENT)
    writer = TradesDayWriter(tmp_path, "cme", "MBT", DATE)
    writer.append([row])
    path = writer.close()
    assert path is not None
    assert pq.read_table(path).to_pylist()[0]["source"] == "databento"


def test_sequence_audit_counts_observations_and_regressions() -> None:
    audit = SequenceAudit()
    assert audit.observe("MES", 1)
    assert audit.observe("MES", 2)
    assert not audit.observe("MES", 1), "a sequence regression is a gap"
    assert audit.observe("MBT", 5)

    assert audit.observations == {"MES": 3, "MBT": 1}
    assert audit.gaps == {"MES": 1}
