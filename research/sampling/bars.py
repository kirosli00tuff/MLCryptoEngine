"""Bar samplers: time bars (comparison only), event bars, imbalance bars.

Default to event or imbalance bars. Time bars oversample quiet periods and
undersample exactly the moments that matter — they exist here only as the
comparison baseline. Kraken runs roughly 3-9x Coinbase's message rate
depending on session, so identical event-bar settings produce very different
sample counts per venue over the same wall-clock window;
:func:`samples_per_hour` makes that visible instead of surprising.

Reference: Lopez de Prado, *Advances in Financial Machine Learning* (2018),
ch. 2 — information-driven bars.
"""

from __future__ import annotations

from collections import Counter
from typing import Protocol

from research.stream.events import StreamEvent

NS_PER_HOUR = 3_600 * 1_000_000_000


class Sampler(Protocol):
    """Decides, per event, whether a sample is due at that event's timestamp.

    ``update`` sees every stream event in order (warm-up events included, so
    state is realistic at the day boundary) but the pipeline only *acts* on
    True for non-warm-up events. ``signed_qty`` is the signed trade volume of
    the event when it is a trade (see research/features/signing.py), else None.
    """

    def update(self, event: StreamEvent, signed_qty: float | None) -> bool: ...


class TimeBars:
    """Sample on fixed wall-clock boundaries. Comparison baseline only."""

    def __init__(self, interval_ms: int) -> None:
        if interval_ms <= 0:
            raise ValueError("interval_ms must be positive")
        self._interval_ns = interval_ms * 1_000_000
        self._next_ns: int | None = None

    def update(self, event: StreamEvent, signed_qty: float | None) -> bool:
        if self._next_ns is None:
            self._next_ns = (event.local_ns // self._interval_ns + 1) * self._interval_ns
            return False
        if event.local_ns >= self._next_ns:
            self._next_ns = (event.local_ns // self._interval_ns + 1) * self._interval_ns
            return True
        return False


class EventBars:
    """Sample every N events — book updates by default, trades if requested."""

    def __init__(self, every_n: int, count: str = "book") -> None:
        if every_n <= 0:
            raise ValueError("every_n must be positive")
        if count not in ("book", "trade"):
            raise ValueError(f"count must be 'book' or 'trade', got {count!r}")
        self._every_n = every_n
        self._count_trades = count == "trade"
        self._seen = 0

    def update(self, event: StreamEvent, signed_qty: float | None) -> bool:
        counted = event.trade is not None if self._count_trades else event.book is not None
        if not counted:
            return False
        self._seen += 1
        if self._seen >= self._every_n:
            self._seen = 0
            return True
        return False


class ImbalanceBars:
    """Sample when cumulative signed order flow crosses a threshold.

    Signed trade volume accumulates; a sample fires when |cumulative| reaches
    ``threshold_qty`` (in base units) and the accumulator resets. Quiet,
    balanced flow produces few samples; one-sided bursts produce many —
    sampling density follows information arrival.
    """

    def __init__(self, threshold_qty: float) -> None:
        if threshold_qty <= 0:
            raise ValueError("threshold_qty must be positive")
        self._threshold = threshold_qty
        self._cum = 0.0

    def update(self, event: StreamEvent, signed_qty: float | None) -> bool:
        if event.trade is None or signed_qty is None:
            return False
        self._cum += signed_qty
        if abs(self._cum) >= self._threshold:
            self._cum = 0.0
            return True
        return False


def samples_per_hour(sample_ts_ns: list[int]) -> dict[int, int]:
    """Sample count per UTC hour-of-epoch bucket → count, for rate visibility."""
    return dict(sorted(Counter(ts // NS_PER_HOUR for ts in sample_ts_ns).items()))
