"""Streaming feature engine for one venue/symbol.

Point-in-time contract, enforced structurally: the pipeline calls
:meth:`compute` for a sample at time ``t`` *before* calling :meth:`on_event`
with the event stamped ``t``, so every feature value is a function of events
with local timestamp strictly less than ``t``. No centered windows, no
forward fills, no rolling statistic that includes the current event.

Per-event work is O(1) amortized (deque appends and window-sum updates);
:meth:`compute` does bounded work per sample. Nothing per-event is retained
beyond the longest rolling window, so a full day streams in bounded memory.
"""

from __future__ import annotations

import math
from collections import deque
from itertools import pairwise

from research.features import book as bookfeat
from research.features.capabilities import REQUIRED_CHANNELS, supported_features
from research.features.cross_venue import CrossVenueTracker
from research.features.rolling import WindowSum
from research.features.signing import sign_trade
from research.stream.events import Bbo, BookState, StreamEvent

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000
LEVELS = 5
INTERARRIVAL_TRADES = 50
# Interarrival stats are bounded by count AND age, so the effective lookback
# can never silently exceed what the pipeline's gap-validity check covers.
INTERARRIVAL_MAX_AGE_NS = 60 * NS_PER_S

FEATURE_COLUMNS: list[str] = [
    "ofi_best_1s",
    "ofi_best_5s",
    "ofi_deep_1s",
    "ofi_deep_5s",
    "qimb_best",
    "micro_minus_mid",
    "spread_abs",
    "spread_bps",
    *[f"depth_bid_{i}" for i in range(1, LEVELS + 1)],
    *[f"depth_ask_{i}" for i in range(1, LEVELS + 1)],
    "slope_bid",
    "slope_ask",
    "book_asym",
    "dwp_minus_mid",
    "signed_vol_1s",
    "signed_vol_5s",
    "signed_vol_30s",
    "trade_count_5s",
    "interarrival_mean_ms",
    "interarrival_std_ms",
    "vwap_minus_mid_5s",
    "time_since_trade_ms",
    "rvol_1s",
    "rvol_5s",
    "rvol_30s",
    "ret_1s",
    "abs_ret_1s",
    "xv_mid_diff_bps",
    "xv_diff_z",
    "xv_leadlag_m500",
    "xv_leadlag_m100",
    "xv_leadlag_0",
    "xv_leadlag_p100",
    "xv_leadlag_p500",
]

_XV_COLUMN_BY_OFFSET = {
    -500: "xv_leadlag_m500",
    -100: "xv_leadlag_m100",
    0: "xv_leadlag_0",
    100: "xv_leadlag_p100",
    500: "xv_leadlag_p500",
}


