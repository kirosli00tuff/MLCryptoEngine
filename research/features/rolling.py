"""Rolling time-window aggregates with O(1) amortized updates.

The feature engine sees every event once; per-event work must be constant, so
window sums are maintained incrementally (append + prune) rather than
recomputed per sample. Values contribute at their event's local timestamp and
leave the window exactly ``window_ns`` later.
"""

from __future__ import annotations

from collections import deque


class WindowSum:
    """Sum (and count) of values whose timestamp is within the trailing window."""

    def __init__(self, window_ns: int) -> None:
        if window_ns <= 0:
            raise ValueError("window_ns must be positive")
        self._window_ns = window_ns
        self._items: deque[tuple[int, float]] = deque()
        self._total = 0.0

    def add(self, ts_ns: int, value: float) -> None:
        self._items.append((ts_ns, value))
        self._total += value

    def _prune(self, now_ns: int) -> None:
        cutoff = now_ns - self._window_ns
        items = self._items
        while items and items[0][0] <= cutoff:
            _, value = items.popleft()
            self._total -= value

    def total(self, now_ns: int) -> float:
        self._prune(now_ns)
        return self._total

    def count(self, now_ns: int) -> int:
        self._prune(now_ns)
        return len(self._items)
