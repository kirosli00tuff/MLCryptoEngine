"""Bar samplers: time (comparison only), event, and imbalance."""

from __future__ import annotations

import pytest

from research.sampling.bars import EventBars, ImbalanceBars, TimeBars, samples_per_hour
from research.stream.events import BookState, StreamEvent, Trade

NS_PER_MS = 1_000_000
NS_PER_HOUR = 3_600_000 * NS_PER_MS
BASE_NS = 1_785_412_800 * 1_000_000_000


def _book_event(ts_ns: int) -> StreamEvent:
    book = BookState(100.0, 1.0, 101.0, 1.0, 100.5, 100.5, (100.0,), (1.0,), (101.0,), (1.0,), True)
    return StreamEvent("kraken", "BTC/USD", ts_ns, None, book, None)


def _trade_event(ts_ns: int) -> StreamEvent:
    return StreamEvent("kraken", "BTC/USD", ts_ns, ts_ns, None, Trade(100.5, 1.0, "buy"))


def test_time_bars_fire_on_wall_clock_boundaries() -> None:
    bars = TimeBars(interval_ms=1000)
    fired = [
        bars.update(_book_event(BASE_NS + offset_ms * NS_PER_MS), None)
        for offset_ms in (0, 100, 900, 1000, 1500, 2100)
    ]
    # First event initializes; boundary crossings at +1000 and +2100 fire.
    assert fired == [False, False, False, True, False, True]


def test_event_bars_count_only_the_configured_event_type() -> None:
    bars = EventBars(every_n=2)
    assert bars.update(_book_event(BASE_NS), None) is False
    assert bars.update(_trade_event(BASE_NS + 1), 1.0) is False, "trades not counted"
    assert bars.update(_book_event(BASE_NS + 2), None) is True
    assert bars.update(_book_event(BASE_NS + 3), None) is False


def test_imbalance_bars_fire_when_cumulative_signed_flow_crosses() -> None:
    bars = ImbalanceBars(threshold_qty=2.0)
    assert bars.update(_trade_event(BASE_NS), 1.5) is False
    assert bars.update(_trade_event(BASE_NS + 1), -0.4) is False  # cum 1.1
    assert bars.update(_trade_event(BASE_NS + 2), 1.0) is True  # cum 2.1 crosses
    assert bars.update(_trade_event(BASE_NS + 3), -1.9) is False, "accumulator reset"
    assert bars.update(_trade_event(BASE_NS + 4), -0.2) is True  # |-2.1| crosses


def test_samples_per_hour_makes_venue_rate_asymmetry_visible() -> None:
    ts = [BASE_NS + i * NS_PER_MS for i in range(3)] + [BASE_NS + NS_PER_HOUR]
    counts = samples_per_hour(ts)
    assert list(counts.values()) == [3, 1]


def test_samplers_reject_nonsense_configuration() -> None:
    with pytest.raises(ValueError):
        TimeBars(0)
    with pytest.raises(ValueError):
        EventBars(0)
    with pytest.raises(ValueError):
        EventBars(1, count="ticks")
    with pytest.raises(ValueError):
        ImbalanceBars(0.0)
