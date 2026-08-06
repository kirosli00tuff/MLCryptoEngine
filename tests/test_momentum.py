"""Tests for the C.16 time-series momentum engine.

The one that matters most is the anti-persistent trap: a panel whose trend
reverses every holding period, so trailing information is systematically wrong.
A simulator with any look-ahead — the signal reading the block it is about to
hold — would profit on that panel; an honest one must lose. Same discipline as
C.10's look-ahead lesson and C.13's ranking trap.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.momentum import engine

DAY_NS = 86_400_000_000_000
N = 12  # comfortably above engine.MIN_NAMES


def panel(paths: list[list[float]]) -> tuple[np.ndarray, np.ndarray]:
    """Column-per-asset close matrix; ragged tails padded with NaN."""
    n_days = max(len(p) for p in paths)
    closes = np.full((n_days, len(paths)), np.nan)
    for j, path in enumerate(paths):
        closes[: len(path), j] = path
    return np.arange(n_days, dtype=np.int64) * DAY_NS, closes


def drift(start: float, step: float, days: int) -> list[float]:
    return [start * (1.0 + step) ** d for d in range(days)]


# --------------------------------------------------------------------------- #
# the signal, and the trap
# --------------------------------------------------------------------------- #


def test_persistent_trends_are_profitable_long_and_short() -> None:
    # Arrange — half the book rises 1%/day forever, half falls 1%/day forever.
    # Momentum is long the risers and short the fallers, so BOTH legs earn.
    dates, closes = panel(
        [drift(100.0, +0.01, 60) for _ in range(N // 2)]
        + [drift(100.0, -0.01, 60) for _ in range(N // 2)]
    )

    # Act
    result = engine.simulate(dates, closes, engine.Spec(5, 5))

    # Assert
    assert result.rebalances > 5
    assert result.gross_pnl > 0.05  # both legs compound in its favour
    assert abs(result.mean_net_exposure) < 1e-9  # half long, half short


def test_the_anti_persistent_panel_loses_on_trailing_information() -> None:
    # Arrange — every asset reverses direction each 5-day block, staggered so
    # the cross-section stays balanced. The trailing 5-day return is therefore
    # ALWAYS the wrong sign for the block about to be held. Look-ahead would
    # turn this panel into the most profitable one in the file.
    paths = []
    for j in range(N):
        price, path = 100.0, []
        for d in range(60):
            block = d // 5
            step = +0.01 if (j + block) % 2 == 0 else -0.01
            price *= 1.0 + step
            path.append(price)
        paths.append(path)
    dates, closes = panel(paths)

    # Act
    result = engine.simulate(dates, closes, engine.Spec(5, 5))

    # Assert — the C.10 trap: an honest simulator must lose here.
    assert result.rebalances > 5
    assert result.gross_pnl < -0.02


# --------------------------------------------------------------------------- #
# deaths, costs, guards
# --------------------------------------------------------------------------- #


def test_a_death_mid_hold_is_a_forced_exit_that_is_charged() -> None:
    # Arrange — one asset trends hard down (so momentum is short it) and then
    # stops printing mid-hold. Dead coins are past losers; dropping this exit
    # would flatter exactly the strategy under test.
    healthy = [drift(100.0, +0.002, 60) for _ in range(N)]
    dying = drift(100.0, -0.05, 33)  # dies on day 33, inside a hold block
    dates, closes = panel([*healthy, dying])

    # Act
    result = engine.simulate(dates, closes, engine.Spec(5, 10))

    # Assert
    assert result.forced_exits >= 1
    assert result.traded_total > 0


def test_fees_scale_linearly_and_traded_notional_is_fee_invariant() -> None:
    # Arrange
    dates, closes = panel(
        [drift(100.0, +0.01, 60) for _ in range(N // 2)]
        + [drift(100.0, -0.01, 60) for _ in range(N // 2)]
    )
    result = engine.simulate(dates, closes, engine.Spec(5, 5))

    # Act
    cheap = result.net_daily(1.5)
    dear = result.net_daily(3.0)

    # Assert — cost is traded x fee, so doubling the fee doubles the drag.
    drag_cheap = float(np.sum(result.gross_daily - cheap))
    drag_dear = float(np.sum(result.gross_daily - dear))
    assert drag_dear == pytest.approx(2.0 * drag_cheap)
    assert drag_cheap == pytest.approx(result.traded_total * 1.5 * 1e-4)


def test_break_even_fee_is_gross_pnl_over_traded_notional() -> None:
    # Arrange
    result = engine.MomentumResult(
        spec=engine.Spec(5, 5),
        days_ns=np.arange(10, dtype=np.int64),
        gross_daily=np.full(10, 0.001),
        traded_daily=np.full(10, 0.1),
    )

    # Act & Assert — 0.01 gross over 1.0 traded, in bps per side.
    assert result.break_even_fee_bps_per_side == pytest.approx(0.01 / 1.0 / 1e-4)


def test_too_few_names_means_no_position_and_a_loud_counter() -> None:
    # Arrange — five assets is a handful of coins, not a cross-section.
    dates, closes = panel([drift(100.0, +0.01, 40) for _ in range(5)])

    # Act
    result = engine.simulate(dates, closes, engine.Spec(5, 5))

    # Assert — degrade loudly, never concentrate silently.
    assert result.thin_rebalances == result.rebalances > 0
    assert result.gross_pnl == pytest.approx(0.0)
    assert result.traded_total == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# the beta control
# --------------------------------------------------------------------------- #


def test_beta_alpha_recovers_a_planted_intercept_and_slope() -> None:
    # Arrange — the strategy IS the benchmark plus 2 bps/day of true alpha.
    rng = np.random.default_rng(9)
    bench = rng.normal(0.001, 0.02, 800)
    strat = bench + 0.0002

    # Act
    found = engine.beta_alpha(strat, bench)

    # Assert
    assert found["beta"] == pytest.approx(1.0, abs=0.02)
    assert found["alpha_annual"] == pytest.approx(0.0002 * 365, rel=0.05)
    assert found["alpha_t"] > 2.0


def test_beta_alpha_reports_zero_alpha_for_pure_beta() -> None:
    # Arrange — a scaled benchmark plus independent noise: all beta, no alpha.
    # This is the "discovered a rising market" case the control exists to name.
    # The noise is load-bearing: an EXACTLY collinear pair has zero residuals,
    # and the t-statistic degenerates into a ratio of float rounding.
    rng = np.random.default_rng(11)
    bench = rng.normal(0.001, 0.02, 800)
    strat = 0.7 * bench + rng.normal(0.0, 0.005, 800)

    # Act
    found = engine.beta_alpha(strat, bench)

    # Assert
    assert found["beta"] == pytest.approx(0.7, abs=0.02)
    assert abs(found["alpha_annual"]) < 0.01
    assert abs(found["alpha_t"]) < 2.0


def test_up_down_split_classifies_by_trailing_trend_sign() -> None:
    # Arrange — benchmark rises 60 days then falls 60. The strategy earns +10
    # bps every day, so the split isolates classification, not performance.
    closes = np.asarray(drift(100.0, +0.01, 60) + drift(100.0, -0.01, 60))
    strat = np.full(120, 0.001)

    # Act
    split = engine.up_down_split(strat, closes)

    # Assert — both regimes present, and returns identical in both since the
    # strategy is constant: any difference would be a classification bug.
    assert split["up_days"] > 20
    assert split["down_days"] > 20
    assert split["up_annual_return_pct"] == pytest.approx(36.5, abs=0.1)
    assert split["down_annual_return_pct"] == pytest.approx(36.5, abs=0.1)


def test_a_frozen_market_empties_the_book_and_pays_for_the_exit() -> None:
    # Arrange — trends establish momentum, then prices freeze forever. Once
    # every trailing window is flat, momentum is exactly zero for every asset:
    # no asset is scoreable, the thin-cross-section guard fires, and the book
    # must be flattened AT COST — not carried, and not exited for free.
    paths = []
    for j in range(N):
        step = +0.01 if j % 2 == 0 else -0.01
        head = drift(100.0, step, 10)
        paths.append(head + [head[-1]] * 50)
    dates, closes = panel(paths)

    # Act
    result = engine.simulate(dates, closes, engine.Spec(5, 5))

    # Assert — entry (~1.0 gross) + drift trades while the trend tail was still
    # moving + one full exit (~1.0) when the signal died; nothing after, so the
    # final unwind is zero and total traded sits just above 2.0.
    assert result.thin_rebalances >= 8
    assert 2.0 < result.traded_total < 2.1
    # After the exit the book is flat: no further P&L of any sign.
    exit_row = int(np.nonzero(result.traded_daily > 0.5)[0][-1])
    assert float(np.abs(result.gross_daily[exit_row + 1 :]).sum()) == pytest.approx(0.0)
