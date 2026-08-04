"""Spread census and adverse selection: the two measures Stage C.9 rests on.

Both are accumulators over a stream, and both have a way of being subtly wrong
that still produces a plausible number — the spread by weighting updates
instead of time, the adverse move by reading a mid from after its deadline.
These tests pin the distinction in each case.
"""

from __future__ import annotations

import pytest

from research.microstructure import AdverseSelection, SpreadCensus

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000
BASE = 1_780_000_000 * NS_PER_S


def test_spread_is_weighted_by_time_not_by_update_count() -> None:
    # Arrange: 1 bp quoted for 100 s, then ~11 bps quoted for 1 s, flickering
    # 10 times. Update-weighting is dragged toward the wide quote; time
    # weighting reports what a resting order actually faced.
    census = SpreadCensus(symbol="X")
    census.observe(BASE, 100.0, 100.01)  # 1.0 bps
    t = BASE + 100 * NS_PER_S
    for i in range(10):
        census.observe(t + i * NS_PER_S // 10, 100.0, 100.11)  # ~11 bps
    census.close(t + NS_PER_S)

    # Act
    summary = census.summary()
    mean = summary["mean_bps"]
    assert isinstance(mean, float)

    # Assert
    naive_update_mean = (1.0 + 10 * 10.99) / 11
    assert mean == pytest.approx(1.099, abs=0.02), "100 s at 1 bp dominates 1 s at 11 bps"
    assert mean < naive_update_mean / 5, "update-weighting would report ~10x this"
    assert summary["quoted_hours"] == pytest.approx(101 / 3600, rel=1e-6)


def test_fraction_wider_than_is_exact_at_reporting_thresholds() -> None:
    # Arrange: half the time at 2 bps, half at 8 bps.
    census = SpreadCensus(symbol="X")
    census.observe(BASE, 100.0, 100.02)  # 2.0 bps
    census.observe(BASE + 10 * NS_PER_S, 100.0, 100.08)  # 8.0 bps
    census.close(BASE + 20 * NS_PER_S)

    # Act / Assert
    assert census.fraction_wider_than(3.0) == pytest.approx(0.5)
    assert census.fraction_wider_than(6.0) == pytest.approx(0.5)
    assert census.fraction_wider_than(12.0) == pytest.approx(0.0)


def test_a_threshold_that_is_not_a_bin_edge_is_refused() -> None:
    census = SpreadCensus(symbol="X")
    census.observe(BASE, 100.0, 100.02)
    census.close(BASE + NS_PER_S)
    with pytest.raises(ValueError, match="exact histogram edge"):
        census.fraction_wider_than(7.0)


def test_crossed_quotes_are_counted_and_kept_out_of_the_distribution() -> None:
    # Arrange: a crossed book is not a spread anyone could have quoted.
    census = SpreadCensus(symbol="X")
    census.observe(BASE, 100.0, 100.02)
    census.observe(BASE + NS_PER_S, 100.05, 100.0)  # crossed
    census.close(BASE + 2 * NS_PER_S)

    # Act
    summary = census.summary()

    # Assert
    assert summary["crossed_or_locked"] == 1
    # 0.02 on a mid of 100.01 is 1.9998 bps, not 2.0 — the mid is the divisor.
    assert summary["mean_bps"] == pytest.approx(2.0, abs=0.001), "only the quotable second counts"
    assert summary["quoted_hours"] == pytest.approx(1 / 3600, rel=1e-6)


def test_adverse_move_is_positive_when_the_market_follows_the_aggressor() -> None:
    # Arrange: a buyer lifts the offer, then the mid rises 5 bps. The maker who
    # sold to them is 5 bps worse off.
    adv = AdverseSelection(symbol="X", horizons_ms=(1_000,))
    adv.on_mid(BASE, 100.0)
    adv.on_trade(BASE, sign=1)
    adv.on_mid(BASE + 1_000 * NS_PER_MS, 100.05)

    # Act
    mean = adv.summary()["mean_adverse_bps"]["1000"]

    # Assert
    assert mean == pytest.approx(5.0, abs=0.01), "positive means adverse to the passive side"


def test_adverse_move_is_negative_when_the_market_moves_against_the_aggressor() -> None:
    # Arrange: a buyer lifts the offer and the mid then falls — the maker who
    # sold to them profited, so the adverse move is negative.
    adv = AdverseSelection(symbol="X", horizons_ms=(1_000,))
    adv.on_mid(BASE, 100.0)
    adv.on_trade(BASE, sign=1)
    adv.on_mid(BASE + 1_000 * NS_PER_MS, 99.95)

    # Act / Assert
    assert adv.summary()["mean_adverse_bps"]["1000"] == pytest.approx(-5.0, abs=0.01)


def test_sell_aggressor_signs_the_move_the_other_way() -> None:
    # Arrange: a seller hits the bid and the mid falls — adverse to the maker
    # who bought.
    adv = AdverseSelection(symbol="X", horizons_ms=(1_000,))
    adv.on_mid(BASE, 100.0)
    adv.on_trade(BASE, sign=-1)
    adv.on_mid(BASE + 1_000 * NS_PER_MS, 99.90)

    # Act / Assert
    assert adv.summary()["mean_adverse_bps"]["1000"] == pytest.approx(10.0, abs=0.01)


def test_deadline_resolves_against_the_last_mid_before_it_never_a_later_one() -> None:
    # Arrange: the deadline is 1 s. A mid exists at 0.9 s, and the next quote
    # only arrives at 30 s after a large move. Resolving against the 30 s quote
    # would read the future into a one-second measurement.
    adv = AdverseSelection(symbol="X", horizons_ms=(1_000,))
    adv.on_mid(BASE, 100.0)
    adv.on_trade(BASE, sign=1)
    adv.on_mid(BASE + 900 * NS_PER_MS, 100.01)
    adv.on_mid(BASE + 30 * NS_PER_S, 150.0)

    # Act
    mean = adv.summary()["mean_adverse_bps"]["1000"]

    # Assert
    assert mean == pytest.approx(1.0, abs=0.01), (
        "must use the 0.9 s mid, not the 30 s one — otherwise a quiet stretch "
        "imports a much later move into the horizon"
    )


def test_trades_before_any_quote_are_counted_not_silently_dropped() -> None:
    # Arrange: no mid yet, so there is no entry price to measure against.
    adv = AdverseSelection(symbol="X", horizons_ms=(1_000,))
    adv.on_trade(BASE, sign=1)
    adv.on_mid(BASE + NS_PER_S, 100.0)

    # Act
    summary = adv.summary()

    # Assert
    assert summary["trades"] == 1
    assert summary["trades_without_mid"] == 1
    assert summary["resolved"]["1000"] == 0
    assert summary["mean_adverse_bps"]["1000"] is None, "no observation, not a zero"


def test_an_unsigned_trade_is_rejected_rather_than_assumed() -> None:
    adv = AdverseSelection(symbol="X", horizons_ms=(1_000,))
    adv.on_mid(BASE, 100.0)
    with pytest.raises(ValueError, match="aggressor sign"):
        adv.on_trade(BASE, sign=0)
