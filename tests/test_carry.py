"""Carry: the arithmetic that decides whether the income is real.

Four things here fail silently, and each one flatters the result:

- annualising a funding series by a fixed intervals-per-year constant, when the
  venue changed its own interval 27 days into the sample;
- crediting funding on a notional that grew with price while holding the margin
  that backs it fixed at entry;
- measuring return on notional rather than on the capital two venues actually
  tie up;
- counting a negative-funding run by interval count instead of elapsed time.
"""

from __future__ import annotations

import numpy as np
import pytest

from data.archive.hyperliquid import (
    FundingRow,
    accumulated,
    annualised,
    elapsed_years,
    intervals_ms,
)
from research.carry import funding as fx
from research.carry import risk as rk
from research.carry import trade as tr

HOUR = 3_600_000
EIGHT_HOURS = 8 * HOUR
BASE = 1_683_849_600_000  # 2023-05-12T00:00:00Z


def _rows(rates: list[float], step_ms: int = HOUR, start: int = BASE) -> list[FundingRow]:
    return [
        FundingRow(coin="X", time_ms=start + i * step_ms, rate=r, premium=0.0)
        for i, r in enumerate(rates)
    ]


def test_annualisation_survives_the_venue_changing_its_funding_interval() -> None:
    """Hyperliquid paid eight-hourly until 2023-06-08 and hourly after. A fixed
    intervals-per-year constant is wrong for one era or the other by 8x."""
    # Arrange: eight-hourly rows and hourly rows at the SAME economic rate of
    # 0.01% per 8h, so the honest annualised figure must be identical.
    eight = _rows([0.0001] * 30, step_ms=EIGHT_HOURS)
    hourly = _rows([0.0000125] * 30, step_ms=HOUR, start=eight[-1].time_ms + EIGHT_HOURS)

    # Act
    eight_ann = annualised(eight)
    hourly_ann = annualised(hourly)

    # Assert: both land on the ~10.95%/yr the literature quotes.
    assert eight_ann == pytest.approx(0.1095, rel=0.05)
    assert hourly_ann == pytest.approx(0.1095, rel=0.05)
    assert eight_ann == pytest.approx(hourly_ann, rel=0.05)
    # The naive form disagrees with itself by exactly the interval ratio.
    naive_eight = sum(r.rate for r in eight) / len(eight) * 24 * 365
    assert naive_eight / hourly_ann == pytest.approx(8.0, rel=0.1)


def test_a_publication_gap_is_not_credited_as_funding_time() -> None:
    """A venue outage must not be paid for at whatever rate preceded it."""
    rows = [
        FundingRow(coin="X", time_ms=BASE, rate=0.001, premium=0.0),
        FundingRow(coin="X", time_ms=BASE + 48 * HOUR, rate=0.001, premium=0.0),
        FundingRow(coin="X", time_ms=BASE + 49 * HOUR, rate=0.001, premium=0.0),
    ]

    spans = intervals_ms(rows)

    assert max(spans) == 8 * HOUR, "the 48h hole is clamped, not credited in full"
    assert elapsed_years(rows) < 20 / (24 * 365), "elapsed time excludes the outage"


def test_negative_runs_are_measured_in_elapsed_time_not_interval_count() -> None:
    """Three eight-hourly negative rows is a day underwater, not three hours."""
    rows = _rows([0.001, -0.001, -0.001, -0.001, 0.001], step_ms=EIGHT_HOURS)

    (run,) = fx.negative_runs(rows)

    assert run.hours == pytest.approx(24.0)
    assert run.cost == pytest.approx(-0.003)


def test_a_single_positive_interval_ends_a_negative_run() -> None:
    """Strict on purpose: it makes reported runs a lower bound on time
    underwater, which is the conservative direction for a risk statistic."""
    rows = _rows([-0.001, -0.001, 0.0001, -0.001, -0.001])

    runs = fx.negative_runs(rows)

    assert len(runs) == 2
    assert all(r.hours == pytest.approx(2.0) for r in runs)


def test_return_is_reported_on_deployed_capital_not_notional() -> None:
    """Two venues tie up capital: the spot leg in full, plus perp margin. A
    figure quoted on notional overstates by exactly the capital multiple."""
    n = 24 * 400
    times = np.arange(n, dtype=np.int64) * HOUR + BASE
    price = np.full(n, 100.0)
    rate = np.full(n, 0.00001)

    result = tr.simulate("X", times, price, price, rate, tr.CarryConfig())

    assert result is not None
    assert result.deployed_capital > result.notional, "margin sits on top of the spot leg"
    on_capital = result.annualised_on_capital
    on_notional = result.return_on_notional / result.years
    assert on_capital < on_notional
    assert on_notional / on_capital == pytest.approx(
        result.deployed_capital / result.notional, rel=1e-6
    )


def test_equal_units_stay_delta_flat_so_a_rising_price_forces_no_delta_trade() -> None:
    """A 1:1 unit hedge does not drift out of delta as price moves — both legs
    scale together. Charging rebalancing against price volatility would be
    charging for work the structure does not require."""
    n = 24 * 200
    times = np.arange(n, dtype=np.int64) * HOUR + BASE
    price = np.linspace(100.0, 300.0, n)  # tripling, monotone
    rate = np.zeros(n)

    held = tr.simulate("X", times, price, price, rate, tr.CarryConfig(reset_to_target=False))

    assert held is not None
    assert held.rebalances == 0, "delta never breaks, so nothing is traded"
    assert abs(held.price_pnl) < 1e-6, "the hedge cancels price exactly"


