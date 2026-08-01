"""Trade extraction and the merged point-in-time stream."""

from __future__ import annotations

import random
from pathlib import Path

import orjson

from data.config import AppConfig, load_config
from data.recorder.writer import RawFileWriter
from data.store import BookDayWriter, TradesDayWriter
from data.trades.extract import extract_trades_day
from data.trades.parse import iso_to_ns, parse_coinbase_trades, parse_kraken_trades
from research.stream.reader import merged_stream
from tests.test_leakage import _book_row  # shared synthetic book-row builder

DATE = "2026-07-30"
PREV = "2026-07-29"
BASE_NS = 1_785_412_800 * 1_000_000_000  # 2026-07-30T12:00:00Z
NS_PER_S = 1_000_000_000

KRAKEN_TRADE = {
    "channel": "trade",
    "type": "update",
    "data": [
        {
            "symbol": "BTC/USD",
            "side": "buy",
            "price": 63732.7,
            "qty": 0.00015574,
            "ord_type": "limit",
            "trade_id": 104543030,
            "timestamp": "2026-07-31T12:00:00.150089Z",
        }
    ],
}
COINBASE_TRADE_ITEMS = [
    {
        "product_id": "BTC-USD",
        "trade_id": "1064891097",
        "price": "63738.74",
        "size": "0.006",
        "time": "2026-07-31T12:00:00.278163Z",
        "side": "BUY",
    }
]
COINBASE_TRADE = {
    "channel": "market_trades",
    "sequence_num": 84080,
    "events": [{"type": "update", "trades": COINBASE_TRADE_ITEMS}],
}


def test_iso_to_ns_handles_micro_and_nanosecond_fractions() -> None:
    assert iso_to_ns("2026-07-30T12:00:00.000000Z") == BASE_NS
    assert iso_to_ns("2026-07-30T12:00:00.359808705Z") == BASE_NS + 359_808_705
    assert iso_to_ns("not a timestamp") is None


def test_kraken_trade_parses_with_aggressor_flag_and_both_timestamps() -> None:
    (row,) = parse_kraken_trades(KRAKEN_TRADE, recv_ns=123)
    assert row["ts_ns"] == 123, "local receive time is the ordering clock"
    assert row["exchange_ns"] == iso_to_ns("2026-07-31T12:00:00.150089Z")
    assert (row["venue_side"], row["price"], row["qty"]) == ("buy", 63732.7, 0.00015574)


def test_coinbase_trade_parses_and_snapshots_are_excluded() -> None:
    (row,) = parse_coinbase_trades(COINBASE_TRADE, recv_ns=456)
    assert (row["symbol"], row["venue_side"]) == ("BTC-USD", "BUY")
    snapshot = {
        "channel": "market_trades",
        "events": [{"type": "snapshot", "trades": COINBASE_TRADE_ITEMS}],
    }
    assert parse_coinbase_trades(snapshot, recv_ns=1) == []
    kraken_snapshot = {**KRAKEN_TRADE, "type": "snapshot"}
    assert parse_kraken_trades(kraken_snapshot, recv_ns=1) == []


def test_extract_trades_day_round_trips_raw_capture(tmp_path: Path) -> None:
    writer = RawFileWriter(tmp_path / "raw", "kraken")
    try:
        for i in range(5):
            writer.write(BASE_NS + i * NS_PER_S, orjson.dumps(KRAKEN_TRADE).decode())
    finally:
        writer.close()
    cfg = AppConfig(data_root=tmp_path, logs_dir=tmp_path / "logs", venues=load_config().venues)

    written = extract_trades_day(cfg, "kraken", DATE)

    assert written == {"BTC/USD": 5}


def test_merged_stream_orders_by_local_ns_and_flags_warmup(tmp_path: Path) -> None:
    rng = random.Random(1)
    books = BookDayWriter(tmp_path, "kraken", "BTC/USD", DATE)
    trades = TradesDayWriter(tmp_path, "kraken", "BTC/USD", DATE)
    prev_books = BookDayWriter(tmp_path, "kraken", "BTC/USD", PREV)
    day_start_ns = BASE_NS - 12 * 3600 * NS_PER_S
    # Previous-day tail: one event inside the warm-up window, one before it.
    prev_books.append([_book_row(day_start_ns - 200 * NS_PER_S, 50_000.0, rng)])
    prev_books.append([_book_row(day_start_ns - 10 * NS_PER_S, 50_001.0, rng)])
    prev_books.close()
    for i in range(3):
        books.append([_book_row(day_start_ns + i * NS_PER_S, 50_000.0 + i, rng)])
    trades.append(
        [
            {
                "venue": "kraken",
                "symbol": "BTC/USD",
                "ts_ns": day_start_ns + NS_PER_S + 1,
                "exchange_ns": None,
                "price": 50_000.0,
                "qty": 1.0,
                "venue_side": "sell",
                "trade_id": "t1",
            }
        ]
    )
    books.close()
    trades.close()

    events = list(merged_stream(tmp_path, "kraken", "BTC/USD", DATE, warmup_s=120))

    ts = [e.local_ns for e in events]
    assert ts == sorted(ts), "stream must be ordered by local receive timestamp"
    warmups = [e for e in events if e.is_warmup]
    assert len(warmups) == 1, "only the tail inside the warm-up window is included"
    assert warmups[0].local_ns == day_start_ns - 10 * NS_PER_S
    assert sum(1 for e in events if e.trade is not None) == 1
    trade_event = next(e for e in events if e.trade is not None)
    assert not trade_event.is_warmup
