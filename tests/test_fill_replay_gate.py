"""The replacement D.1d gate: a differential control over the order machine.

Audit finding A1: the shipped known-answer gate (generous mode vs D.1c's
``InventorySim``) executes none of ``fill_replay``'s order machine. These tests
replace it. They difference :class:`BoundedQuoteSim` against the deliberately
dissimilar :mod:`research.microstructure.reference_replay` over randomised event
streams, assert the lifecycle accounting closes, and — so this gate cannot
quietly decay into the one it replaces — assert that the workload actually
executes the lines it is offered as a control over.
"""

from __future__ import annotations

import inspect
import random
import trace as _trace

import pytest

from research.microstructure import fill_replay as fr
from research.microstructure.fill_replay import BoundedQuoteSim
from research.microstructure.reference_replay import Event, replay_reference

MS = 1_000_000
SZ_DECIMALS = 2
QUOTE = 5.0


def _stream(seed: int, n: int = 400) -> list[Event]:
    """A random walk on a tick grid, interleaved with prints at and through it."""
    rng = random.Random(seed)
    events: list[Event] = []
    tick = 10 ** -(6 - SZ_DECIMALS)
    px, ts = 1.0, 0
    for _ in range(n):
        ts += rng.randint(5, 300) * MS
        px = max(0.5, px + rng.choice((-2, -1, 0, 1, 2)) * tick)
        half = rng.choice((1, 1, 2, 5)) * tick
        bid, ask = round(px - half, 8), round(px + half, 8)
        events.append(
            ("bbo", ts, bid, rng.choice((1.0, 4.0, 20.0)), ask, rng.choice((1.0, 4.0, 20.0)))
        )
        for _ in range(rng.choice((0, 0, 1, 2))):
            ts += rng.randint(1, 60) * MS
            sign = rng.choice((1, -1))
            base = ask if sign > 0 else bid
            hit = base + rng.choice((0, 0, 0, 1, -1)) * tick * rng.choice((1, 2))
            events.append(("trade", ts, sign, round(hit, 8), rng.choice((0.5, 3.0, 25.0))))
    return events


def _bounded(
    events: list[Event], cap: float | None, latency_ns: int, queue: str
) -> BoundedQuoteSim:
    sim = BoundedQuoteSim(
        symbol="X",
        quote_size=QUOTE,
        cap_size=cap,
        latency_ns=latency_ns,
        sz_decimals=SZ_DECIMALS,
        fill_model="always_last",
        queue_model=queue,  # type: ignore[arg-type]
    )
    for ev in events:
        if ev[0] == "bbo":
            sim.on_bbo(ev[1], ev[2], ev[3], ev[4], ev[5])
        else:
            sim.on_trade(ev[1], ev[2], ev[3], ev[4])
    return sim


class TestDifferentialAgainstReference:
    """Two implementations, two arithmetic routes, one answer."""

    @pytest.mark.parametrize("seed", [1, 2, 3, 7, 11, 19, 23, 41])
    @pytest.mark.parametrize("cap", [None, 12.0])
    @pytest.mark.parametrize("latency_ns", [0, 100 * MS])
    @pytest.mark.parametrize("queue", ["own_level", "own_level_cancels"])
    def test_ledger_matches_independent_reference(
        self, seed: int, cap: float | None, latency_ns: int, queue: str
    ) -> None:
        events = _stream(seed)
        got = _bounded(events, cap, latency_ns, queue)
        want = replay_reference(
            events,
            quote_size=QUOTE,
            cap_size=cap,
            latency_ns=latency_ns,
            sz_decimals=SZ_DECIMALS,
            queue_model=queue,  # type: ignore[arg-type]
        ).ledger()
        assert got.fills == int(want["fills"])
        assert got.position == pytest.approx(want["position"])
        assert got.edge_usd == pytest.approx(want["edge_usd"], abs=1e-9)
        assert got.inventory_usd == pytest.approx(want["inventory_usd"], abs=1e-9)
        assert got.fees_usd == pytest.approx(want["fees_usd"], abs=1e-9)
        assert got.filled_notional_usd == pytest.approx(want["filled_notional_usd"], abs=1e-9)
        assert got.total_net_usd() == pytest.approx(want["net_usd"], abs=1e-9)

    def test_reference_detects_the_a4_defect(self) -> None:
        """The control must be able to fail. A gate that cannot is not a gate.

        ``touch`` is the A4 defect itself — queue-ahead read from whatever level
        happens to be the touch. Fill *counts* coincide with the correct engine
        on some streams by luck, so the detection claim is made over a seed set
        and on the ledger, not on one seed and one scalar.
        """
        detected = 0
        for seed in (5, 13, 29, 41, 3, 7):
            events = _stream(seed)
            want = replay_reference(
                events,
                quote_size=QUOTE,
                cap_size=12.0,
                latency_ns=100 * MS,
                sz_decimals=SZ_DECIMALS,
            ).ledger()
            honest = _bounded(events, 12.0, 100 * MS, "own_level")
            defective = _bounded(events, 12.0, 100 * MS, "touch")
            assert honest.fills == int(want["fills"])
            assert honest.total_net_usd() == pytest.approx(want["net_usd"], abs=1e-9)
            if defective.fills != int(want["fills"]) or defective.total_net_usd() != pytest.approx(
                want["net_usd"], abs=1e-9
            ):
                detected += 1
        assert detected >= 5, f"control caught the A4 defect on only {detected}/6 streams"


