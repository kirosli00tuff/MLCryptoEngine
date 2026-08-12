"""Tick geometry: the actual minimum price increment, and the spread in ticks.

Hyperliquid perp prices carry at most 5 significant figures and no more than
``6 - szDecimals`` decimal places (integer prices are always allowed), so the
tick is a *fraction of price* rather than a constant. Whether a measured spread
is quotable-inside depends on how many ticks wide it is: a spread pinned at one
or two ticks admits no price improvement, which collapses the D.1a
always-first/always-last range toward its always-last end.

The accumulator time-weights the spread expressed in ticks, the same weighting
rule as :mod:`research.microstructure.spread` and for the same reason — what a
resting quote faced, not how often the quote flickered.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# Perps: prices carry at most MAX_DECIMALS - szDecimals decimal places.
MAX_DECIMALS_PERP = 6
_SIG_FIGS = 5
# Spread-in-ticks histogram: exact integer bins 1..10, and one overflow bin.
_OVERFLOW_BIN = 11


def tick_size(price: float, sz_decimals: int) -> float:
    """Minimum price increment at ``price`` for an instrument's ``szDecimals``.

    Two constraints bind: 5 significant figures (an increment of
    ``10^(floor(log10 p) - 4)``, never above 1 because integer prices are always
    allowed) and the decimal cap (an increment of ``10^-(6 - szDecimals)``).
    The tick is the larger of the two.
    """
    if price <= 0.0:
        raise ValueError(f"price must be positive, got {price!r}")
    sig_increment = min(10.0 ** (math.floor(math.log10(price)) - (_SIG_FIGS - 1)), 1.0)
    decimal_cap = 10.0 ** -(MAX_DECIMALS_PERP - sz_decimals)
    return max(sig_increment, decimal_cap)


def tick_bps(price: float, sz_decimals: int) -> float:
    """The tick at ``price`` expressed in basis points of price."""
    return tick_size(price, sz_decimals) / price * 1e4


@dataclass
class SpreadTicks:
    """Time-weighted distribution of the touch spread measured in ticks."""

    symbol: str
    sz_decimals: int
    weight_ns: dict[int, int] = field(default_factory=dict)
    total_ns: int = 0
    sum_tick_bps_ns: float = 0.0
    crossed_or_locked: int = 0
    min_mid: float | None = None
    max_mid: float | None = None
    last_mid: float | None = None
    _last_ns: int | None = None
    _last_ticks: int | None = None
    _last_tick_bps: float | None = None

    def observe(self, ts_ns: int, bid: float, ask: float) -> None:
        """Record a quote; the previous spread-in-ticks is credited its time."""
        if bid <= 0.0 or ask <= 0.0:
            return
        mid = 0.5 * (bid + ask)
        self.min_mid = mid if self.min_mid is None else min(self.min_mid, mid)
        self.max_mid = mid if self.max_mid is None else max(self.max_mid, mid)
        self.last_mid = mid
        if ask <= bid:
            self.crossed_or_locked += 1
            self._credit(ts_ns)
            self._last_ns, self._last_ticks, self._last_tick_bps = ts_ns, None, None
            return
        tick = tick_size(mid, self.sz_decimals)
        # On-grid quotes differ by whole ticks; round absorbs float parse fuzz,
        # and a positive spread narrower than one tick (a quote straddling a
        # significant-figure decade boundary) still counts as one tick wide.
        ticks = min(max(round((ask - bid) / tick), 1), _OVERFLOW_BIN)
        self._credit(ts_ns)
        self._last_ns, self._last_ticks = ts_ns, ticks
        self._last_tick_bps = tick / mid * 1e4

    def _credit(self, ts_ns: int) -> None:
        if self._last_ns is None or self._last_ticks is None or self._last_tick_bps is None:
            return
        dt = ts_ns - self._last_ns
        if dt <= 0:
            return
        self.total_ns += dt
        self.weight_ns[self._last_ticks] = self.weight_ns.get(self._last_ticks, 0) + dt
        self.sum_tick_bps_ns += self._last_tick_bps * dt

    def close(self, ts_ns: int) -> None:
        """Credit the final state's time up to ``ts_ns``."""
        self._credit(ts_ns)
        self._last_ns, self._last_ticks, self._last_tick_bps = None, None, None

    def median_ticks(self) -> int | None:
        """Time-weighted median spread in ticks."""
        if self.total_ns <= 0:
            return None
        run = 0
        for ticks in sorted(self.weight_ns):
            run += self.weight_ns[ticks]
            if 2 * run >= self.total_ns:
                return ticks
        return _OVERFLOW_BIN

    def fraction_at_most(self, ticks: int) -> float | None:
        """Fraction of quoted time with a spread of at most ``ticks`` ticks."""
        if self.total_ns <= 0:
            return None
        return sum(w for k, w in self.weight_ns.items() if k <= ticks) / self.total_ns

    def summary(self) -> dict[str, Any]:
        mean_tick = self.sum_tick_bps_ns / self.total_ns if self.total_ns else None
        return {
            "symbol": self.symbol,
            "sz_decimals": self.sz_decimals,
            "quoted_hours": self.total_ns / 3.6e12,
            "tick_bps_time_weighted_mean": mean_tick,
            "median_spread_ticks": self.median_ticks(),
            "frac_le_1_tick": self.fraction_at_most(1),
            "frac_le_2_ticks": self.fraction_at_most(2),
            "frac_le_3_ticks": self.fraction_at_most(3),
            "min_mid": self.min_mid,
            "max_mid": self.max_mid,
            "last_mid": self.last_mid,
            "tick_at_last_mid": (
                tick_size(self.last_mid, self.sz_decimals) if self.last_mid else None
            ),
            "crossed_or_locked": self.crossed_or_locked,
        }