class FeatureEngine:
    """Accumulates stream events and produces one feature dict per sample."""

    def __init__(self, venue: str, symbol: str, cross: CrossVenueTracker | None = None) -> None:
        self.venue = venue
        self.symbol = symbol
        self._cross = cross
        # Capability matrix consultation happens here, once: features the
        # venue's feed cannot support are nulled in every compute() output
        # rather than computed as garbage (e.g. OFI from snapshot deltas).
        # Raises for undeclared venues — defaults closed.
        # Per-contract where the matrix declares one (CME MES vs MBT differ by
        # 39x in event rate), venue-wide otherwise.
        self._unsupported = frozenset(FEATURE_COLUMNS) - supported_features(venue, symbol)
        # Venues with a dedicated BBO channel take their touch and mid from
        # it; their book feed is depth-only and much slower.
        self._prefers_bbo_mid = venue in REQUIRED_CHANNELS
        self._touch: Bbo | None = None
        self._prev_book: BookState | None = None
        self._last_mid: float | None = None
        self._ofi_best = {1: WindowSum(NS_PER_S), 5: WindowSum(5 * NS_PER_S)}
        self._ofi_deep = {1: WindowSum(NS_PER_S), 5: WindowSum(5 * NS_PER_S)}
        self._signed_vol = {
            1: WindowSum(NS_PER_S),
            5: WindowSum(5 * NS_PER_S),
            30: WindowSum(30 * NS_PER_S),
        }
        self._r2 = {
            1: WindowSum(NS_PER_S),
            5: WindowSum(5 * NS_PER_S),
            30: WindowSum(30 * NS_PER_S),
        }
        self._ret_1s = WindowSum(NS_PER_S)
        self._vwap_pq_5s = WindowSum(5 * NS_PER_S)
        self._vwap_q_5s = WindowSum(5 * NS_PER_S)
        self._trade_count_5s = WindowSum(5 * NS_PER_S)
        self._trade_ts: deque[int] = deque(maxlen=INTERARRIVAL_TRADES)
        self._last_trade_price: float | None = None
        self._last_trade_sign = 0
        self._last_trade_ns: int | None = None

    @property
    def last_mid(self) -> float | None:
        """Last valid mid applied — the entry price known strictly before now."""
        return self._last_mid

    @property
    def book_is_valid(self) -> bool:
        book = self._prev_book
        return book is not None and book.valid

    def preview_signed_qty(
        self, trade_price: float, trade_qty: float, venue_side: str | None
    ) -> float:
        """Signed qty of a trade *without* applying it — pre-t state only."""
        sign = sign_trade(
            self.venue, venue_side, trade_price, self._last_trade_price, self._last_trade_sign
        )
        return sign * trade_qty

    # -- state updates -----------------------------------------------------

    def on_event(self, event: StreamEvent) -> float | None:
        """Apply one event; returns the signed trade qty for trade events."""
        if event.bbo is not None:
            self._on_bbo(event)
            return None
        if event.book is not None:
            self._on_book(event)
            return None
        if event.trade is not None:
            return self._on_trade(event)
        return None

    def _on_bbo(self, event: StreamEvent) -> None:
        """Top-of-book update: the touch, the mid, and everything derived.

        On a venue that has a BBO channel this is the authoritative price
        view — book snapshots there are far staler (Hyperliquid: 5,387 ms vs
        123 ms), so :meth:`_on_book` yields the mid series to this method
        rather than interleaving two different-latency views of the same
        touch into one return series.
        """
        bbo = event.bbo
        assert bbo is not None
        self._touch = bbo
        if bbo.mid is not None and bbo.mid > 0:
            self._observe_mid(event.local_ns, bbo.mid)

    def _observe_mid(self, ts: int, mid: float) -> None:
        """Fold one mid observation into returns, realized vol, and cross-venue."""
        if self._last_mid is not None and self._last_mid > 0:
            log_ret = math.log(mid / self._last_mid)
            for window in self._r2.values():
                window.add(ts, log_ret * log_ret)
            self._ret_1s.add(ts, log_ret)
        self._last_mid = mid
        if self._cross is not None:
            self._cross.on_mid("primary", ts, mid)

    def _on_book(self, event: StreamEvent) -> None:
        book = event.book
        assert book is not None
        ts = event.local_ns
        prev = self._prev_book
        if prev is not None and prev.valid and book.valid:
            best = bookfeat.ofi_best(prev, book)
            if best is not None:
                self._ofi_best[1].add(ts, best)
                self._ofi_best[5].add(ts, best)
            deep = bookfeat.ofi_deep(prev, book, LEVELS)
            if deep is not None:
                self._ofi_deep[1].add(ts, deep)
                self._ofi_deep[5].add(ts, deep)
        # On BBO venues the book is the slow, depth-only view: it must not
        # inject stale mids into the return series that bbo already drives.
        if not self._prefers_bbo_mid and book.valid and book.mid is not None and book.mid > 0:
            self._observe_mid(ts, book.mid)
        self._prev_book = book

    def _on_trade(self, event: StreamEvent) -> float:
        trade = event.trade
        assert trade is not None
        ts = event.local_ns
        sign = sign_trade(
            self.venue, trade.venue_side, trade.price, self._last_trade_price, self._last_trade_sign
        )
        signed_qty = sign * trade.qty
        for window in self._signed_vol.values():
            window.add(ts, signed_qty)
        self._vwap_pq_5s.add(ts, trade.price * trade.qty)
        self._vwap_q_5s.add(ts, trade.qty)
        self._trade_count_5s.add(ts, 1.0)
        self._trade_ts.append(ts)
        self._last_trade_price = trade.price
        if sign != 0:
            self._last_trade_sign = sign
        self._last_trade_ns = ts
        return signed_qty

    def on_reference_mid(self, ts_ns: int, mid: float) -> None:
        if self._cross is not None:
            self._cross.on_mid("reference", ts_ns, mid)

    # -- sampling ----------------------------------------------------------

    def compute(self, t_ns: int) -> dict[str, float | None]:
        """Feature vector from state strictly before ``t_ns``."""
        book = self._prev_book
        out: dict[str, float | None] = dict.fromkeys(FEATURE_COLUMNS)
        out["ofi_best_1s"] = self._ofi_best[1].total(t_ns)
        out["ofi_best_5s"] = self._ofi_best[5].total(t_ns)
        out["ofi_deep_1s"] = self._ofi_deep[1].total(t_ns)
        out["ofi_deep_5s"] = self._ofi_deep[5].total(t_ns)
        touch = self._touch
        if self._prefers_bbo_mid and touch is not None:
            # Touch-derived features come from the fast BBO channel; depth
            # features stay unsupported on these venues and are nulled below.
            out["spread_abs"] = touch.best_ask - touch.best_bid
            out["spread_bps"] = (
                1e4 * (touch.best_ask - touch.best_bid) / touch.mid
                if touch.mid is not None and touch.mid > 0
                else None
            )
            out["micro_minus_mid"] = (
                touch.microprice - touch.mid
                if touch.microprice is not None and touch.mid is not None
                else None
            )
            total = touch.bid_qty + touch.ask_qty
            out["qimb_best"] = (touch.bid_qty - touch.ask_qty) / total if total > 0 else None
        if book is not None and book.valid:
            if not self._prefers_bbo_mid:
                out["qimb_best"] = bookfeat.queue_imbalance(book)
                out["micro_minus_mid"] = bookfeat.microprice_minus_mid(book)
                out["spread_abs"] = bookfeat.spread(book)
                out["spread_bps"] = bookfeat.spread_bps(book)
            bids, asks = bookfeat.depth_at_levels(book, LEVELS)
            for i in range(LEVELS):
                out[f"depth_bid_{i + 1}"] = bids[i]
                out[f"depth_ask_{i + 1}"] = asks[i]
            out["slope_bid"], out["slope_ask"] = bookfeat.book_slope(book, LEVELS)
            out["book_asym"] = bookfeat.book_asymmetry(book, LEVELS)
            out["dwp_minus_mid"] = bookfeat.depth_weighted_price_minus_mid(book, LEVELS)
        out["signed_vol_1s"] = self._signed_vol[1].total(t_ns)
        out["signed_vol_5s"] = self._signed_vol[5].total(t_ns)
        out["signed_vol_30s"] = self._signed_vol[30].total(t_ns)
        out["trade_count_5s"] = self._trade_count_5s.total(t_ns)
        out["interarrival_mean_ms"], out["interarrival_std_ms"] = self._interarrival_ms(t_ns)
        vwap_qty = self._vwap_q_5s.total(t_ns)
        if vwap_qty > 0 and self._last_mid is not None:
            out["vwap_minus_mid_5s"] = self._vwap_pq_5s.total(t_ns) / vwap_qty - self._last_mid
        if self._last_trade_ns is not None:
            out["time_since_trade_ms"] = (t_ns - self._last_trade_ns) / NS_PER_MS
        for seconds, window in self._r2.items():
            out[f"rvol_{seconds}s"] = math.sqrt(max(window.total(t_ns), 0.0))
        out["ret_1s"] = self._ret_1s.total(t_ns)
        out["abs_ret_1s"] = abs(self._ret_1s.total(t_ns))
        if self._cross is not None:
            out["xv_mid_diff_bps"] = self._cross.mid_diff_bps()
            out["xv_diff_z"] = self._cross.diff_zscore(t_ns)
            for offset, corr in self._cross.leadlag().items():
                out[_XV_COLUMN_BY_OFFSET[offset]] = corr
        for name in self._unsupported:
            out[name] = None
        return out

    def _interarrival_ms(self, t_ns: int) -> tuple[float | None, float | None]:
        cutoff = t_ns - INTERARRIVAL_MAX_AGE_NS
        recent = [ts for ts in self._trade_ts if ts >= cutoff]
        if len(recent) < 3:
            return None, None
        deltas = [(b - a) / NS_PER_MS for a, b in pairwise(recent)]
        mean = sum(deltas) / len(deltas)
        variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
        return mean, math.sqrt(variance)