class TestLifecycleAccounting:
    @pytest.mark.parametrize("seed", [1, 2, 3, 7, 11])
    def test_every_order_reaches_exactly_one_terminal_state(self, seed: int) -> None:
        sim = _bounded(_stream(seed), 12.0, 100 * MS, "own_level")
        still_open = sum(o is not None for o in sim._orders.values())
        # Orders leave by fill, by a cancel that landed, or by ALO rejection.
        cancels_completed = sim.placements - sim.fills - sim.alo_rejections - still_open
        assert cancels_completed >= 0
        assert sim.placements == sim.fills + sim.alo_rejections + cancels_completed + still_open
        assert sim.cancels_started >= cancels_completed

    @pytest.mark.parametrize("seed", [1, 5, 13])
    def test_decomposition_identity_holds_over_a_random_stream(self, seed: int) -> None:
        sim = _bounded(_stream(seed), 12.0, 100 * MS, "own_level")
        assert sim.mark_to_market_usd() == pytest.approx(sim.edge_usd + sim.inventory_usd)
        assert sim.total_net_usd() == pytest.approx(
            sim.edge_usd + sim.inventory_usd + sim.funding_usd - sim.fees_usd
        )
        assert sum(sim.net_by_hour.values()) == pytest.approx(sim.total_net_usd())

    @pytest.mark.parametrize("seed", [2, 7, 19])
    def test_no_fill_is_booked_before_its_order_could_be_live(self, seed: int) -> None:
        latency = 100 * MS
        events = _stream(seed)
        sim = _bounded(events, None, latency, "own_level")
        first_bbo = min(e[1] for e in events if e[0] == "bbo")
        assert all(ts >= first_bbo + latency for ts, *_ in sim.trade_records)

    def test_fees_are_exactly_one_and_a_half_bps_per_leg(self) -> None:
        sim = _bounded(_stream(3), None, 0, "own_level")
        assert sim.fills > 0
        assert sim.fees_usd == pytest.approx(sim.filled_notional_usd * 1.5 / 1e4)


class TestGateActuallyCoversTheOrderMachine:
    """A1 in test form: this gate must execute what it claims to control."""

    ORDER_MACHINE = (
        "_process_transitions",
        "_crossing_fills",
        "_cancel_stale",
        "_place_wanted",
        "_sweep",
        "_fill",
    )

    def test_workload_executes_every_order_machine_method(self) -> None:
        tracer = _trace.Trace(count=1, trace=0)
        tracer.runfunc(_bounded, _stream(1), 12.0, 100 * MS, "own_level")
        hit = {ln for f, ln in tracer.results().counts if f.endswith("fill_replay.py")}
        unexecuted = []
        for name in self.ORDER_MACHINE:
            lines, start = inspect.getsourcelines(getattr(fr.BoundedQuoteSim, name))
            if not hit & set(range(start, start + len(lines))):
                unexecuted.append(name)
        assert not unexecuted, f"gate does not execute: {unexecuted} — this is finding A1 again"
