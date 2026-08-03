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
    # A crossed book (bid > ask) is not a book: its mid, spread, microprice
    # and every depth statistic are meaningless. Carried explicitly so the
    # feature engine can exclude those moments rather than computing
    # confident nonsense from them. Locked (bid == ask) is degenerate but
    # legitimate at a touch, so it is carried and reported without excluding.
    crossed: bool = False
    locked: bool = False

    @property
    def usable(self) -> bool:
        """True only when this state can support book-derived features."""
        return self.valid and not self.crossed


@dataclass(frozen=True, slots=True)
class Trade:
    """One executed trade; ``venue_side`` is the venue's flag verbatim."""

    price: float
    qty: float
    venue_side: str | None


@dataclass(frozen=True, slots=True)
class Bbo:
    """A top-of-book update: both touches, with resting order counts.

    Distinct from :class:`BookState` on purpose (ADR-013). A BBO update is
    an accurate, fast view of the touch and says nothing about depth; a
    BookState is a depth view that may be far staler. On Hyperliquid the
    two differ by more than an order of magnitude in cadence (123 ms vs
    5,387 ms measured), so conflating them would silently substitute
    5-second-old prices into sub-second features.
    """

    best_bid: float
    bid_qty: float
    best_ask: float
    ask_qty: float
    mid: float | None
    microprice: float | None
    bid_n: int | None = None
    ask_n: int | None = None


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event on the merged timeline: exactly one payload slot is set.

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
    bbo: Bbo | None = None
