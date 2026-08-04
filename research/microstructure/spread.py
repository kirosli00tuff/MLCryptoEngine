"""Time-weighted spread distribution for one instrument, in bounded memory.

Spread capture economics turn on the spread you can *earn* against the cost
you must *pay*, so the spread has to be weighted by the time it was actually
quoted rather than by the number of updates. An instrument that sits wide for
an hour and then flickers tight a thousand times in a minute has a very
different mean under the two weightings, and only the time-weighted one
describes what a resting quote would have faced.

Percentiles come from a log-spaced weighted histogram rather than a retained
list of observations — the same rule as every other accumulator in this
project, and for the same reason: a day of bbo updates is millions of values,
and retaining them is the defect that has now cost this project five OOM
incidents.

Thresholds at 3, 6 and 12 bps are exact bin edges, so "fraction of time wider
than 6 bps" is an exact figure rather than an interpolation.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Any

NS_PER_S = 1_000_000_000
# Log-spaced, with the reporting thresholds as exact edges.
BOUNDS_BPS: tuple[float, ...] = (
    0.02,
    0.05,
    0.1,
    0.2,
    0.3,
    0.5,
    0.75,
    1.0,
    1.5,
    2.0,
    3.0,
    4.0,
    6.0,
    8.0,
    12.0,
    20.0,
    35.0,
    60.0,
    100.0,
    200.0,
    500.0,
)
REPORT_THRESHOLDS: tuple[float, ...] = (3.0, 6.0, 12.0)


@dataclass
class SpreadCensus:
    """Accumulates time-weighted spread statistics for one instrument."""

    symbol: str
    weight_ns: list[float] = field(default_factory=lambda: [0.0] * (len(BOUNDS_BPS) + 1))
    total_ns: int = 0
    sum_weighted_bps: float = 0.0
    updates: int = 0
    crossed_or_locked: int = 0
    min_bps: float | None = None
    max_bps: float | None = None
    _last_ns: int | None = None
    _last_bps: float | None = None

    def observe(self, ts_ns: int, bid: float, ask: float) -> None:
        """Record a quote. The *previous* spread is credited with the elapsed time."""
        self.updates += 1
        if bid <= 0.0 or ask <= 0.0:
            return
        mid = 0.5 * (bid + ask)
        if mid <= 0.0:
            return
        bps = (ask - bid) / mid * 1e4
        if bps <= 0.0:
            # Crossed or locked: counted and reported, never folded into the
            # distribution as though it were a quotable spread (ADR-019's rule).
            self.crossed_or_locked += 1
            self._credit(ts_ns)
            self._last_ns, self._last_bps = ts_ns, None
            return
        self._credit(ts_ns)
        self._last_ns, self._last_bps = ts_ns, bps
        self.min_bps = bps if self.min_bps is None else min(self.min_bps, bps)
        self.max_bps = bps if self.max_bps is None else max(self.max_bps, bps)

    def _credit(self, ts_ns: int) -> None:
        if self._last_ns is None or self._last_bps is None:
            return
        dt = ts_ns - self._last_ns
        if dt <= 0:
            return
        self.total_ns += dt
        self.sum_weighted_bps += self._last_bps * dt
        self.weight_ns[bisect_left(BOUNDS_BPS, self._last_bps)] += dt

    def close(self, ts_ns: int) -> None:
        """Credit the final quote's time up to ``ts_ns``."""
        self._credit(ts_ns)
        self._last_ns, self._last_bps = None, None

    def _percentile(self, q: float) -> float | None:
        if self.total_ns <= 0:
            return None
        target = q * self.total_ns
        run = 0.0
        for i, w in enumerate(self.weight_ns):
            run += w
            if run >= target:
                return BOUNDS_BPS[i] if i < len(BOUNDS_BPS) else BOUNDS_BPS[-1]
        return BOUNDS_BPS[-1]

    def fraction_wider_than(self, bps: float) -> float | None:
        """Fraction of quoted time with a spread strictly wider than ``bps``.

        ``bps`` must be one of :data:`BOUNDS_BPS`; the bin edge makes the
        answer exact instead of an interpolation across a bin.
        """
        if self.total_ns <= 0:
            return None
        index = bisect_left(BOUNDS_BPS, bps)
        if index >= len(BOUNDS_BPS) or BOUNDS_BPS[index] != bps:
            raise ValueError(f"{bps} is not an exact histogram edge; add it to BOUNDS_BPS")
        return sum(self.weight_ns[index + 1 :]) / self.total_ns

    def summary(self) -> dict[str, Any]:
        mean = self.sum_weighted_bps / self.total_ns if self.total_ns else None
        return {
            "symbol": self.symbol,
            "updates": self.updates,
            "quoted_hours": self.total_ns / (3600 * NS_PER_S),
            "mean_bps": mean,
            "median_bps": self._percentile(0.5),
            "p90_bps": self._percentile(0.9),
            "min_bps": self.min_bps,
            "max_bps": self.max_bps,
            "crossed_or_locked": self.crossed_or_locked,
            "frac_wider_than": {f"{t:g}": self.fraction_wider_than(t) for t in REPORT_THRESHOLDS},
        }
