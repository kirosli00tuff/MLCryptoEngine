"""Event types for the point-in-time research stream.

Two timestamps, one rule: ``local_ns`` is the recorder's receive time — when
the information actually became available to us — and is the only clock used
for ordering, feature windows, and label horizons. ``exchange_ns`` is what
the venue claims; it is kept for reference and never ordered on. Book events
carry only ``local_ns`` because the Phase A book schema records receive time;
trades carry both.

A feature computed at time ``t`` may read only events with
``local_ns`` strictly less than ``t``. The pipeline enforces this by
computing features from accumulated state *before* applying the event that
triggered the sample.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BookState:
    """One reconstructed L2 book observation (top ``N`` levels)."""

    best_bid: float | None
    bid_qty: float | None
    best_ask: float | None
    ask_qty: float | None
    mid: float | None
    microprice: float | None
    bid_prices: tuple[float, ...]
    bid_qtys: tuple[float, ...]
    ask_prices: tuple[float, ...]
    ask_qtys: tuple[float, ...]
    valid: bool


@dataclass(frozen=True, slots=True)
class Trade:
    """One executed trade; ``venue_side`` is the venue's flag verbatim."""

    price: float
    qty: float
    venue_side: str | None


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event on the merged timeline: exactly one of ``book``/``trade`` set.

    ``is_warmup`` marks previous-day tail events used only to warm feature
    state; they are never sampled, labeled, or trained on.
    """

    venue: str
    symbol: str
    local_ns: int
    exchange_ns: int | None
    book: BookState | None
    trade: Trade | None
    is_warmup: bool = False
