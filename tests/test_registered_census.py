"""Tests for the C.18 registered census machinery.

Everything here runs on synthetic data. The ten thin instruments' recorded
bytes are the scored population and are not touched by any test — the guard
that enforces that has its own test, and the adverse-selection canary fires in
both directions so a null census result on 2026-08-11 will mean something
(ADR-040's capable-of-firing rule).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import zstandard

from research.microstructure import registered as reg
from research.microstructure.census import run_census

NS_PER_MS = 1_000_000
NS_PER_S = 1_000_000_000
T0 = reg.SCORED_START_NS  # inside the scored window for panel tests


def bbo_line(recv_ns: int, coin: str, bid: float, ask: float) -> str:
    raw = json.dumps(
        {
            "channel": "bbo",
            "data": {
                "coin": coin,
                "time": 1,
                "bbo": [
                    {"px": str(bid), "sz": "1.0", "n": 1},
                    {"px": str(ask), "sz": "1.0", "n": 1},
                ],
            },
        }
    )
    return json.dumps({"recv_ns": recv_ns, "raw": raw})


def trade_line(recv_ns: int, coin: str, side: str, px: float, sz: float) -> str:
    raw = json.dumps(
        {
            "channel": "trades",
            "data": [
                {
                    "coin": coin,
                    "side": side,
                    "px": str(px),
                    "sz": str(sz),
                    "time": 1,
                    "hash": "0x0",
                    "tid": 1,
                    "users": ["0xa", "0xb"],
                }
            ],
        }
    )
    return json.dumps({"recv_ns": recv_ns, "raw": raw})


def write_day(raw_dir: Path, date: str, lines: list[str]) -> None:
    hour = raw_dir / "venue=hyperliquid" / f"date={date}" / "hour=00"
    hour.mkdir(parents=True)
    payload = ("\n".join(lines) + "\n").encode()
    (hour / "messages.ndjson.zst").write_bytes(zstandard.ZstdCompressor().compress(payload))


# --------------------------------------------------------------------------- #
# the guard, and the allowlist
# --------------------------------------------------------------------------- #


def test_census_refuses_to_run_before_the_window_closes(tmp_path: Path) -> None:
    # Act / Assert — one nanosecond early is early.
    with pytest.raises(RuntimeError, match=reg.REGISTRATION_COMMIT):
        reg.run_registered_census(tmp_path, [], now_ns=reg.SCORED_END_NS - 1)
    # At the boundary the guard opens (empty data -> ten too-thin reports).
    reports, verdict = reg.run_registered_census(tmp_path, [], now_ns=reg.SCORED_END_NS)
    assert len(reports) == len(reg.THIN_COINS)
    assert all(r["category"] == "too_thin_by_prior_declaration" for r in reports)
    assert "H6 closes" in verdict["registered_action"]


def test_known_answer_allowlist_excludes_thin_coins_at_the_parse_level(tmp_path: Path) -> None:
    # Arrange — a day containing BTC and PUMP traffic.
    lines = [
        bbo_line(T0 + 1 * NS_PER_S, "BTC", 100.0, 100.02),
        bbo_line(T0 + 1 * NS_PER_S + 1, "PUMP", 0.0025, 0.0026),
        trade_line(T0 + 2 * NS_PER_S, "BTC", "B", 100.02, 1.0),
        trade_line(T0 + 2 * NS_PER_S + 1, "PUMP", "B", 0.0026, 1000.0),
        bbo_line(T0 + 4 * NS_PER_S, "BTC", 100.0, 100.02),
        bbo_line(T0 + 4 * NS_PER_S + 1, "PUMP", 0.0025, 0.0026),
    ]
    write_day(tmp_path, "2026-08-04", lines)

    # Act
    result = run_census(tmp_path, "2026-08-04", coins={"BTC", "ETH"})

    # Assert — the thin coin never reaches an accumulator, not even as a key.
    assert "BTC" in result.instruments
    assert "PUMP" not in result.instruments


# --------------------------------------------------------------------------- #
# the registered measure
# --------------------------------------------------------------------------- #


def test_trade_time_spread_state_is_the_spread_the_fill_saw() -> None:
    # Arrange — wide quote, a trade, then the book tightens. C.9's time-
    # weighted mean would blend the tight regime in; the registered measure
    # must credit the fill with the ~10 bps that stood when it happened.
    inst = reg.RegisteredInstrument(symbol="X")
    inst.on_quote(T0, 99.95, 100.05)  # ~10 bps
    inst.on_trade(T0 + 100 * NS_PER_MS, +1, 100.05, 1.0)
    inst.on_quote(T0 + 200 * NS_PER_MS, 100.0, 100.002)  # ~0.2 bps, tight
    inst.on_quote(T0 + 90 * NS_PER_S, 100.0, 100.002)  # resolve every horizon

    # Act
    rows = inst.rows[1_000]

    # Assert
    assert len(rows) == 1
    assert rows[0][1] == pytest.approx(10.0, abs=0.1)


def test_adverse_canary_fires_in_both_directions() -> None:
    # Arrange/Act — world 1: every buy is followed by the mid marching up
    # (informed flow). World 2: every buy is followed by reversion down.
    def build(drift: float) -> reg.RegisteredInstrument:
        inst = reg.RegisteredInstrument(symbol="X")
        price = 100.0
        ts = T0
        for _ in range(400):
            inst.on_quote(ts, price - 0.005, price + 0.005)  # ~1 bps spread
            inst.on_trade(ts + 10 * NS_PER_MS, +1, price + 0.005, 1.0)
            price *= 1.0 + drift
            # The moved mid must be QUOTED before the deadlines, or the
            # resolver — correctly — reports zero drift: a deadline resolves
            # against the last mid at or before it, never a later one.
            inst.on_quote(ts + 200 * NS_PER_MS, price - 0.005, price + 0.005)
            ts += 70 * NS_PER_S  # beyond the longest horizon: full resolution
        inst.on_quote(ts, price - 0.005, price + 0.005)
        return inst

    adverse_world = reg.instrument_report(build(+0.0008))  # ~8 bps against the fill
    benign_world = reg.instrument_report(build(-0.0008))  # ~8 bps of reversion

    # Assert — the pipeline must distinguish the worlds decisively, or a null
    # census verdict would mean nothing.
    assert adverse_world["floor_met"] and benign_world["floor_met"]
    assert float(adverse_world["ci95_lower_bps_worst"]) < -5.0
    assert float(benign_world["ci95_lower_bps_worst"]) > 2.0
    assert benign_world["holds_in_both_halves"] is False  # every trade in half one


def test_prefix_invariance_rows_resolved_early_never_change() -> None:
    # Arrange — the same stream, full and truncated; rows resolved within the
    # prefix must be identical whether or not the future arrived.
    def feed(inst: reg.RegisteredInstrument, n: int) -> None:
        price = 50.0
        for i in range(n):
            ts = T0 + i * 120 * NS_PER_S
            inst.on_quote(ts, price - 0.01, price + 0.01)
            inst.on_trade(ts + NS_PER_S, -1 if i % 2 else +1, price, 2.0)
            price += 0.02 if i % 3 else -0.03

    full = reg.RegisteredInstrument(symbol="X")
    feed(full, 40)
    prefix = reg.RegisteredInstrument(symbol="X")
    feed(prefix, 25)

    # Act / Assert
    for horizon in reg.HORIZONS_MS:
        head = full.rows[horizon][: len(prefix.rows[horizon])]
        assert head == prefix.rows[horizon]


# --------------------------------------------------------------------------- #
# bars: floor, halves, multiplicity, outcome map
# --------------------------------------------------------------------------- #


def _report(symbol: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "symbol": symbol,
        "floor_met": True,
        "net_mean_bps_worst": 1.0,
        "ci95_lower_bps_worst": 0.4,
        "p_one_sided_worst": 0.001,
        "holds_in_both_halves": True,
        "capacity_tier_met": True,
        "trades_per_day": 500.0,
        "median_daily_usd": 250_000.0,
    }
    base.update(overrides)
    return base


def test_sample_floor_declares_too_thin_never_stretches() -> None:
    # Arrange — 299 resolved trades is one short of the registered floor.
    inst = reg.RegisteredInstrument(symbol="X")
    price = 10.0
    for i in range(299):
        ts = T0 + i * 130 * NS_PER_S
        inst.on_quote(ts, price - 0.001, price + 0.001)
        inst.on_trade(ts + NS_PER_S, +1, price, 1.0)
    inst.on_quote(T0 + 299 * 130 * NS_PER_S, price - 0.001, price + 0.001)

    # Act / Assert
    assert reg.instrument_report(inst)["category"] == "too_thin_by_prior_declaration"


def test_outcome_map_matches_the_registration() -> None:
    # All fail -> H6 closes.
    verdict = reg.assemble(
        [_report("A", net_mean_bps_worst=-1.0, ci95_lower_bps_worst=-2.0, p_one_sided_worst=0.9)]
    )
    assert "H6 closes" in verdict["registered_action"]
    # Survivor with capacity -> D.1 input, and the expected FP count is stated.
    verdict = reg.assemble([_report("B")])
    assert "D.1 fill-simulation" in verdict["registered_action"]
    assert verdict["survivors_all_bars"] == ["B"]
    assert verdict["expected_false_positives"] == pytest.approx(0.1)
    # Survivor without capacity -> fill-frequency arithmetic, stop.
    verdict = reg.assemble([_report("C", capacity_tier_met=False)])
    assert "fill-frequency" in verdict["registered_action"]
    # Positive but CI straddling zero -> extend 30 days, no building.
    verdict = reg.assemble([_report("D", ci95_lower_bps_worst=-0.2, p_one_sided_worst=0.2)])
    assert "extend recording 30 days" in verdict["registered_action"]


def test_one_spike_is_not_an_edge_by_prior_declaration() -> None:
    # Arrange — passes everything except the halves requirement.
    verdict = reg.assemble([_report("E", holds_in_both_halves=False)])

    # Assert — episodic income is filed as noise, and the action is the
    # extend-and-re-run branch, never a pass.
    assert verdict["categories"]["E"] == "suggestive_noise_of_zero"
    assert verdict["survivors_all_bars"] == []
    assert "extend recording 30 days" in verdict["registered_action"]
