"""Adverse selection: how far the mid runs against a passive fill.

A favourable spread-to-cost ratio is necessary and not sufficient. A resting
quote is not filled by a random counterparty — it is filled preferentially by
someone who wanted that side, and on a thin book that someone is more likely
to be informed. The cost of that is measurable directly from recorded data,
with no fill simulation: take every trade, sign it by aggressor direction, and
measure how far the mid moves in the aggressor's favour over the next few
hundred milliseconds.

That move is what a passive fill on the opposite side would have suffered. A
maker who sold at the ask to a buyer, then watched the mid rise 4 bps in one
second, earned half a spread and lost four basis points.

Sign convention: ``adverse_bps = aggressor_sign * (mid_after - mid_at) / mid_at``
in bps, where ``aggressor_sign`` is +1 for a buy. **Positive means adverse** —
the market moved the aggressor's way, against whoever filled them.

Resolution matches :mod:`research.labels.fixed_horizon`: a deadline resolves
against the last mid at or before it, never a later one, so nothing reads
information from the future. Pending trades are bounded by the longest horizon,
so memory is O(trades in flight) rather than O(trades in the day).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

NS_PER_MS = 1_000_000
DEFAULT_HORIZONS_MS: tuple[int, ...] = (100, 1_000, 5_000)


@dataclass
class _Pending:
    deadline_ns: int
    sign: int
    entry_mid: float


@dataclass
class AdverseSelection:
    """Signed post-trade mid drift for one instrument, at fixed horizons."""

    symbol: str
    horizons_ms: tuple[int, ...] = DEFAULT_HORIZONS_MS
    sums_bps: dict[int, float] = field(default_factory=dict)
    counts: dict[int, int] = field(default_factory=dict)
    trades: int = 0
    trades_without_mid: int = 0
    _queues: dict[int, deque[_Pending]] = field(default_factory=dict)
    _last_mid: float | None = None

    def __post_init__(self) -> None:
        for horizon in self.horizons_ms:
            self.sums_bps.setdefault(horizon, 0.0)
            self.counts.setdefault(horizon, 0)
            self._queues.setdefault(horizon, deque())

    def on_mid(self, ts_ns: int, mid: float) -> None:
        """Advance the clock, resolving any deadline that has now passed."""
        if mid <= 0.0:
            return
        for horizon, queue in self._queues.items():
            # Deadlines strictly before now resolve against the previous mid;
            # a deadline exactly at now resolves against this one.
            if self._last_mid is not None:
                while queue and queue[0].deadline_ns < ts_ns:
                    self._resolve(horizon, queue.popleft(), self._last_mid)
            while queue and queue[0].deadline_ns <= ts_ns:
                self._resolve(horizon, queue.popleft(), mid)
        self._last_mid = mid

    def _resolve(self, horizon_ms: int, pending: _Pending, exit_mid: float) -> None:
        move = (exit_mid - pending.entry_mid) / pending.entry_mid * 1e4
        self.sums_bps[horizon_ms] += pending.sign * move
        self.counts[horizon_ms] += 1

    def on_trade(self, ts_ns: int, sign: int) -> None:
        """Arm one trade. ``sign`` is +1 for a buy aggressor, -1 for a sell."""
        self.trades += 1
        if sign not in (1, -1):
            raise ValueError(f"aggressor sign must be +1 or -1, got {sign!r}")
        if self._last_mid is None:
            # No quote seen yet: there is no entry mid to measure against, and
            # inventing one would fabricate a move. Counted, not silently lost.
            self.trades_without_mid += 1
            return
        for horizon, queue in self._queues.items():
            queue.append(
                _Pending(
                    deadline_ns=ts_ns + horizon * NS_PER_MS,
                    sign=sign,
                    entry_mid=self._last_mid,
                )
            )

    def summary(self) -> dict[str, Any]:
        """Mean adverse move per horizon. Unresolved trades stay uncounted."""
        return {
            "symbol": self.symbol,
            "trades": self.trades,
            "trades_without_mid": self.trades_without_mid,
            "mean_adverse_bps": {
                str(h): (self.sums_bps[h] / self.counts[h] if self.counts[h] else None)
                for h in self.horizons_ms
            },
            "resolved": {str(h): self.counts[h] for h in self.horizons_ms},
        }
