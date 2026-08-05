"""Tests for Stage C.13: cross-sectional funding carry.

The centrepiece is :func:`test_ranking_cannot_see_the_period_it_is_ranked_for`.
C.10's look-ahead defect produced *the highest-ranked result in the study* —
223% annualised from four trades — because a bug that makes results worse gets
investigated while one that makes them better gets published. A cross-sectional
rank strategy has exactly that exposure: rank on funding that includes the
holding period and the backtest prints a spectacular number. So the test builds
a panel where trailing information is systematically *wrong* and asserts the
simulation loses money on it. Look-ahead would make it win.
"""

from __future__ import annotations

import numpy as np
import pytest

from data.archive.hyperliquid import Candle, FundingRow, PerpAsset, parse_universe
from research.cross import dispersion, portfolio, universe
from research.cross.acquire import MS_PER_DAY, CoinHistory

DAY0 = 1_683_849_600_000  # 2023-05-12T00:00:00Z, the venue's launch
HOUR_MS = 3_600_000


def day(n: int) -> int:
    return DAY0 + n * MS_PER_DAY


def make_history(
    coin: str,
    rates_by_day: dict[int, float],
    prices_by_day: dict[int, float] | None = None,
    delisted: bool = False,
    hours_per_day: int = 24,
) -> CoinHistory:
    """A synthetic instrument with each day's funding spread over its hours."""
    funding = [
        FundingRow(coin=coin, time_ms=day(n) + h * HOUR_MS, rate=rate / hours_per_day, premium=0.0)
        for n, rate in sorted(rates_by_day.items())
        for h in range(hours_per_day)
    ]
    prices = prices_by_day if prices_by_day is not None else dict.fromkeys(rates_by_day, 100.0)
    candles = [
        Candle(coin=coin, open_ms=day(n), open=px, high=px, low=px, close=px, volume=1.0)
        for n, px in sorted(prices.items())
    ]
    return CoinHistory(coin=coin, is_delisted_now=delisted, funding=funding, candles=candles)


def build(histories: dict[str, CoinHistory]) -> universe.PerpUniverse:
    assets = [
        PerpAsset(name=coin, sz_decimals=2, max_leverage=5, is_delisted=h.is_delisted_now)
        for coin, h in histories.items()
    ]
    return universe.build(histories, assets)


