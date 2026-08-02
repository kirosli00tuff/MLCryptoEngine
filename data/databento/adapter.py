"""Map Databento GLBX.MDP3 records into the canonical event format.

Clock provenance — record it, never mix it: ``ts_event`` is the CME MDP3
exchange-side timestamp; ``ts_recv`` is Databento's capture-server hardware
receive timestamp. Neither is this project's recorder clock. Canonical rows
therefore carry ``ts_ns := ts_recv`` (the source's capture clock),
``exchange_ns := ts_event``, and ``source = "databento"`` — and rows with
``source="databento"`` must never be ordered against ``source="recorder"``
rows on ``ts_ns`` (different clocks on different machines; see the schema
docstring in data/store/parquet_writer.py).

Integrity the adapter actually verifies: per-instrument ``sequence``
monotonic continuity (:class:`SequenceAudit`) and crossed/locked detection on
the mapped books. Not applicable and reported as such: book checksums (MDP3
has none in this mapping) and snapshot cadence (MBP-10 is incremental depth).

Records arrive as plain dicts (see ``ingest.py`` for the client-object
conversion): prices are Databento fixed-point int64 scaled by 1e-9, with
INT64_MAX as the null sentinel for absent levels.
"""

from __future__ import annotations

from typing import Any

VENUE = "cme"
SOURCE = "databento"
PRICE_SCALE = 1e-9
NULL_PRICE = 9_223_372_036_854_775_807  # Databento UNDEF_PRICE sentinel


class SequenceAudit:
    """Per-symbol monotonic sequence continuity, counted not assumed."""

    def __init__(self) -> None:
        self.observations: dict[str, int] = {}
        self.gaps: dict[str, int] = {}
        self._last: dict[str, int] = {}

    def observe(self, symbol: str, sequence: int) -> bool:
        self.observations[symbol] = self.observations.get(symbol, 0) + 1
        last = self._last.get(symbol)
        self._last[symbol] = sequence
        if last is not None and sequence < last:
            self.gaps[symbol] = self.gaps.get(symbol, 0) + 1
            return False
        return True


def _level_lists(
    record: dict[str, Any],
) -> tuple[list[float], list[float], list[float], list[float]]:
    bid_prices: list[float] = []
    bid_qtys: list[float] = []
    ask_prices: list[float] = []
    ask_qtys: list[float] = []
    for level in record.get("levels", []):
        bid_px = level.get("bid_px", NULL_PRICE)
        ask_px = level.get("ask_px", NULL_PRICE)
        if bid_px != NULL_PRICE:
            bid_prices.append(bid_px * PRICE_SCALE)
            bid_qtys.append(float(level.get("bid_sz", 0)))
        if ask_px != NULL_PRICE:
            ask_prices.append(ask_px * PRICE_SCALE)
            ask_qtys.append(float(level.get("ask_sz", 0)))
    return bid_prices, bid_qtys, ask_prices, ask_qtys


def map_mbp10(record: dict[str, Any], symbol: str) -> dict[str, Any]:
    """One MBP-10 record → one canonical book snapshot row (kind="event")."""
    bid_prices, bid_qtys, ask_prices, ask_qtys = _level_lists(record)
    best_bid = bid_prices[0] if bid_prices else None
    bid_qty = bid_qtys[0] if bid_qtys else None
    best_ask = ask_prices[0] if ask_prices else None
    ask_qty = ask_qtys[0] if ask_qtys else None
    mid = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
    micro = None
    if best_bid is not None and best_ask is not None and bid_qty and ask_qty:
        micro = (bid_qty * best_ask + ask_qty * best_bid) / (bid_qty + ask_qty)
    valid = best_bid is not None and best_ask is not None
    return {
        "venue": VENUE,
        "symbol": symbol,
        "ts_ns": int(record["ts_recv"]),  # Databento capture hardware clock
        "exchange_ns": int(record["ts_event"]),  # CME exchange clock
        "source": SOURCE,
        "kind": "event",
        "valid": valid,
        "crossed": bool(
            valid and best_bid is not None and best_ask is not None and best_bid > best_ask
        ),
        "locked": bool(valid and best_bid == best_ask),
        "best_bid": best_bid,
        "bid_qty": bid_qty,
        "best_ask": best_ask,
        "ask_qty": ask_qty,
        "mid": mid,
        "microprice": micro,
        "bid_prices": bid_prices,
        "bid_qtys": bid_qtys,
        "ask_prices": ask_prices,
        "ask_qtys": ask_qtys,
        "seq": int(record["sequence"]) if record.get("sequence") is not None else None,
        # MBP-10 reports aggregate size per level, not resting order counts.
        "bid_n": None,
        "ask_n": None,
    }


def map_trade(record: dict[str, Any], symbol: str) -> dict[str, Any]:
    """One trades-schema record → one canonical trade row."""
    side_flag = record.get("side")
    side = {"B": "buy", "A": "sell"}.get(str(side_flag)) if side_flag is not None else None
    return {
        "venue": VENUE,
        "symbol": symbol,
        "ts_ns": int(record["ts_recv"]),
        "exchange_ns": int(record["ts_event"]),
        "price": record["price"] * PRICE_SCALE,
        "qty": float(record["size"]),
        "venue_side": side,
        "trade_id": str(record["sequence"]) if record.get("sequence") is not None else None,
        "source": SOURCE,
    }
