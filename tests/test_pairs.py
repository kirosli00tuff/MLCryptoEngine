"""Pairs trading: the ways this study could have lied to itself.

Every test here pins a defect that produces a *better-looking* result when it
is present, which is why none can be left to a smoke test:

- a z-score that includes its own bar flatters every entry;
- a spread scored on the window its pair was selected on is look-ahead, and it
  produced the top-ranked result in this stage's first run;
- a multiple-testing correction that does not bite makes 83 coin flips look
  like 83 discoveries;
- a Sharpe not deflated for the search rewards screening more pairs.
"""

from __future__ import annotations

import numpy as np
import pytest
from statsmodels.stats.multitest import multipletests

from research.pairs import backtest as bt
from research.pairs import validation
from research.pairs.cointegration import (
    EngleGranger,
    engle_granger,
    hedge_ratio,
    johansen,
    rolling_hedge_ratios,
)
from research.pairs.screening import PairResult, ScreenResult

NS_PER_DAY = 86_400_000_000_000


def _cointegrated(n: int = 500, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """A genuine pair: a shared stochastic trend plus a stationary spread."""
    rng = np.random.default_rng(seed)
    common = np.cumsum(rng.normal(0, 0.01, n))
    noise = np.zeros(n)
    for i in range(1, n):  # mean-reverting AR(1) spread
        noise[i] = 0.85 * noise[i - 1] + rng.normal(0, 0.01)
    return common + noise, common


def _independent_walks(n: int = 500, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(0, 0.01, n)), np.cumsum(rng.normal(0, 0.01, n))


def test_engle_granger_separates_a_real_pair_from_two_random_walks() -> None:
    # Arrange
    y_true, x_true = _cointegrated()
    y_fake, x_fake = _independent_walks()

    # Act
    real = engle_granger("A", "B", y_true, x_true)
    fake = engle_granger("A", "B", y_fake, x_fake)

    # Assert
    assert real is not None and fake is not None
    assert real.p_value < 0.01, "a stationary spread must reject the unit root"
    assert fake.p_value > 0.10, "two independent walks must not look cointegrated"


def test_johansen_agrees_with_engle_granger_on_an_unambiguous_pair() -> None:
    y, x = _cointegrated()

    result = johansen("A", "B", y, x)

    assert result is not None
    assert result.rejects_no_cointegration


def test_rolling_hedge_ratio_never_uses_the_bar_it_is_used_on() -> None:
    """The point-in-time guarantee, tested by contradiction: corrupting the
    future must not change any earlier estimate."""
    # Arrange
    y, x = _cointegrated(300)
    window = 60
    baseline = rolling_hedge_ratios(y, x, window)

    # Act: destroy everything from bar 200 onward.
    tampered_y, tampered_x = y.copy(), x.copy()
    tampered_y[200:] += 100.0
    tampered_x[200:] -= 100.0
    after = rolling_hedge_ratios(tampered_y, tampered_x, window)

    # Assert: estimates at or before bar 200 are untouched.
    np.testing.assert_allclose(baseline[:201], after[:201], rtol=0, atol=0, equal_nan=True)
    assert np.all(np.isnan(baseline[:window])), "no ratio exists before a full window"


def test_zscore_excludes_its_own_bar() -> None:
    # Arrange: a quiet oscillating spread with one spike inside it. The
    # oscillation matters — a perfectly flat window has zero dispersion and is
    # correctly refused rather than scored.
    spread = 0.1 * np.array([(-1.0) ** i for i in range(20)])
    spread[15] = 10.0

    # Act
    z = bt.zscores(spread, window=5)

    # Assert: the spike scores against the five quiet bars before it, so it is
    # enormous. Including itself would have shrunk both the gap and the sigma.
    assert np.isnan(z[4]), "a bar without a full prior window cannot be scored"
    assert abs(z[15]) > 50.0
    # The bar after the spike is measured against a window the spike now
    # dominates, so it reads as far below the mean.
    assert z[16] < 0.0


def test_a_flat_window_is_refused_rather_than_scored_as_infinite() -> None:
    """Zero dispersion has no z-score. Substituting a small epsilon would turn
    a dead market into an infinitely confident signal."""
    z = bt.zscores(np.zeros(10), window=4)

    assert np.all(np.isnan(z))


def test_positions_enter_at_the_threshold_and_exit_on_the_crossing() -> None:
    # Arrange: below -entry, then back through zero.
    z = np.array([0.0, -2.5, -1.0, 0.5, 0.0])

    # Act
    pos = bt.positions_from_z(z, entry=2.0, exit_at=0.0, max_hold=99)

    # Assert
    assert pos.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0], "long the spread, out when z >= 0"


def test_a_position_is_abandoned_after_the_maximum_hold() -> None:
    # Arrange: z goes extreme and stays there — the spread never reverts.
    z = np.concatenate([[0.0], np.full(20, -3.0)])

    # Act
    pos = bt.positions_from_z(z, entry=2.0, exit_at=0.0, max_hold=5)

    # Assert: entered at bar 1, released after max_hold bars.
    assert pos[1] == 1.0
    assert pos[6] == 0.0, "must not ride a broken spread forever"


