"""Per-contract futures costs: a fixed fee is not a fixed rate.

The error this guards against is reusing one contract's basis-point figure
for another. MES and MBT carry similar dollar costs and wildly different
notionals, so the same round turn is cheap on one and expensive on the other.
Stage C.8 began from the premise that CME costs "under one basis point round
trip" — true of MES, false of MBT by roughly 5x.
"""

from __future__ import annotations

import pytest

from data.config import FeeTier, InstrumentMeta, VenueConfig, load_config
from research.labels.costs import CostModel, cost_model_from_config

BTC_PRICE = 65_172.50
MBT_MULTIPLIER = 0.1
MES_MULTIPLIER = 5.0


def _model(mode: str, usd_per_side: float, multiplier: float) -> CostModel:
    return CostModel(
        venue="cme",
        mode=mode,  # type: ignore[arg-type]
        fee_usd_per_contract_per_side=usd_per_side,
        contract_multiplier=multiplier,
    )


def test_same_dollar_fee_costs_far_more_on_the_smaller_contract() -> None:
    # Arrange: one dollar cost, two contracts, at their real notionals.
    mbt = _model("maker", 1.495, MBT_MULTIPLIER)  # $2.99 round turn
    mes = _model("maker", 1.495, MES_MULTIPLIER)

    # Act
    mbt_bps = mbt.round_trip_cost_bps(None, BTC_PRICE)
    mes_bps = mes.round_trip_cost_bps(None, 6_800.0)  # S&P ~6800 -> $34k notional

    # Assert
    assert mes_bps == pytest.approx(0.879, abs=0.01), "MES: under one bp, as assumed"
    assert mbt_bps == pytest.approx(4.588, abs=0.01), "MBT: nowhere near one bp"
    assert mbt_bps / mes_bps == pytest.approx(5.2, abs=0.2), (
        "the ratio is the notional ratio — reusing MES's bps for MBT understates by 5x"
    )


def test_cost_in_bps_falls_as_price_rises() -> None:
    # Arrange: a fixed per-contract fee is a shrinking rate on a rising price.
    model = _model("maker", 2.02, MBT_MULTIPLIER)

    # Act
    cheap = model.round_trip_cost_bps(None, 100_000.0)
    dear = model.round_trip_cost_bps(None, 30_000.0)

    # Assert
    assert dear > cheap, "the same fee is a bigger rate on a smaller notional"
    assert cheap == pytest.approx(2.02 * 2 / (100_000.0 * MBT_MULTIPLIER) * 1e4, rel=1e-9)


def test_per_contract_model_refuses_to_price_without_a_price() -> None:
    # Arrange
    model = _model("maker", 2.02, MBT_MULTIPLIER)

    # Act / Assert: no notional means no rate; guessing one invents a fee.
    with pytest.raises(ValueError, match="depends on the notional"):
        model.round_trip_cost_bps(2.0, None)


def test_per_contract_fee_without_a_multiplier_is_rejected_at_construction() -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="contract_multiplier"):
        CostModel(venue="cme", mode="maker", fee_usd_per_contract_per_side=2.02)


def test_taker_adds_the_spread_and_maker_does_not() -> None:
    # Arrange: CME does not split maker/taker fees, so the spread is the
    # entire difference between the two modes.
    maker = _model("maker", 2.02, MBT_MULTIPLIER)
    taker = _model("taker", 2.02, MBT_MULTIPLIER)

    # Act
    spread_bps = 2.3
    difference = taker.round_trip_cost_bps(spread_bps, BTC_PRICE) - maker.round_trip_cost_bps(
        spread_bps, BTC_PRICE
    )

    # Assert
    assert difference == pytest.approx(spread_bps)


def test_percentage_venues_are_unaffected_by_price() -> None:
    # Arrange: crypto spot charges a share of notional, so price is irrelevant.
    model = CostModel(venue="kraken", mode="maker", fee_bps_per_leg=40.0)

    # Act / Assert
    assert model.round_trip_cost_bps(None) == 80.0
    assert model.round_trip_cost_bps(None, 65_000.0) == 80.0
    assert not model.is_per_contract


def test_config_without_a_declared_multiplier_refuses_rather_than_defaulting() -> None:
    # Arrange: a per-contract fee whose instrument has no multiplier.
    vcfg = VenueConfig(
        name="x",
        ws_url="wss://x",
        rest_status_url="https://x",
        symbols=["MBT"],
        book_depth=10,
        snapshot={"on_subscribe": False, "checksum": False, "notes": "t"},  # type: ignore[arg-type]
        aws_region="us-east-2",
        fee_tiers=[
            FeeTier(volume_usd_30d=0, maker_bps=0, taker_bps=0, fee_usd_per_contract_per_side=2.02)
        ],
        instruments={"MBT": InstrumentMeta(price_decimals=0, qty_decimals=0)},
    )

    # Act / Assert
    with pytest.raises(ValueError, match="no contract_multiplier"):
        cost_model_from_config("cme", vcfg, "maker", symbol="MBT")


def test_shipped_cme_config_prices_mbt_per_contract() -> None:
    # Arrange: the real config, so a regression in venues.yaml fails here.
    cfg = load_config()

    # Act
    model = cost_model_from_config("cme", cfg.venues["cme"], "maker", symbol="MBT")

    # Assert
    assert model.is_per_contract, "MBT must not be priced as a share of notional"
    assert model.contract_multiplier == pytest.approx(MBT_MULTIPLIER), "MBT is 0.1 BTC"
    round_trip = model.round_trip_cost_bps(None, BTC_PRICE)
    assert 4.0 < round_trip < 9.0, (
        f"MBT resting round trip is {round_trip:.2f} bps at a {BTC_PRICE:,.0f} price — "
        "if this ever drops below 1 bp the premise that CME is nearly free has "
        "silently returned"
    )
