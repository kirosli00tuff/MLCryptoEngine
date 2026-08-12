"""Per-trade net capture at longer horizons, in bounded memory.

The C.27 census judged net = trade-time spread - adverse - 3.0 bps at 1, 5 and
60 second horizons. Slower informed flow would not appear at those horizons, so
D.1c re-scores the *same fills* at 300 and 900 seconds (with 60 s kept as a
known-answer cross-check against C.27's published means).

Resolution semantics are exactly those of
:class:`research.microstructure.registered.RegisteredInstrument`: a deadline
strictly before a quote resolves against the previous mid, one at the quote's
instant resolves against that quote's mid. The difference is storage — Welford
running moments instead of retained rows, because 900 s of pending trades on a
1.15M-trade instrument must not hold the week in memory.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from scipy.stats import t as student_t

NS_PER_MS = 1_000_000
D1C_HORIZONS_MS: tuple[int, ...] = (60_000, 300_000, 900_000)
ROUND_TRIP_BPS = 3.0
CONFIDENCE = 0.95


@dataclass
class _Armed:
    deadline_ns: int
    trade_ns: int
    sign: int
    entry_mid: float
    spread_bps: float


@dataclass
class _Welford:
    """Running mean and M2; variance without retaining observations."""

    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)

    def variance(self) -> float | None:
        return self.m2 / (self.n - 1) if self.n > 1 else None


@dataclass
class HorizonNet:
    """Streaming net-capture moments for one instrument at fixed horizons."""

    symbol: str
    half_split_ns: int
    horizons_ms: tuple[int, ...] = D1C_HORIZONS_MS
    net: dict[int, _Welford] = field(default_factory=dict)
    sum_adverse_bps: dict[int, float] = field(default_factory=dict)
    half_sums: dict[int, list[float]] = field(default_factory=dict)
    half_counts: dict[int, list[int]] = field(default_factory=dict)
    trades: int = 0
    trades_without_quote: int = 0
    _queues: dict[int, deque[_Armed]] = field(default_factory=dict)
    _last_mid: float | None = None
    _last_spread_bps: float | None = None

    def __post_init__(self) -> None:
        for horizon in self.horizons_ms:
            self.net.setdefault(horizon, _Welford())
            self.sum_adverse_bps.setdefault(horizon, 0.0)
            self.half_sums.setdefault(horizon, [0.0, 0.0])
            self.half_counts.setdefault(horizon, [0, 0])
            self._queues.setdefault(horizon, deque())

    def on_quote(self, ts_ns: int, bid: float, ask: float) -> None:
        if bid <= 0.0 or ask <= 0.0:
            return
        mid = 0.5 * (bid + ask)
        spread = (ask - bid) / mid * 1e4
        for horizon, queue in self._queues.items():
            if self._last_mid is not None:
                while queue and queue[0].deadline_ns < ts_ns:
                    self._resolve(horizon, queue.popleft(), self._last_mid)
            while queue and queue[0].deadline_ns <= ts_ns:
                self._resolve(horizon, queue.popleft(), mid)
        self._last_mid = mid
        self._last_spread_bps = spread if spread > 0.0 else None

    def _resolve(self, horizon_ms: int, armed: _Armed, exit_mid: float) -> None:
        adverse = armed.sign * (exit_mid - armed.entry_mid) / armed.entry_mid * 1e4
        net = armed.spread_bps - adverse - ROUND_TRIP_BPS
        self.net[horizon_ms].update(net)
        self.sum_adverse_bps[horizon_ms] += adverse
        half = 0 if armed.trade_ns < self.half_split_ns else 1
        self.half_sums[horizon_ms][half] += net
        self.half_counts[horizon_ms][half] += 1

    def on_trade(self, ts_ns: int, sign: int) -> None:
        self.trades += 1
        if self._last_mid is None or self._last_spread_bps is None:
            self.trades_without_quote += 1
            return
        for horizon, queue in self._queues.items():
            queue.append(
                _Armed(
                    deadline_ns=ts_ns + horizon * NS_PER_MS,
                    trade_ns=ts_ns,
                    sign=sign,
                    entry_mid=self._last_mid,
                    spread_bps=self._last_spread_bps,
                )
            )

    def summary(self) -> dict[str, Any]:
        per_horizon: dict[str, dict[str, Any]] = {}
        for horizon in self.horizons_ms:
            w = self.net[horizon]
            entry: dict[str, Any] = {"n": w.n}
            variance = w.variance()
            if w.n > 2 and variance is not None:
                se = math.sqrt(variance / w.n)
                crit = float(student_t.ppf(0.5 + CONFIDENCE / 2, w.n - 1))
                entry.update(
                    {
                        "net_mean_bps": w.mean,
                        "ci95_lower_bps": w.mean - crit * se,
                        "mean_adverse_bps": self.sum_adverse_bps[horizon] / w.n,
                        "half_net_means_bps": [
                            (s / c if c else None)
                            for s, c in zip(
                                self.half_sums[horizon], self.half_counts[horizon], strict=True
                            )
                        ],
                    }
                )
            per_horizon[str(horizon)] = entry
        return {
            "symbol": self.symbol,
            "trades": self.trades,
            "trades_without_quote": self.trades_without_quote,
            "per_horizon": per_horizon,
        }
