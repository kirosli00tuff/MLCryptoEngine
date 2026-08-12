"""D.1c units: tick geometry, longer-horizon nets, and the inventory identity."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

from research.microstructure.d1c import load_funding_archive
from research.microstructure.horizons import HorizonNet
from research.microstructure.inventory import InventorySim
from research.microstructure.tick import SpreadTicks, tick_bps, tick_size

NS = 1_000_000_000


class TestTickSize:
    def test_five_sig_figs_bind_at_btc_prices(self) -> None:
        # 62,362 has 5 digits: the increment is 1.0 regardless of szDecimals room.
        assert tick_size(62_362.0, 5) == pytest.approx(1.0)

    def test_integer_prices_always_allowed_above_five_digits(self) -> None:
        # 112,345 would need 6 significant figures at a tick of 1; integers are
        # always allowed, so the increment stays 1, never 10.
        assert tick_size(112_345.0, 5) == pytest.approx(1.0)

    def test_decimal_cap_binds_at_sub_cent_prices(self) -> None:
        # PUMP-like: 0.0035 with szDecimals 0 → 6 decimals max → 1e-6, which
        # exceeds the 5-sig-fig increment of 1e-7.
        assert tick_size(0.0035, 0) == pytest.approx(1e-6)

    def test_sig_figs_bind_when_decimals_have_room(self) -> None:
        # 0.35 with szDecimals 0: 5 sig figs give 1e-5; decimals would allow 1e-6.
        assert tick_size(0.35, 0) == pytest.approx(1e-5)

    def test_tick_in_bps_scales_inversely_with_price(self) -> None:
        # At 0.0035 a 1e-6 tick is ~2.86 bps of price.
        assert tick_bps(0.0035, 0) == pytest.approx(2.857, rel=1e-3)

    def test_nonpositive_price_raises(self) -> None:
        with pytest.raises(ValueError):
            tick_size(0.0, 0)


class TestSpreadTicks:
    def test_time_weighted_median_and_fractions(self) -> None:
        # Arrange: 10 s at 1 tick, then 20 s at 3 ticks, price ~1.0 (tick 1e-4).
        acc = SpreadTicks(symbol="X", sz_decimals=2)
        acc.observe(0, 0.99995, 1.00005)
        acc.observe(10 * NS, 0.99985, 1.00015)
        acc.close(30 * NS)
        # Assert
        assert acc.median_ticks() == 3
        assert acc.fraction_at_most(2) == pytest.approx(10 / 30)
        assert acc.fraction_at_most(3) == pytest.approx(1.0)

    def test_sub_tick_positive_spread_counts_as_one_tick(self) -> None:
        # A positive spread narrower than one tick (decade-straddling quote)
        # must clamp to 1, not round to 0.
        acc = SpreadTicks(symbol="X", sz_decimals=2)
        acc.observe(0, 1.00000, 1.00003)
        acc.observe(NS, 1.00000, 1.00003)
        assert acc.weight_ns == {1: NS}

    def test_locked_quote_counted_not_distributed(self) -> None:
        acc = SpreadTicks(symbol="X", sz_decimals=2)
        acc.observe(0, 1.0, 1.0)
        acc.observe(NS, 0.9999, 1.0001)
        acc.close(2 * NS)
        assert acc.crossed_or_locked == 1
        # Only the second quote's second credited; the locked state carries no weight.
        assert acc.total_ns == NS


class TestHorizonNet:
    def test_deadline_at_quote_resolves_against_that_quote(self) -> None:
        # Arrange: spread 20 bps at mid 100, one buy aggressor, exit mid 101
        # exactly at the 60 s deadline.
        net = HorizonNet(symbol="X", half_split_ns=10**18, horizons_ms=(60_000,))
        net.on_quote(0, 99.9, 100.1)
        net.on_trade(NS, +1)
        net.on_quote(NS + 60_000 * 1_000_000, 100.9, 101.1)
        # Act
        w = net.net[60_000]
        # Assert: adverse = +100 bps, net = 20 - 100 - 3 = -83.
        assert w.n == 1
        assert w.mean == pytest.approx(20.0 - 100.0 - 3.0, abs=0.05)

    def test_deadline_strictly_before_quote_resolves_at_previous_mid(self) -> None:
        net = HorizonNet(symbol="X", half_split_ns=10**18, horizons_ms=(60_000,))
        net.on_quote(0, 99.9, 100.1)
        net.on_trade(NS, +1)
        # The next quote arrives after the deadline: exit is the previous mid
        # (100.0), so adverse is 0 and net = spread - 3.
        net.on_quote(NS + 120_000 * 1_000_000, 100.9, 101.1)
        assert net.net[60_000].mean == pytest.approx(20.0 - 0.0 - 3.0, abs=0.05)

    def test_welford_matches_statistics_variance(self) -> None:
        # Arrange: three trades resolving at distinct exits.
        net = HorizonNet(symbol="X", half_split_ns=10**18, horizons_ms=(1_000,))
        nets = []
        t = 0
        for exit_mid in (100.5, 99.5, 100.25):
            net.on_quote(t, 99.9, 100.1)
            net.on_trade(t + NS, +1)
            net.on_quote(t + 2 * NS, exit_mid - 0.1, exit_mid + 0.1)
            adverse = (exit_mid - 100.0) / 100.0 * 1e4
            nets.append(20.0 - adverse - 3.0)
            t += 10 * NS
        w = net.net[1_000]
        assert w.n == 3
        assert w.mean == pytest.approx(statistics.mean(nets), abs=0.05)
        variance = w.variance()
        assert variance is not None
        assert variance == pytest.approx(statistics.variance(nets), rel=0.01)

    def test_halves_split_on_trade_time(self) -> None:
        split = 5 * NS
        net = HorizonNet(symbol="X", half_split_ns=split, horizons_ms=(1_000,))
        net.on_quote(0, 99.9, 100.1)
        net.on_trade(NS, +1)  # first half
        net.on_quote(8 * NS, 99.9, 100.1)  # resolves first, arms second
        net.on_trade(9 * NS, +1)  # second half
        net.on_quote(20 * NS, 99.9, 100.1)
        assert net.half_counts[1_000] == [1, 1]


class TestInventorySim:
    def test_buy_aggressor_fills_the_ask_and_earns_half_spread(self) -> None:
        sim = InventorySim(symbol="X", quote_size=5.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, +1, 2.0)
        assert sim.position == pytest.approx(-2.0)
        assert sim.edge_usd == pytest.approx((101.0 - 100.0) * 2.0)
        assert sim.fees_usd == pytest.approx(202.0 * 1.5e-4)

    def test_fill_capped_at_quote_size(self) -> None:
        sim = InventorySim(symbol="X", quote_size=5.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, -1, 10.0)
        assert sim.position == pytest.approx(5.0)

    def test_mark_to_market_identity_edge_plus_inventory(self) -> None:
        # Arrange: sell 2 at 101, then the mid rallies to 102 against the short.
        sim = InventorySim(symbol="X", quote_size=5.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, +1, 2.0)
        sim.on_quote(2 * NS, 101.0, 103.0)
        # Assert: inventory = -2 x 2 = -4, and the decomposition equals MtM.
        assert sim.inventory_usd == pytest.approx(-4.0)
        assert sim.mark_to_market_usd() == pytest.approx(sim.edge_usd + sim.inventory_usd)

    def test_funding_sign_short_receives_when_rate_positive(self) -> None:
        sim = InventorySim(symbol="X", quote_size=5.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, +1, 2.0)  # short 2
        sim.on_funding(2 * NS, 1e-4, 102.0)
        assert sim.funding_usd == pytest.approx(2.0 * 102.0 * 1e-4)

    def test_cap_refuses_extension_and_records_forgone_edge(self) -> None:
        sim = InventorySim(symbol="X", quote_size=5.0, cap_size=3.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, +1, 5.0)  # sells capped at 3
        assert sim.position == pytest.approx(-3.0)
        assert sim.forgone_fills == 1
        assert sim.forgone_edge_usd == pytest.approx(1.0 * 2.0)  # $1 edge x 2 refused
        # A second sell attempt is fully refused ...
        sim.on_trade(2 * NS, +1, 1.0)
        assert sim.position == pytest.approx(-3.0)
        # ... but the bid side still fills and reduces the position.
        sim.on_trade(3 * NS, -1, 4.0)
        assert sim.position == pytest.approx(1.0)

    def test_time_away_from_flat_uses_min_notional_threshold(self) -> None:
        sim = InventorySim(symbol="X", quote_size=5.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, +1, 2.0)  # |pos x mid| = $200 >= $10
        sim.on_quote(11 * NS, 99.0, 101.0)
        assert sim.nonflat_ns == 10 * NS
        assert sim.total_ns == 11 * NS

    def test_hourly_ledger_sums_to_total_net(self) -> None:
        sim = InventorySim(symbol="X", quote_size=5.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, +1, 2.0)
        sim.on_quote(2 * NS, 101.0, 103.0)
        sim.on_funding(3 * NS, 1e-4, 102.0)
        assert sum(sim.net_by_hour.values()) == pytest.approx(sim.total_net_usd())

    def test_drawdown_tracks_peak_to_trough(self) -> None:
        sim = InventorySim(symbol="X", quote_size=5.0)
        sim.on_quote(0, 99.0, 101.0)
        sim.on_trade(NS, +1, 2.0)  # edge +2 (peak ~ +2 - fees)
        sim.on_quote(2 * NS, 101.0, 103.0)  # inventory -4
        assert sim.max_drawdown_usd == pytest.approx(4.0)


class TestFundingArchive:
    def test_rows_map_to_hour_boundaries(self, tmp_path: Path) -> None:
        coin_dir = tmp_path / "coin=PUMP"
        coin_dir.mkdir()
        rows = [
            {"coin": "PUMP", "fundingRate": "0.0000125", "time": 3_600_000 * 5 + 11},
            {"coin": "PUMP", "fundingRate": "-0.0000200", "time": 3_600_000 * 6 + 47},
        ]
        (coin_dir / "start=0.json").write_text(json.dumps(rows))
        rates = load_funding_archive(tmp_path, "PUMP")
        assert rates == {
            3_600_000 * 5: pytest.approx(1.25e-5),
            3_600_000 * 6: pytest.approx(-2.0e-5),
        }

    def test_missing_coin_yields_empty(self, tmp_path: Path) -> None:
        assert load_funding_archive(tmp_path, "MERL") == {}
