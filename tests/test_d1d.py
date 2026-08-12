"""D.1d bounded replay: latency, ALO, always-last fills, ledger identity."""

from __future__ import annotations

import pytest

from research.microstructure.d1d import performance_report, zero_crossing_ms
from research.microstructure.fill_replay import BoundedQuoteSim
from research.microstructure.inventory import InventorySim

NS = 1_000_000_000
L = NS // 10  # 100 ms


def _sim(model: str = "always_last", cap: float | None = None, lat: int = L) -> BoundedQuoteSim:
    return BoundedQuoteSim(
        symbol="X",
        quote_size=5.0,
        cap_size=cap,
        latency_ns=lat,
        sz_decimals=2,
        fill_model=model,  # type: ignore[arg-type]
    )


class TestAlwaysLastFills:
    def test_placement_activates_after_latency_then_sweep_fills(self) -> None:
        sim = _sim()
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        assert sim.placements == 2
        sim.on_trade(NS // 20, +1, 1.0001, 20.0)  # before active_ns: no fill
        assert sim.fills == 0
        sim.on_trade(NS // 5, +1, 1.0001, 20.0)  # live, sz >= visible: sweep
        assert sim.fills == 1 and sim.fills_sweep == 1
        assert sim.position == pytest.approx(-5.0)
        assert sim.edge_usd == pytest.approx((1.0001 - 1.0) * 5.0)

    def test_sub_sweep_print_does_not_fill_the_last_in_queue(self) -> None:
        sim = _sim()
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        sim.on_trade(NS // 5, +1, 1.0001, 3.0)  # sz < visible touch
        assert sim.fills == 0

    def test_print_through_price_fills_the_remainder(self) -> None:
        sim = _sim()
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        sim.on_trade(NS // 5, +1, 1.0005, 1.0)  # strictly through our ask
        assert sim.fills == 1 and sim.fills_through == 1
        assert sim.position == pytest.approx(-5.0)


class TestLatencyAndAlo:
    def test_alo_rejects_an_arrival_that_would_cross(self) -> None:
        sim = _sim()
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)  # ask placed, active at 0.1 s
        # By arrival the market moved past our ask price: venue rejects ALO.
        sim.on_bbo(NS // 5, 1.0002, 10.0, 1.0004, 10.0)
        assert sim.alo_rejections == 1
        assert sim._orders["ask"] is None  # not repriced, not re-placed this update

    def test_stale_price_fill_while_cancel_is_in_flight_costs_money(self) -> None:
        sim = _sim()
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        # Touch moves away: cancel starts (dead at 0.2 s + L = 0.3 s).
        sim.on_bbo(NS // 5, 1.0000, 10.0, 1.0003, 10.0)
        assert sim.cancels_started >= 1
        # Before the cancel lands the bid crosses our stale ask: we are filled
        # at 1.0001 with the mid already at 1.0003 — the latency loss, booked.
        sim.on_bbo(NS // 4, 1.0002, 10.0, 1.0004, 10.0)
        assert sim.fills_crossing == 1
        assert sim.edge_usd < 0.0

    def test_cancel_completes_then_requotes_at_the_new_touch(self) -> None:
        sim = _sim()
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        sim.on_bbo(NS // 5, 1.0000, 10.0, 1.0003, 10.0)  # cancel starts
        sim.on_bbo(NS, 1.0000, 10.0, 1.0003, 10.0)  # cancel dead, re-placed
        order = sim._orders["ask"]
        assert sim.fills == 0 and order is not None
        assert order.price == pytest.approx(1.0003)


class TestImprovedAndCap:
    def test_improved_quotes_inside_and_fills_on_any_print(self) -> None:
        sim = _sim(model="improved", lat=0)
        sim.on_bbo(0, 0.9995, 10.0, 1.0005, 10.0)  # 10-tick book, tick 1e-4
        order = sim._orders["ask"]
        assert order is not None and order.price == pytest.approx(1.0004)
        sim.on_trade(NS, +1, 1.0004, 1.0)  # any size reaches the improved quote
        assert sim.fills == 1
        assert sim.position == pytest.approx(-1.0)

    def test_cap_clips_fills_and_withdraws_the_extending_side(self) -> None:
        sim = _sim(cap=5.0, lat=0)
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        sim.on_trade(NS, -1, 0.9999, 20.0)  # sell sweep: we buy, clipped to 5
        assert sim.position == pytest.approx(5.0)
        sim.on_bbo(2 * NS, 0.9999, 10.0, 1.0001, 10.0)
        assert sim._orders["bid"] is None  # at cap: extending side withdrawn
        assert sim._orders["ask"] is not None


class TestLedger:
    def test_identity_and_hourly_sum(self) -> None:
        sim = _sim(lat=0)
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        sim.on_trade(NS, +1, 1.0001, 20.0)  # sweep fill, short 5
        sim.on_bbo(2 * NS, 1.0001, 10.0, 1.0003, 10.0)  # mid drifts against us
        sim.on_funding(3 * NS, 1e-4, 1.0002)
        assert sim.mark_to_market_usd() == pytest.approx(sim.edge_usd + sim.inventory_usd)
        assert sum(sim.net_by_hour.values()) == pytest.approx(sim.total_net_usd())
        assert sum(sim.fees_by_hour.values()) == pytest.approx(sim.fees_usd)

    def test_generous_mode_reproduces_inventory_sim(self) -> None:
        # The Task 2 known-answer gate in miniature: identical events through
        # D.1c's InventorySim and this engine in generous mode must agree.
        bounded = _sim(model="generous", cap=12.0, lat=0)
        legacy = InventorySim(symbol="X", quote_size=5.0, cap_size=12.0)
        events: list[tuple[str, tuple[float, ...]]] = [
            ("bbo", (0.9999, 10.0, 1.0001, 10.0)),
            ("trade", (+1, 1.0001, 2.0)),
            ("bbo", (1.0000, 8.0, 1.0002, 6.0)),
            ("trade", (-1, 1.0000, 9.0)),
            ("trade", (-1, 1.0000, 30.0)),
            ("bbo", (0.9997, 8.0, 0.9999, 6.0)),
            ("funding", (1e-4, 1.0)),
            ("trade", (+1, 0.9999, 4.0)),
            ("bbo", (1.0001, 8.0, 1.0003, 6.0)),
        ]
        for i, (kind, args) in enumerate(events):
            ts = (i + 1) * NS
            if kind == "bbo":
                bounded.on_bbo(ts, *args)
                legacy.on_quote(ts, args[0], args[2])
            elif kind == "trade":
                bounded.on_trade(ts, int(args[0]), args[1], args[2])
                legacy.on_trade(ts, int(args[0]), args[2])
            else:
                bounded.on_funding(ts, args[0], args[1])
                legacy.on_funding(ts, args[0], args[1])
        for attr in (
            "position",
            "edge_usd",
            "inventory_usd",
            "funding_usd",
            "fees_usd",
            "filled_notional_usd",
        ):
            assert getattr(bounded, attr) == pytest.approx(getattr(legacy, attr)), attr
        assert bounded.fills == legacy.fills


class TestReporting:
    def test_zero_crossing_interpolates_between_grid_points(self) -> None:
        assert zero_crossing_ms([(0.0, 2.0), (100.0, 1.0), (200.0, -1.0)]) == pytest.approx(150.0)
        assert zero_crossing_ms([(0.0, 2.0), (100.0, 1.0)]) is None

    def test_performance_report_is_schema_valid_backtest(self) -> None:
        sim = _sim(lat=0)
        sim.on_bbo(0, 0.9999, 10.0, 1.0001, 10.0)
        sim.on_trade(NS, +1, 1.0001, 20.0)
        sim.on_bbo(2 * NS, 0.9999, 10.0, 1.0001, 10.0)
        report = performance_report(sim, run_id="test-run")
        assert report.mode.value == "backtest"
        assert len(report.trades) == sim.fills
        assert all(point.drawdown_pct <= 0 for point in report.drawdown)
        assert report.model_dump_json()  # serialises cleanly against the contract
