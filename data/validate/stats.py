"""Inter-message arrival distribution with bounded memory.

A day of tick data can run to tens of millions of messages, so deltas are
binned into fixed log-spaced buckets rather than stored. Percentiles are
approximated by each bucket's upper bound — precise enough to spot a feed
that stalls, which is what the validation harness cares about.
"""

from __future__ import annotations

from bisect import bisect_left

from pydantic import BaseModel

BUCKET_BOUNDS_MS: list[float] = [
    0.01,
    0.05,
    0.1,
    0.5,
    1.0,
    5.0,
    10.0,
    50.0,
    100.0,
    500.0,
    1_000.0,
    5_000.0,
    30_000.0,
]


class ArrivalStats(BaseModel):
    """Serializable summary of the arrival distribution."""

    bounds_ms: list[float]
    counts: list[int]
    count: int
    max_ms: float
    p50_ms: float
    p90_ms: float
    p99_ms: float


class ArrivalHistogram:
    """Accumulates inter-message deltas (milliseconds) into log-spaced buckets."""

    def __init__(self) -> None:
        # One overflow bucket beyond the last bound.
        self._counts = [0] * (len(BUCKET_BOUNDS_MS) + 1)
        self._count = 0
        self._max_ms = 0.0

    def add(self, delta_ms: float) -> None:
        self._counts[bisect_left(BUCKET_BOUNDS_MS, delta_ms)] += 1
        self._count += 1
        if delta_ms > self._max_ms:
            self._max_ms = delta_ms

    def _percentile(self, fraction: float) -> float:
        if self._count == 0:
            return 0.0
        target = fraction * self._count
        cumulative = 0
        for index, bucket_count in enumerate(self._counts):
            cumulative += bucket_count
            if cumulative >= target:
                if index < len(BUCKET_BOUNDS_MS):
                    return BUCKET_BOUNDS_MS[index]
                return self._max_ms
        return self._max_ms

    def snapshot(self) -> ArrivalStats:
        return ArrivalStats(
            bounds_ms=BUCKET_BOUNDS_MS,
            counts=list(self._counts),
            count=self._count,
            max_ms=round(self._max_ms, 3),
            p50_ms=self._percentile(0.50),
            p90_ms=self._percentile(0.90),
            p99_ms=self._percentile(0.99),
        )