def test_never_resizing_makes_the_margin_requirement_grow_with_price() -> None:
    """The cost of not rebalancing is capital, not slippage: a short whose
    notional triples needs the margin to match or it is liquidated."""
    n = 24 * 200
    times = np.arange(n, dtype=np.int64) * HOUR + BASE
    price = np.linspace(100.0, 300.0, n)
    rate = np.zeros(n)

    held = tr.simulate("X", times, price, price, rate, tr.CarryConfig(reset_to_target=False))
    resized = tr.simulate("X", times, price, price, rate, tr.CarryConfig(reset_to_target=True))

    assert held is not None and resized is not None
    assert held.peak_margin_need > resized.peak_margin_need
    assert held.deployed_capital > resized.deployed_capital
    assert resized.rebalances > 0, "resizing to target is what bounds the capital"
    assert resized.rebalance_cost > 0, "and it costs the 40 bps spot leg to do it"


def test_funding_accrues_on_the_notional_as_it_stands_not_as_it_started() -> None:
    # Arrange: price doubles halfway, so the second half's funding is on 2x.
    n = 2000
    times = np.arange(n, dtype=np.int64) * HOUR + BASE
    price = np.concatenate([np.full(n // 2, 100.0), np.full(n - n // 2, 200.0)])
    rate = np.full(n, 0.00001)

    result = tr.simulate("X", times, price, price, rate, tr.CarryConfig(reset_to_target=False))

    assert result is not None
    flat = 0.00001 * 10_000.0 * (n - 1)
    assert result.funding_collected > flat * 1.4, "the grown notional must be credited"


def test_holding_through_the_worst_run_is_compared_against_the_exit_cost() -> None:
    """The decision an operator faces, priced. A round trip is 83 bps because
    the spot leg is 40 bps a side, so the bar for exiting is high."""
    runs = [fx.NegativeRun(start_ms=BASE, end_ms=BASE + 5 * HOUR, hours=5.0, cost=-0.001)]

    risk = rk.negative_funding_risk(runs, tr.CarryConfig())

    assert risk is not None
    assert risk.exit_reenter_cost == pytest.approx(0.0083)
    assert risk.hold_cost == pytest.approx(0.001)
    assert risk.holding_was_cheaper
    assert risk.summary()["cheaper_action"] == "hold"


def test_liquidation_threshold_tightens_as_leverage_rises() -> None:
    """The design trade-off, made explicit: less margin is less capital and a
    closer liquidation.

    The move has to be a *gap*, not a ramp. A gradual rise is repeatedly caught
    by the rebalance band, which resets the price the short is carried at — so
    rebalancing is itself liquidation protection, and only a jump larger than
    the band can outrun it.
    """
    prices = np.concatenate([np.full(100, 100.0), np.full(100, 118.0)])

    sweep = rk.leverage_sweep(prices, margins=(1.0, 0.5, 0.1))

    assert [row["liquidation_threshold_pct"] for row in sweep] == [50.0, 25.0, 5.0]
    assert [row["capital_per_notional"] for row in sweep] == [2.0, 1.5, 1.1]
    # An 18% gap breaches the 10x book and neither of the others.
    assert sweep[-1]["breaches"] > 0
    assert sweep[0]["breaches"] == 0


def test_rebalancing_protects_against_liquidation_by_resetting_the_reference() -> None:
    """A ramp of the same total size as the gap above does not liquidate,
    because each rebalance re-establishes the short at the current price."""
    ramp = np.linspace(100.0, 118.0, 300)

    caught = rk.liquidation_risk(ramp, tr.CarryConfig(margin_fraction=0.1))
    ungated = rk.liquidation_risk(ramp, tr.CarryConfig(margin_fraction=0.1), rebalance_band=10.0)

    assert caught["breaches"] == 0, "each 2% step resets the carried reference"
    assert ungated["breaches"] > 0, "with rebalancing disabled the same path breaches"


def test_basis_risk_treats_a_widening_premium_as_the_adverse_tail() -> None:
    """A short perp is hurt when the perp gets richer than the index."""
    premium = np.concatenate([np.full(200, 0.0001), [0.004], np.full(200, 0.0001)])

    result = rk.basis_risk(premium, notional=10_000.0)

    assert result["worst_adverse_hourly_move_bps"] == pytest.approx(39.0, abs=0.1)
    assert result["worst_adverse_move_cost_usd"] == pytest.approx(39.0, abs=0.1)
    assert result["worst_favourable_hourly_move_bps"] < 0


def test_unmodellable_risks_are_stated_rather_than_omitted() -> None:
    risks = rk.unmodellable_risks()

    assert len(risks) >= 4
    joined = " ".join(risks).lower()
    for term in ("protocol", "insolvency", "oracle", "operational"):
        assert term in joined


def test_accumulated_funding_is_a_plain_sum_of_charged_rates() -> None:
    rows = _rows([0.001, -0.0005, 0.002])

    assert accumulated(rows) == pytest.approx(0.0025)
