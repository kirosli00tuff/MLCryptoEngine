"""L2 book maintenance with sequence validation and crossed/locked detection.

The builder never silently interpolates: on a sequence gap or checksum failure
the book is marked invalid and stays invalid until a fresh snapshot arrives.
Crossed and locked books are the primary correctness signal — they are counted
and flagged, never repaired.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from enum import StrEnum

from data.book.types import BookEvent, Level

ChecksumFn = Callable[[list[Level], list[Level]], int]


class ApplyResult(StrEnum):
    """Outcome of applying one event to the book."""

    SNAPSHOT = "snapshot"
    APPLIED = "applied"
    IGNORED_INVALID = "ignored_invalid"
    SEQ_GAP = "seq_gap"
    CHECKSUM_FAILED = "checksum_failed"


class SequenceTracker:
    """Contiguity check for venues with per-connection sequence numbers."""

    def __init__(self) -> None:
        self._last: int | None = None
        self.gaps = 0
        # How many sequence numbers were actually inspected. Zero gaps out of
        # zero observations is not evidence of continuity, and the validation
        # harness reports the two together so it can never be read that way.
        self.observations = 0

    def reset_counts(self) -> None:
        """Zero the gap/observation counters but keep the last-seen sequence.

        Used at the day boundary after a warm-up replay: continuity across
        midnight must still be checked, but observations made while warming
        belong to the previous day.
        """
        self.gaps = 0
        self.observations = 0

    def observe(self, seq: int) -> bool:
        """Record ``seq``; True when contiguous (or first), False on a gap."""
        self.observations += 1
        last = self._last
        self._last = seq
        if last is None or seq == last + 1:
            return True
        # A restarted feed legitimately resets to 0/1; treat backward jumps as
        # resets (new connection), forward jumps as data loss.
        if seq <= last:
            self.reset()
            self._last = seq
            return True
        self.gaps += 1
        return False

    def reset(self) -> None:
        self._last = None


class BookBuilder:
    """Maintains one venue/symbol L2 book from snapshot + incremental events."""

    def __init__(
        self,
        venue: str,
        symbol: str,
        depth: int,
        checksum_fn: ChecksumFn | None = None,
    ) -> None:
        self.venue = venue
        self.symbol = symbol
        self.depth = depth
        self._checksum_fn = checksum_fn
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._sorted_bids: list[Decimal] | None = []
        self._sorted_asks: list[Decimal] | None = []
        self.valid = False
        self.last_event_ns: int | None = None
        # Counters consumed by the validation harness.
        self.events_applied = 0
        self.snapshots_applied = 0
        self.ignored_while_invalid = 0
        self.seq_gaps = 0
        self.checksum_failures = 0
        # Checksums actually compared. A venue-day with zero failures out of
        # zero comparisons has not been integrity-checked at all; the harness
        # scores the pair, never the failure count alone.
        self.checksums_verified = 0
        self.crossed_events = 0
        self.locked_events = 0

    # -- state application ------------------------------------------------

    def apply(self, event: BookEvent, seq_ok: bool = True) -> ApplyResult:
        """Apply one normalized event. ``seq_ok=False`` signals an upstream gap."""
        self.last_event_ns = event.recv_ns
        if event.is_snapshot:
            self._load_snapshot(event)
            self._after_change()
            return ApplyResult.SNAPSHOT

        if not seq_ok:
            self.seq_gaps += 1
            self.invalidate()
            return ApplyResult.SEQ_GAP

        if not self.valid:
            self.ignored_while_invalid += 1
            return ApplyResult.IGNORED_INVALID

        for level in event.bids:
            self._set_level(self._bids, level)
        for level in event.asks:
            self._set_level(self._asks, level)
        self._truncate()
        self._dirty()
        self.events_applied += 1
        self._after_change()

        if event.checksum is not None and self._checksum_fn is not None:
            self.checksums_verified += 1
            computed = self._checksum_fn(self.bid_levels(10), self.ask_levels(10))
            if computed != event.checksum:
                self.checksum_failures += 1
                self.invalidate()
                return ApplyResult.CHECKSUM_FAILED
        return ApplyResult.APPLIED

    def invalidate(self) -> None:
        """Mark the book untrustworthy until the next snapshot."""
        self.valid = False
        self._bids.clear()
        self._asks.clear()
        self._dirty()

    def reset_counters(self) -> None:
        """Zero every scoring counter while keeping book state and validity.

        Used at the day boundary after a warm-up replay: the warmed book is
        the target day's starting condition, but events applied while warming
        belong to the previous day and must not be scored against this one.
        """
        self.events_applied = 0
        self.snapshots_applied = 0
        self.ignored_while_invalid = 0
        self.seq_gaps = 0
        self.checksum_failures = 0
        self.checksums_verified = 0
        self.crossed_events = 0
        self.locked_events = 0

    def _load_snapshot(self, event: BookEvent) -> None:
        self._bids = {lv.price: lv.qty for lv in event.bids if lv.qty > 0}
        self._asks = {lv.price: lv.qty for lv in event.asks if lv.qty > 0}
        self._truncate()
        self._dirty()
        self.valid = True
        self.snapshots_applied += 1

    @staticmethod
    def _set_level(side: dict[Decimal, Decimal], level: Level) -> None:
        if level.qty <= 0:
            side.pop(level.price, None)
        else:
            side[level.price] = level.qty

    def _truncate(self) -> None:
        if len(self._bids) > self.depth:
            for price in sorted(self._bids, reverse=True)[self.depth :]:
                del self._bids[price]
        if len(self._asks) > self.depth:
            for price in sorted(self._asks)[self.depth :]:
                del self._asks[price]

    def _dirty(self) -> None:
        self._sorted_bids = None
        self._sorted_asks = None

    def _after_change(self) -> None:
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return
        if bid.price > ask.price:
            self.crossed_events += 1
        elif bid.price == ask.price:
            self.locked_events += 1

    # -- views -------------------------------------------------------------

    def _bids_sorted(self) -> list[Decimal]:
        if self._sorted_bids is None:
            self._sorted_bids = sorted(self._bids, reverse=True)
        return self._sorted_bids

    def _asks_sorted(self) -> list[Decimal]:
        if self._sorted_asks is None:
            self._sorted_asks = sorted(self._asks)
        return self._sorted_asks

    @property
    def best_bid(self) -> Level | None:
        prices = self._bids_sorted()
        return Level(prices[0], self._bids[prices[0]]) if prices else None

    @property
    def best_ask(self) -> Level | None:
        prices = self._asks_sorted()
        return Level(prices[0], self._asks[prices[0]]) if prices else None

    @property
    def is_crossed(self) -> bool:
        bid, ask = self.best_bid, self.best_ask
        return bid is not None and ask is not None and bid.price > ask.price

    @property
    def is_locked(self) -> bool:
        bid, ask = self.best_bid, self.best_ask
        return bid is not None and ask is not None and bid.price == ask.price

    @property
    def mid(self) -> Decimal | None:
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return None
        return (bid.price + ask.price) / 2

    @property
    def microprice(self) -> Decimal | None:
        """Queue-weighted mid: (bid_qty*ask_px + ask_qty*bid_px) / (bid_qty+ask_qty)."""
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return None
        total = bid.qty + ask.qty
        if total == 0:
            return None
        return (bid.qty * ask.price + ask.qty * bid.price) / total

    def bid_levels(self, n: int) -> list[Level]:
        return [Level(p, self._bids[p]) for p in self._bids_sorted()[:n]]

    def ask_levels(self, n: int) -> list[Level]:
        return [Level(p, self._asks[p]) for p in self._asks_sorted()[:n]]
