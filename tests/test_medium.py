"""Tests for the C.17 medium-horizon pipeline.

Two tests carry the stage's honesty and mirror the existing leakage suite at
daily/weekly cadence. The **planted-future canary** feeds the walk-forward a
feature that IS the label plus noise and demands a huge result — a pipeline
that cannot see a deliberate leak proves nothing when it reports a null. The
**lag test** plants a feature spike dated day T with lag L and asserts no
weekly row before T+L can see it — the exact mechanism medium-horizon on-chain
backtests classically get wrong.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pytest

from research.medium import data as med_data
from research.medium import features as feat
from research.medium import study

MS_PER_DAY = 86_400_000
SUNDAY0 = 1_596_326_400_000  # 2020-08-02


def _weeks(n: int) -> list[int]:
    return [SUNDAY0 + i * 7 * MS_PER_DAY for i in range(n)]


# --------------------------------------------------------------------------- #
# the lag discipline
# --------------------------------------------------------------------------- #


def test_a_feature_dated_t_is_invisible_before_t_plus_lag() -> None:
    # Arrange — one observation dated day T, lag 75 days (the measured CM lag).
    t = SUNDAY0 + 100 * MS_PER_DAY
    series = feat.Series.from_map({t: 42.0})

    # Act & Assert — invisible the day before availability, visible on it.
    assert np.isnan(series.latest_usable(t + 74 * MS_PER_DAY, 75))
    assert series.latest_usable(t + 75 * MS_PER_DAY, 75) == 42.0
    # And with lag 0 it is visible on its own date, never before it.
    assert np.isnan(series.latest_usable(t - 1, 0))
    assert series.latest_usable(t, 0) == 42.0


def test_features_are_prefix_invariant_at_daily_cadence() -> None:
    # Arrange — the same supply series, full and truncated at day 60.
    rng = np.random.default_rng(3)
    days = [SUNDAY0 + i * MS_PER_DAY for i in range(120)]
    supply = {}
    level = 1e11
    for day in days:
        level *= 1.0 + rng.normal(0.0002, 0.002)
        supply[day] = level
    cutoff = days[60]

    # Act
    full = feat.stablecoin_class(supply)
    truncated = feat.stablecoin_class({d: v for d, v in supply.items() if d <= cutoff})

    # Assert — history that existed at the cutoff reads identically whether or
    # not the future has been appended since.
    for name in full.names():
        for day, value in truncated.features[name].items():
            assert full.features[name][day] == pytest.approx(value), (name, day)


def test_train_indices_enforce_purge_plus_embargo() -> None:
    # Arrange / Act — decision at t=20, horizon 4: the label of week s spans
    # s..s+4, purge needs s+4<=20, embargo adds four more => s<=12.
    admissible = study.train_indices(100, 20, 4)

    # Assert
    assert max(admissible) == 12
    assert 13 not in admissible
    assert study.train_indices(100, 7, 4) == []  # nothing resolved+embargoed yet


# --------------------------------------------------------------------------- #
# the canary, and its control
# --------------------------------------------------------------------------- #


def _cell(x_by_asset: dict[str, np.ndarray], returns: dict[str, np.ndarray]) -> study.CellInput:
    n = next(iter(x_by_asset.values())).shape[0]
    weekly = {a: np.cumprod(1.0 + returns[a]) * 100.0 for a in returns}
    label = {
        a: np.asarray(
            [weekly[a][i + 1] / weekly[a][i] - 1.0 if i + 1 < n else np.nan for i in range(n)]
        )
        for a in returns
    }
    return study.CellInput(
        weeks_ms=np.asarray(_weeks(n), dtype=np.int64),
        x_by_asset=x_by_asset,
        label_by_asset=label,
        next_week_return=label,
        btc_weekly_return=label["BTC"],
        btc_trend_up=np.ones(n, dtype=bool),
    )


def test_planted_future_canary_explodes_and_noise_control_does_not() -> None:
    # Arrange — 300 weeks of iid returns. Canary feature = next week's return
    # plus small noise; control feature = pure noise.
    rng = np.random.default_rng(7)
    n = 300
    returns = {a: rng.normal(0.0, 0.03, n) for a in ("BTC", "ETH")}
    canary_x = {}
    noise_x = {}
    for a in returns:
        future = np.roll(returns[a], -1)
        canary_x[a] = np.column_stack([future + rng.normal(0.0, 0.003, n)])
        noise_x[a] = np.column_stack([rng.normal(0.0, 1.0, n)])

    # Act
    canary = study.simulate_cell(_cell(canary_x, returns), 1, "long_short")
    control = study.simulate_cell(_cell(noise_x, returns), 1, "long_short")

    # Assert — the pipeline must be ABLE to see a leak, and must not hallucinate
    # one from noise. Together these make a null result elsewhere meaningful.
    assert canary is not None and control is not None
    assert study.sharpe_weekly(canary["gross"]) > 3.0
    assert abs(study.sharpe_weekly(control["gross"])) < 1.5


def test_ridge_recovers_a_planted_linear_signal() -> None:
    # Arrange
    rng = np.random.default_rng(11)
    x = rng.normal(0.0, 1.0, (500, 3))
    y = 0.05 * x[:, 0] + rng.normal(0.0, 0.01, 500)

    # Act
    beta, _, _ = study.ridge_fit(x, y)

    # Assert — the planted coefficient dominates and carries the right sign.
    assert beta[0] > 5 * abs(beta[1])
    assert beta[0] > 5 * abs(beta[2])


# --------------------------------------------------------------------------- #
# portfolio mechanics
# --------------------------------------------------------------------------- #


def test_long_only_clips_to_cash_and_never_goes_net_short() -> None:
    # Arrange — a near-perfect predictor, so the model's SIGN is meaningful:
    # roughly half the predictions are negative, and long-only must express
    # those as cash rather than shorts. (An anti-correlated feature would NOT
    # do this — ridge just flips the coefficient, which was this test's
    # original design bug.)
    rng = np.random.default_rng(5)
    n = 200
    returns = {a: rng.normal(0.0, 0.03, n) for a in ("BTC", "ETH")}
    x = {a: np.column_stack([np.roll(returns[a], -1) + rng.normal(0, 0.003, n)]) for a in returns}

    # Act
    lo = study.simulate_cell(_cell(x, returns), 1, "long_only")

    # Assert — never net short, capped at fully long, and the negative
    # predictions show up as genuine cash weeks.
    assert lo is not None
    assert float(np.min(lo["net_exposure"])) >= 0.0
    assert float(np.max(lo["net_exposure"])) <= 1.0
    assert bool(np.any(lo["net_exposure"] == 0.0))
    assert bool(np.any(lo["net_exposure"] == 1.0))


def test_costs_scale_with_fee_and_traded_notional() -> None:
    # Arrange — any live cell.
    rng = np.random.default_rng(13)
    n = 200
    returns = {a: rng.normal(0.0, 0.03, n) for a in ("BTC", "ETH")}
    x = {a: np.column_stack([rng.normal(0.0, 1.0, n)]) for a in returns}
    path = study.simulate_cell(_cell(x, returns), 1, "long_short")
    assert path is not None

    # Act
    drag25 = float(np.sum(path["traded"] * 25.0 * study.BPS))
    drag40 = float(np.sum(path["traded"] * 40.0 * study.BPS))

    # Assert
    assert drag40 == pytest.approx(drag25 * 40.0 / 25.0)
    assert drag25 > 0.0


# --------------------------------------------------------------------------- #
# parsers and the weekly grid
# --------------------------------------------------------------------------- #


def test_coinmetrics_parser_reads_dates_and_skips_blanks(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "btc.csv"
    path.write_text("time,MetricA,MetricB\n2021-01-01,1.5,\n2021-01-02,2.5,7.0\nbad,,\n")

    # Act
    out = med_data.load_coinmetrics(path)

    # Assert — blanks absent (never zero), bad dates dropped, UTC-midnight keys.
    day1 = 1_609_459_200_000
    assert out["MetricA"][day1] == 1.5
    assert day1 not in out["MetricB"]
    assert out["MetricB"][day1 + MS_PER_DAY] == 7.0


def test_defillama_parser_reads_epoch_seconds_and_pegged_usd(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "all.json"
    path.write_text(
        '[{"date":"1609459200","totalCirculatingUSD":{"peggedUSD":27.5e9}},'
        '{"date":"1609545600","totalCirculatingUSD":{}}]'
    )

    # Act
    out = med_data.load_defillama(path)

    # Assert
    assert out[1_609_459_200_000] == pytest.approx(27.5e9)
    assert len(out) == 1  # the row without peggedUSD is absent, not zero


def test_weekly_grid_returns_sundays_only() -> None:
    # Act
    weeks = feat.weekly_grid(SUNDAY0, SUNDAY0 + 30 * MS_PER_DAY)

    # Assert — 2020-08-02 was a Sunday; every entry is 7 days apart.
    assert weeks[0] == SUNDAY0
    assert all(b - a == 7 * MS_PER_DAY for a, b in itertools.pairwise(weeks))
