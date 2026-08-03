"""Bounded interval statistics: horizon counters and percentiles without retention."""

from __future__ import annotations

import sys

from data.databento.validate import IntervalStats
from research.labels.fixed_horizon import DEFAULT_HORIZONS_MS


def test_counts_intervals_below_each_label_horizon() -> None:
    stats = IntervalStats()
    # 100 intervals: 60 at 50 ms, 30 at 700 ms, 10 at 40 s.
    for _ in range(60):
        stats.add(50.0)
    for _ in range(30):
        stats.add(700.0)
    for _ in range(10):
        stats.add(40_000.0)

    assert stats.count == 100
    assert stats.below_horizon[100] == 60  # only the 50 ms ones
    assert stats.below_horizon[500] == 60
    assert stats.below_horizon[1_000] == 90  # + the 700 ms ones
    assert stats.below_horizon[30_000] == 90
    assert stats.below_horizon[60_000] == 100  # + the 40 s ones
    assert stats.share_below(1_000) == 0.9
    assert stats.max_ms == 40_000.0


def test_percentiles_bracket_the_distribution() -> None:
    stats = IntervalStats()
    for _ in range(90):
        stats.add(0.08)  # fast
    for _ in range(10):
        stats.add(900.0)  # slow tail

    # p50 sits in the fast bucket, p99 out in the tail.
    assert stats.percentile_ms(0.5) <= 0.1
    assert stats.percentile_ms(0.99) >= 500.0


def test_empty_is_not_a_silent_zero() -> None:
    stats = IntervalStats()
    assert stats.count == 0
    assert stats.percentile_ms(0.5) != stats.percentile_ms(0.5)  # NaN
    assert stats.share_below(100) != stats.share_below(100)  # NaN
    assert all(v == 0 for v in stats.below_horizon.values())


def test_memory_is_bounded_regardless_of_sample_count() -> None:
    """The whole point: 15 million intervals must not retain 15 million floats."""
    small = IntervalStats()
    big = IntervalStats()
    for _ in range(100):
        small.add(1.0)
    for i in range(200_000):
        big.add(float(i % 1000))

    assert big.count == 200_000
    # Internal state is the same size either way: fixed buckets + fixed counters.
    assert len(big._buckets) == len(small._buckets)
    assert len(big.below_horizon) == len(small.below_horizon) == len(DEFAULT_HORIZONS_MS)
    assert sys.getsizeof(big._buckets) == sys.getsizeof(small._buckets)
