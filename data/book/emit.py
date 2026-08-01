"""Emit reconstructed book snapshots at event-driven and fixed-interval cadences.

Rows are plain dicts with Parquet-friendly types (floats, lists of floats);
the storage layer owns the schema. Interval rows are stamped at the interval
boundary and carry the book state as of the last event before that boundary,
so a quiet market still produces one row per interval.
"""

from __future__ import annotations

from typing import Any

from data.book.builder import BookBuilder

NS_PER_MS = 1_000_000


class SnapshotEmitter:
    """Produces top-of-book + depth rows for one builder."""

    def __init__(self, builder: BookBuilder, interval_ms: int, depth: int) -> None:
        self._builder = builder
        self._interval_ns = interval_ms * NS_PER_MS
        self._depth = depth
        self._next_interval_ns: int | None = None

    def _row(self, ts_ns: int, kind: str, seq: int | None) -> dict[str, Any]:
        b = self._builder
        bid, ask = b.best_bid, b.best_ask
        mid = b.mid
        micro = b.microprice
        bid_levels = b.bid_levels(self._depth)
        ask_levels = b.ask_levels(self._depth)
        return {
            "venue": b.venue,
            "symbol": b.symbol,
            "ts_ns": ts_ns,
            # Recorder-produced rows: ts_ns is our local receive clock; the
            # feeds carry no usable per-event exchange timestamp.
            "exchange_ns": None,
            "source": "recorder",
            "kind": kind,
            "valid": b.valid,
            "crossed": b.is_crossed,
            "locked": b.is_locked,
            "best_bid": float(bid.price) if bid else None,
            "bid_qty": float(bid.qty) if bid else None,
            "best_ask": float(ask.price) if ask else None,
            "ask_qty": float(ask.qty) if ask else None,
            "mid": float(mid) if mid is not None else None,
            "microprice": float(micro) if micro is not None else None,
            "bid_prices": [float(lv.price) for lv in bid_levels],
            "bid_qtys": [float(lv.qty) for lv in bid_levels],
            "ask_prices": [float(lv.price) for lv in ask_levels],
            "ask_qtys": [float(lv.qty) for lv in ask_levels],
            "seq": seq,
        }

    def on_event(self, ts_ns: int, seq: int | None = None) -> list[dict[str, Any]]:
        """Rows due after one applied event: catch-up interval rows, then the event row."""
        rows: list[dict[str, Any]] = []
        if self._next_interval_ns is None:
            self._next_interval_ns = (ts_ns // self._interval_ns + 1) * self._interval_ns
        else:
            while self._next_interval_ns <= ts_ns:
                rows.append(self._row(self._next_interval_ns, "interval", seq))
                self._next_interval_ns += self._interval_ns
        rows.append(self._row(ts_ns, "event", seq))
        return rows