def test_break_even_cost_is_the_cost_that_zeroes_the_net_return() -> None:
    # Arrange: 4% gross over 20 one-way turns.
    result = bt.PairBacktest(
        left="A",
        right="B",
        bars=365,
        years=1.0,
        gross_return=0.04,
        daily_returns=np.full(365, 0.04 / 365),
        one_way_turns=20.0,
        trades=10,
    )

    # Act
    break_even = result.break_even_bps

    # Assert: 2 * 0.04 / (20 * 1e-4) = 40 bps per round trip.
    assert break_even == pytest.approx(40.0)
    assert result.net_return(break_even) == pytest.approx(0.0, abs=1e-12)
    assert result.net_return(bt.HYPERLIQUID_MAKER_BPS) > 0
    assert result.net_return(2 * break_even) < 0


def test_a_losing_pair_reports_no_break_even_rather_than_a_negative_one() -> None:
    """A negative break-even reads as a threshold. There is no cost at which a
    strategy that loses money before costs becomes profitable."""
    result = bt.PairBacktest(
        left="A",
        right="B",
        bars=365,
        years=1.0,
        gross_return=-0.10,
        daily_returns=np.full(365, -0.10 / 365),
        one_way_turns=20.0,
        trades=10,
    )

    assert result.break_even_bps == 0.0


def test_benjamini_hochberg_rejects_far_fewer_than_the_raw_threshold() -> None:
    """The stage's central arithmetic: uniform p-values under a true null give
    about alpha*N raw 'discoveries' and essentially none after correction."""
    # Arrange: 1,000 tests of pure noise.
    rng = np.random.default_rng(3)
    p_values = rng.uniform(0, 1, 1000)
    result = ScreenResult(alpha=0.05)
    result.pairs = [
        PairResult(
            left=f"A{i}",
            right=f"B{i}",
            eg=EngleGranger(f"A{i}", f"B{i}", 500, -1.0, float(p), 1.0, 0.0),
            joh=None,
        )
        for i, p in enumerate(p_values)
    ]
    rejected, q_values, _, _ = multipletests(list(p_values), alpha=0.05, method="fdr_bh")
    result.rejected_bh = [bool(r) for r in rejected]
    result.q_values = [float(q) for q in q_values]

    # Assert
    assert result.expected_false_positives == pytest.approx(50.0)
    assert 30 <= result.raw_hits <= 75, "roughly alpha*N by construction"
    assert result.corrected_hits <= 2, "BH must remove essentially all of them"


def test_embargo_scales_to_a_day_length_holding_period() -> None:
    """Stage C.2 sized the embargo for millisecond horizons. A pairs position
    is held for days — five orders of magnitude larger — so the conversion has
    to survive that jump exactly, not approximately."""
    embargo = validation.embargo_ns_for_holding(bt.MAX_HOLD_BARS)

    assert embargo == 30 * NS_PER_DAY
    assert embargo == 2_592_000_000_000_000
    # Exactly representable: int64 nanoseconds cover about +/-292 years.
    assert embargo < int(np.iinfo(np.int64).max)
    assert validation.embargo_ns_for_holding(0) == 0
    with pytest.raises(ValueError, match="non-negative"):
        validation.embargo_ns_for_holding(-1)


def test_deflated_sharpe_falls_as_more_pairs_are_searched() -> None:
    """Screening more and reporting the best must be penalised, or the number
    rewards the search rather than the strategy."""
    rng = np.random.default_rng(5)
    daily = rng.normal(0.0008, 0.01, 1000)
    result = bt.PairBacktest(
        left="A",
        right="B",
        bars=daily.size,
        years=daily.size / bt.BARS_PER_YEAR,
        gross_return=float(daily.sum()),
        daily_returns=daily,
        one_way_turns=40.0,
        trades=20,
    )

    few = validation.deflate(result, n_trials=2, sharpe_std=0.03)["deflated_sharpe"]
    many = validation.deflate(result, n_trials=2000, sharpe_std=0.03)["deflated_sharpe"]

    assert few > many, "the same result must be worth less after a wider search"
    assert validation.expected_max_sharpe(2000, 0.03) > validation.expected_max_sharpe(20, 0.03)


def test_a_pair_whose_leg_died_is_not_scored_inside_its_selection_window() -> None:
    """Regression: the look-ahead that ranked first in this stage's first run.

    ``start`` was computed by counting back from the end of each pair's own
    series, so a pair whose overlap was shorter than the holdout traded
    entirely inside the formation window it had been selected on. It reported
    223% annualised from four trades on a leg dead since 2022-05.
    """
    # Arrange: 400 bars of overlap, but the holdout begins at bar 730 of the
    # shared calendar — this pair has nothing out of sample at all.
    y, x = _cointegrated(400)
    y_close, x_close = np.exp(y), np.exp(x)
    pair_dates = np.arange(400, dtype=np.int64) * NS_PER_DAY
    holdout_start_ns = 730 * NS_PER_DAY

    # Act: the date-based start lands past the end of the series.
    start = int(np.searchsorted(pair_dates, holdout_start_ns, side="left"))
    scored = bt.run_pair("A", "B", y_close, x_close, start=start)

    # Assert
    assert start == 400
    assert scored is None, "a pair with no out-of-sample bars must not be scored"
    # The old, wrong computation would have scored the whole in-sample series.
    wrong_start = max(0, y_close.size - (1826 - 730))
    assert wrong_start == 0
    assert bt.run_pair("A", "B", y_close, x_close, start=wrong_start) is not None


def test_hedge_ratio_recovers_a_known_slope() -> None:
    x = np.linspace(1.0, 10.0, 200)
    y = 2.5 * x + 3.0

    beta, intercept = hedge_ratio(y, x)

    assert beta == pytest.approx(2.5)
    assert intercept == pytest.approx(3.0)
