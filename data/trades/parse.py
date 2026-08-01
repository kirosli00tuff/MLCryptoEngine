"""Parse raw trade messages into rows matching ``TRADE_SCHEMA``.

Both timestamps are kept: ``ts_ns`` is the recorder's local receive time —
when the information was actually available to us — and is what all ordering
and feature horizons use. ``exchange_ns`` is what the venue claims and is
never used for ordering.

Snapshot-type trade messages are deliberately skipped on both venues: they
replay trades that executed before the subscription (and re-arrive on every
reconnect), so including them would inject pre-session history at the
subscribe timestamp and duplicate trades across reconnects.

``venue_side`` is recorded verbatim. Kraken WS v2 documents ``side`` as the
taker (aggressor) side; Coinbase Advanced Trade ``market_trades`` side
semantics are not clearly documented, so downstream signing uses the venue
flag for Kraken and the tick rule for Coinbase — see
:mod:`research.features.signing`, which records the method per venue.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

VENUE_KRAKEN = "kraken"
VENUE_COINBASE = "coinbase"
VENUE_HYPERLIQUID = "hyperliquid"

TradeRow = dict[str, Any]


def iso_to_ns(value: str) -> int | None:
    """ISO-8601 ``...Z`` timestamp to epoch nanoseconds; None when malformed.

    Handles any number of fractional digits (venues send 6 or 9) without the
    float round-trip that would lose nanosecond precision.
    """
    try:
        base, _, frac = value.removesuffix("Z").partition(".")
        stamp = datetime.fromisoformat(base).replace(tzinfo=UTC)
        frac_ns = int((frac + "000000000")[:9]) if frac else 0
    except ValueError:
        return None
    return int(stamp.timestamp()) * 10**9 + frac_ns


def parse_kraken_trades(message: dict[str, Any], recv_ns: int) -> list[TradeRow]:
    """Trade rows in a raw Kraken WS v2 trade update; empty for other messages."""
    if message.get("channel") != "trade" or message.get("type") != "update":
        return []
    data = message.get("data")
    if not isinstance(data, list):
        return []
    rows: list[TradeRow] = []
    for item in data:
        if not isinstance(item, dict) or "symbol" not in item:
            continue
        try:
            price = float(item["price"])
            qty = float(item["qty"])
        except (KeyError, TypeError, ValueError):
            continue
        side = item.get("side")
        trade_id = item.get("trade_id")
        rows.append(
            {
                "venue": VENUE_KRAKEN,
                "symbol": str(item["symbol"]),
                "ts_ns": recv_ns,
                "exchange_ns": iso_to_ns(str(item.get("timestamp", ""))),
                "price": price,
                "qty": qty,
                "venue_side": str(side) if side is not None else None,
                "trade_id": str(trade_id) if trade_id is not None else None,
                "source": "recorder",
            }
        )
    return rows


def parse_coinbase_trades(message: dict[str, Any], recv_ns: int) -> list[TradeRow]:
    """Trade rows in a raw Coinbase market_trades update; empty for other messages."""
    if message.get("channel") != "market_trades":
        return []
    events = message.get("events")
    if not isinstance(events, list):
        return []
    rows: list[TradeRow] = []
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "update":
            continue
        trades = event.get("trades")
        if not isinstance(trades, list):
            continue
        for item in trades:
            if not isinstance(item, dict) or "product_id" not in item:
                continue
            try:
                price = float(item["price"])
                qty = float(item["size"])
            except (KeyError, TypeError, ValueError):
                continue
            side = item.get("side")
            trade_id = item.get("trade_id")
            rows.append(
                {
                    "venue": VENUE_COINBASE,
                    "symbol": str(item["product_id"]),
                    "ts_ns": recv_ns,
                    "exchange_ns": iso_to_ns(str(item.get("time", ""))),
                    "price": price,
                    "qty": qty,
                    "venue_side": str(side) if side is not None else None,
                    "trade_id": str(trade_id) if trade_id is not None else None,
                    "source": "recorder",
                }
            )
    return rows


def parse_hyperliquid_trades(message: dict[str, Any], recv_ns: int) -> list[TradeRow]:
    """Trade rows in a raw Hyperliquid trades message; empty otherwise.

    The venue's ``side`` is the taker direction ("B" buy / "A" sell) and is
    normalized to "buy"/"sell" so downstream signing can use the flag
    directly. ``time`` is exchange milliseconds → ``exchange_ns``; ordering
    still uses the recorder's ``recv_ns``.
    """
    if message.get("channel") != "trades":
        return []
    data = message.get("data")
    if not isinstance(data, list):
        return []
    rows: list[TradeRow] = []
    for item in data:
        if not isinstance(item, dict) or "coin" not in item:
            continue
        try:
            price = float(item["px"])
            qty = float(item["sz"])
        except (KeyError, TypeError, ValueError):
            continue
        side_flag = item.get("side")
        side = {"B": "buy", "A": "sell"}.get(str(side_flag)) if side_flag is not None else None
        time_ms = item.get("time")
        trade_id = item.get("tid")
        rows.append(
            {
                "venue": VENUE_HYPERLIQUID,
                "symbol": str(item["coin"]),
                "ts_ns": recv_ns,
                "exchange_ns": int(time_ms) * 1_000_000 if isinstance(time_ms, int) else None,
                "price": price,
                "qty": qty,
                "venue_side": side,
                "trade_id": str(trade_id) if trade_id is not None else None,
                "source": "recorder",
            }
        )
    return rows


PARSERS = {
    VENUE_KRAKEN: parse_kraken_trades,
    VENUE_COINBASE: parse_coinbase_trades,
    VENUE_HYPERLIQUID: parse_hyperliquid_trades,
}