def _cfg(**kwargs: object) -> portfolio.CrossConfig:
    base: dict[str, object] = {
        "min_cross_section": 2,
        "names_per_side": 1,
        "lookback_days": 3,
        "rebalance_days": 3,
    }
    base.update(kwargs)
    return portfolio.CrossConfig(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# archive layer
# --------------------------------------------------------------------------- #


def test_parse_universe_keeps_delisted_assets_and_defaults_live() -> None:
    # Arrange — the venue writes isDelisted only when it is true.
    payload = {
        "universe": [
            {"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
            {"name": "FTT", "szDecimals": 2, "maxLeverage": 3, "isDelisted": True},
        ]
    }

    # Act
    assets = parse_universe(payload)

    # Assert — a dead instrument must survive parsing, or the very names whose
    # funding went pathological are silently absent from every screen.
    assert [a.name for a in assets] == ["BTC", "FTT"]
    assert assets[0].is_delisted is False
    assert assets[1].is_delisted is True


def test_funding_by_day_sums_intervals_rather_than_averaging_them() -> None:
    # Arrange — 24 hourly rows of 0.001 is 0.024 for the day.
    history = make_history("X", {0: 0.024}, hours_per_day=24)

    # Act
    daily = history.funding_by_day()

    # Assert
    assert daily[day(0)] == pytest.approx(0.024)


def test_funding_by_day_is_interval_agnostic_across_the_venues_8h_to_1h_switch() -> None:
    # Arrange — one day's cost as 3 eight-hourly rows and as 24 hourly rows.
    # Hyperliquid switched interval on 2023-06-08; a per-row constant would
    # report these as differing by a factor of eight.
    eight_hourly = CoinHistory(
        coin="X",
        is_delisted_now=False,
        funding=[
            FundingRow(coin="X", time_ms=day(0) + h * HOUR_MS, rate=0.008, premium=0.0)
            for h in (0, 8, 16)
        ],
    )
    hourly = make_history("X", {0: 0.024}, hours_per_day=24)

    # Act & Assert
    assert eight_hourly.funding_by_day()[day(0)] == pytest.approx(hourly.funding_by_day()[day(0)])


def test_short_history_is_unusable_but_still_counted() -> None:
    # Arrange — 10 days is below the 30-day minimum.
    brief = make_history("NEW", dict.fromkeys(range(10), 0.0))
    long_enough = make_history("OLD", dict.fromkeys(range(60), 0.0))

    # Act & Assert
    assert brief.usable is False
    assert long_enough.usable is True


# --------------------------------------------------------------------------- #
# universe: point-in-time membership
# --------------------------------------------------------------------------- #


def test_membership_is_per_day_so_a_dead_coin_is_present_until_it_dies() -> None:
    # Arrange — DEAD trades for 40 days, ALIVE for all 100.
    histories = {
        "ALIVE": make_history("ALIVE", dict.fromkeys(range(100), 0.0)),
        "DEAD": make_history("DEAD", dict.fromkeys(range(40), 0.0), delisted=True),
    }

    # Act
    built = build(histories)

    # Assert — present early, absent late, never retroactively removed.
    assert built.members[day(10)] == {"ALIVE", "DEAD"}
    assert built.members[day(50)] == {"ALIVE"}
    assert [listing.coin for listing in built.deaths_in_sample()] == ["DEAD"]
    assert built.summary()["died_in_sample"] == 1


def test_a_day_with_funding_but_no_price_is_not_membership() -> None:
    # Arrange — funding for 60 days, price for only the first 40.
    history = make_history(
        "X", dict.fromkeys(range(60), 0.0), prices_by_day=dict.fromkeys(range(40), 100.0)
    )

    # Act
    built = build({"X": history})

    # Assert — an instrument that cannot be priced cannot be traded, however
    # much funding data the venue kept publishing for it.
    assert day(39) in built.members
    assert day(45) not in built.members


def test_panels_never_expose_a_day_outside_membership() -> None:
    # Arrange
    histories = {
        "A": make_history("A", dict.fromkeys(range(60), 0.01)),
        "B": make_history("B", dict.fromkeys(range(40), 0.01)),
    }
    built = build(histories)

    # Act
    funding, price = universe.panels(histories, built)

    # Assert
    assert set(funding["B"]) == set(price["B"])
    assert max(funding["B"]) == day(39)


def test_size_by_month_averages_days_so_a_short_lived_listing_is_not_lost() -> None:
    # Arrange — FLASH lists partway through and is alive only for part of a month.
    histories = {
        "A": make_history("A", dict.fromkeys(range(70), 0.0)),
        "B": make_history("B", dict.fromkeys(range(70), 0.0)),
        "FLASH": make_history("FLASH", dict.fromkeys(range(35, 70), 0.0)),
    }

    # Act
    sizes = build(histories).size_by_month()

    # Assert — a month-end count could read 2 throughout; a mean over days
    # cannot hide a member that existed for part of the month.
    assert max(sizes.values()) == 3


# --------------------------------------------------------------------------- #
# dispersion: the gate
# --------------------------------------------------------------------------- #


def test_thin_cross_sections_are_refused_rather_than_averaged() -> None:
    # Arrange — nine instruments cannot support a decile.
    # Act & Assert
    assert dispersion.measure_day(day(0), np.arange(9, dtype=np.float64)) is None
    assert dispersion.measure_day(day(0), np.arange(10, dtype=np.float64)) is not None


def test_decile_spread_is_top_minus_bottom_and_iqr_matches_percentiles() -> None:
    # Arrange
    values = np.arange(20, dtype=np.float64)

    # Act
    measured = dispersion.measure_day(day(0), values)

    # Assert — a decile of 20 is two names a side: (18+19)/2 - (0+1)/2 = 18.
    assert measured is not None
    assert measured.tail_size == 2
    assert measured.decile_spread == pytest.approx(18.0)
    assert measured.iqr == pytest.approx(
        float(np.percentile(values, 75) - np.percentile(values, 25))
    )


def test_iqr_is_robust_where_stdev_is_not() -> None:
    # Arrange — identical bodies, one with a pathological tail. This is the
    # case the report must distinguish: dispersion retreating into a few
    # extreme names reads as persistence if only stdev is consulted.
    body = np.zeros(20, dtype=np.float64)
    tailed = body.copy()
    tailed[-1] = 500.0

    # Act
    calm = dispersion.measure_day(day(0), body)
    wild = dispersion.measure_day(day(0), tailed)

    # Assert
    assert calm is not None and wild is not None
    assert wild.stdev > calm.stdev
    assert wild.iqr == pytest.approx(calm.iqr)


def test_verdict_anchors_on_the_last_full_year_not_a_partial_one() -> None:
    # Arrange — 800 days, so the final calendar year is a stub.
    days = [
        dispersion.DayDispersion(
            day_ms=DAY0 + i * MS_PER_DAY,
            n=20,
            tail_size=2,
            mean=0.0,
            decile_spread=1.0,
            stdev=1.0,
            iqr=1.0,
            top_decile_mean=0.5,
            bottom_decile_mean=-0.5,
        )
        for i in range(800)
    ]

    # Act
    found = dispersion.verdict(days, days)

    # Assert — the anchor year must have a full year of days behind it.
    assert int(found["by_year"][found["latest_full_year"]]["days"]) >= dispersion.FULL_YEAR_DAYS


# --------------------------------------------------------------------------- #
# portfolio: sign conventions, sizing, look-ahead
# --------------------------------------------------------------------------- #


def test_a_long_collects_when_funding_is_negative_and_a_short_when_positive() -> None:
    # Arrange — PAYER always pays positive funding (its short collects); EARNER
    # is always negative (its long collects). Prices never move, so all P&L is
    # funding.
    histories = {
        "PAYER": make_history("PAYER", dict.fromkeys(range(60), 0.001)),
        "EARNER": make_history("EARNER", dict.fromkeys(range(60), -0.001)),
    }
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # Act
    sim = portfolio.simulate(funding, price, built, _cfg(fee_bps_per_side=0.0))

    # Assert
    assert sim.funding_pnl > 0
    assert sim.price_pnl == pytest.approx(0.0, abs=1e-9)


def test_positions_are_sized_dollar_neutral() -> None:
    # Arrange — constant prices, so the book cannot drift off its target.
    histories = {
        "A": make_history("A", dict.fromkeys(range(60), -0.001)),
        "B": make_history("B", dict.fromkeys(range(60), 0.001)),
    }
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # Act
    sim = portfolio.simulate(funding, price, built, _cfg(fee_bps_per_side=0.0))

    # Assert — gross notional hits its target once a book exists, which can
    # only hold if the two sides carry equal dollars.
    invested = [g for g in sim.gross_notional if g > 0]
    assert invested
    assert all(g == pytest.approx(sim.config.gross_notional) for g in invested)


def test_ranking_cannot_see_the_period_it_is_ranked_for() -> None:
    # Arrange — an anti-persistent panel. Funding flips sign every block, so
    # whatever looked cheapest over the trailing block is about to be the most
    # expensive. Ranking on trailing data is systematically WRONG here.
    block, blocks, n_coins = 3, 20, 6
    histories = {}
    for i in range(n_coins):
        rates = {d: (0.001 if (i + d // block) % 2 == 0 else -0.001) for d in range(block * blocks)}
        histories[f"C{i}"] = make_history(f"C{i}", rates)
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # Act
    sim = portfolio.simulate(
        funding,
        price,
        built,
        _cfg(rebalance_days=block, lookback_days=block, fee_bps_per_side=0.0),
    )

    # Assert — this is the C.10 trap. With look-ahead the ranking would pick
    # the coin about to pay and funding P&L would come out strongly POSITIVE.
    # On trailing information alone it must be negative.
    assert sim.rebalances > 5
    assert sim.funding_pnl < 0


def test_a_delisting_forces_an_exit_and_is_charged_for_it() -> None:
    # Arrange — DEAD earns the most negative funding, so it sits on the long
    # leg, and then stops being priced while the rest of the book lives on.
    histories = {
        f"C{i}": make_history(f"C{i}", dict.fromkeys(range(90), 0.0005 * (i - 2))) for i in range(5)
    }
    histories["DEAD"] = make_history("DEAD", dict.fromkeys(range(45), -0.002), delisted=True)
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # Act
    sim = portfolio.simulate(funding, price, built, _cfg(rebalance_days=7, lookback_days=7))

    # Assert — the exit is counted and paid for, never silently dropped at its
    # entry price.
    assert sim.forced_exits >= 1
    assert sim.cost > 0


def test_a_publication_hole_is_not_treated_as_a_delisting() -> None:
    # Arrange — GAPPY is missing a single interior day but keeps trading after,
    # while the rest of the book is continuous. Reading a missing print as a
    # delisting would liquidate a live position and charge it a fee.
    histories = {
        f"C{i}": make_history(f"C{i}", dict.fromkeys(range(90), 0.0005 * (i - 2))) for i in range(5)
    }
    rates = dict.fromkeys(range(90), -0.002)
    prices = {d: 100.0 for d in range(90) if d != 44}
    histories["GAPPY"] = make_history("GAPPY", rates, prices)
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # GAPPY's most-negative funding keeps it on the long leg across the hole.
    assert day(44) not in price["GAPPY"]
    assert built.listings["GAPPY"].last_day_ms == day(89)

    # Act
    sim = portfolio.simulate(funding, price, built, _cfg(rebalance_days=7, lookback_days=7))

    # Assert — the hole is counted as a hole, and nothing was liquidated for it.
    assert sim.gap_days >= 1
    assert sim.forced_exits == 0


def test_cost_scales_with_the_fee_while_traded_notional_does_not() -> None:
    # Arrange
    histories = {
        "A": make_history("A", dict.fromkeys(range(90), -0.001)),
        "B": make_history("B", dict.fromkeys(range(90), 0.001)),
    }
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # Act
    cheap = portfolio.simulate(funding, price, built, _cfg(fee_bps_per_side=1.0))
    dear = portfolio.simulate(funding, price, built, _cfg(fee_bps_per_side=2.0))

    # Assert
    assert dear.traded_notional == pytest.approx(cheap.traded_notional)
    assert dear.cost == pytest.approx(2.0 * cheap.cost)


def test_break_even_fee_is_the_fee_that_exactly_consumes_gross_profit() -> None:
    # Arrange
    sim = portfolio.Simulation(config=portfolio.CrossConfig())
    sim.funding_pnl = 100.0
    sim.traded_notional = 1_000_000.0

    # Act & Assert — 100 / 1e6 = 1 bp per side.
    assert sim.break_even_fee_bps == pytest.approx(1.0)


def test_beta_recovers_a_book_that_is_simply_long_the_benchmark() -> None:
    # Arrange — a book whose price return IS the benchmark's.
    rng = np.random.default_rng(7)
    days = [day(i) for i in range(200)]
    level, prices = 100.0, {}
    moves = rng.normal(0.0, 0.02, size=200)
    for i, d in enumerate(days):
        level *= 1.0 + (moves[i] if i else 0.0)
        prices[d] = level
    closes = np.asarray([prices[d] for d in days])
    returns = [0.0, *(closes[1:] / closes[:-1] - 1.0).tolist()]

    sim = portfolio.Simulation(config=portfolio.CrossConfig())
    sim.days = days
    sim.price_return = returns
    sim.funding_return = [0.0] * len(days)
    sim.long_return = list(returns)
    sim.short_return = [0.0] * len(days)
    sim.gross_notional = [20_000.0] * len(days)

    # Act
    risk = portfolio.residual_price_risk(sim, prices)

    # Assert — a book that IS the benchmark has beta 1. Reporting beta is only
    # meaningful because a dollar-neutral book is not supposed to.
    assert risk["beta_to_btc"] == pytest.approx(1.0, abs=0.02)
    assert risk["r_squared_vs_btc"] == pytest.approx(1.0, abs=0.02)


def test_price_and_funding_are_reported_as_separate_terms() -> None:
    # Arrange — prices move hard, funding is nil. A combined figure would
    # describe this as carry income, which is the error the stage exists for.
    histories = {}
    for i in range(4):
        drift = 1.0 + (0.01 if i < 2 else -0.01)
        histories[f"C{i}"] = make_history(
            f"C{i}", dict.fromkeys(range(90), 0.0), {d: 100.0 * drift**d for d in range(90)}
        )
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # Act
    sim = portfolio.simulate(funding, price, built, _cfg(fee_bps_per_side=0.0))

    # Assert
    assert sim.funding_pnl == pytest.approx(0.0, abs=1e-6)
    assert abs(sim.price_pnl) > 0.0
    row = sim.summary()
    assert row["funding_income_pct_of_capital_pa"] == pytest.approx(0.0, abs=0.01)
    assert row["price_return_pct_of_capital_pa"] != 0.0


def test_capital_is_the_peak_margin_the_path_demanded() -> None:
    # Arrange — a losing book. Funding must reverse *after* selection to lose,
    # since ranking correctly puts the negative-funding coin on the long leg;
    # so this reuses the anti-persistent panel, where every choice is stale by
    # the time it is held.
    block, n_coins = 3, 6
    histories = {
        f"C{i}": make_history(
            f"C{i}", {d: (0.002 if (i + d // block) % 2 == 0 else -0.002) for d in range(90)}
        )
        for i in range(n_coins)
    }
    built = build(histories)
    funding, price = universe.panels(histories, built)

    # Act
    sim = portfolio.simulate(
        funding, price, built, _cfg(rebalance_days=block, lookback_days=block, fee_bps_per_side=0.0)
    )

    # Assert — accumulated losses raise the capital an operator must actually
    # have held, above the margin the position started with (ADR-035).
    assert sim.funding_pnl < 0
    assert sim.deployed_capital > sim.config.margin_fraction * sim.config.gross_notional
