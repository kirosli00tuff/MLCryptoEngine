"""Labels: fixed-horizon resolution, triple barrier, cost-aware overlays."""

from __future__ import annotations

import math

from data.config import load_config
from research.labels.costs import cost_model_from_config, net_label
from research.labels.fixed_horizon import FixedHorizonLabeler
from research.labels.triple_barrier import TripleBarrierLabeler

NS_PER_MS = 1_000_000
BASE_NS = 1_785_412_800 * 1_000_000_000


def test_fixed_horizon_resolves_against_last_mid_at_or_before_deadline() -> None:
    labeler = FixedHorizonLabeler(horizons_ms=(100,))
    labeler.on_mid(BASE_NS, 100.0)
    labeler.on_sample(0, BASE_NS + NS_PER_MS, entry_mid=100.0)

    # A mid before the deadline updates the running exit price...
    assert labeler.on_mid(BASE_NS + 50 * NS_PER_MS, 101.0) == []
    # ...and the first mid after the deadline resolves against it, not itself.
    resolved = labeler.on_mid(BASE_NS + 200 * NS_PER_MS, 999.0)
    assert len(resolved) == 1
    index, horizon_ms, ret_bps = resolved[0]
    assert (index, horizon_ms) == (0, 100)
    assert math.isclose(ret_bps, 1e4 * (101.0 - 100.0) / 100.0)


def test_fixed_horizon_censors_samples_at_end_of_stream() -> None:
    labeler = FixedHorizonLabeler(horizons_ms=(100, 500))
    labeler.on_sample(3, BASE_NS, entry_mid=100.0)
    assert sorted(labeler.finalize()) == [(3, 100), (3, 500)]
    assert labeler.finalize() == [], "finalize drains the queues"


def test_triple_barrier_profit_stop_and_timeout() -> None:
    labeler = TripleBarrierLabeler(pt_mult=2.0, sl_mult=2.0, time_limit_ms=1000)
    vol = 0.01  # barriers at ±2%
    assert labeler.on_sample(0, BASE_NS, entry_mid=100.0, vol_fraction=vol)
    assert labeler.on_sample(1, BASE_NS, entry_mid=100.0, vol_fraction=vol)
    assert labeler.on_sample(2, BASE_NS, entry_mid=100.0, vol_fraction=vol)

    up = labeler.on_mid(BASE_NS + NS_PER_MS, 102.5)
    assert [(o.index, o.label) for o in up] == [(0, 1), (1, 1), (2, 1)]

    # Fresh sample: stop side.
    assert labeler.on_sample(3, BASE_NS, entry_mid=100.0, vol_fraction=vol)
    down = labeler.on_mid(BASE_NS + 2 * NS_PER_MS, 97.0)
    assert [(o.index, o.label) for o in down] == [(3, -1)]

    # Timeout: within barriers until past the deadline. The outcome resolves
    # against the last mid at-or-before the deadline (100.5), never against
    # the mid that finally notices the deadline passed — even when that later
    # mid (103.0) would have crossed a barrier outside the time limit.
    assert labeler.on_sample(4, BASE_NS, entry_mid=100.0, vol_fraction=vol)
    assert labeler.on_mid(BASE_NS + 500 * NS_PER_MS, 100.5) == []
    timed_out = labeler.on_mid(BASE_NS + 1_500 * NS_PER_MS, 103.0)
    assert [(o.index, o.label) for o in timed_out] == [(4, 0)]
    assert math.isclose(timed_out[0].ret_bps, 1e4 * 0.5 / 100.0), (
        "timeout return must not read past the time limit"
    )


def test_triple_barrier_refuses_unusable_volatility() -> None:
    labeler = TripleBarrierLabeler()
    assert labeler.on_sample(0, BASE_NS, entry_mid=100.0, vol_fraction=0.0) is False


def test_net_label_requires_clearing_round_trip_cost() -> None:
    assert net_label(ret_bps=5.0, cost_bps=4.0) == 1
    assert net_label(ret_bps=3.9, cost_bps=4.0) == 0, "sub-cost move is a non-event"
    assert net_label(ret_bps=-5.0, cost_bps=4.0) == -1


def test_cost_models_come_from_venue_config_and_differ_by_mode() -> None:
    venues = load_config().venues
    maker = cost_model_from_config("kraken", venues["kraken"], "maker")
    taker = cost_model_from_config("kraken", venues["kraken"], "taker")

    assert maker.fee_bps_per_leg == venues["kraken"].fee_tiers[0].maker_bps
    assert taker.fee_bps_per_leg == venues["kraken"].fee_tiers[0].taker_bps
    spread_bps = 1.0
    maker_cost = maker.round_trip_cost_bps(spread_bps)
    taker_cost = taker.round_trip_cost_bps(spread_bps)
    assert maker_cost == 2 * maker.fee_bps_per_leg, "maker legs rest; no spread paid"
    assert taker_cost == 2 * taker.fee_bps_per_leg + spread_bps
    assert taker_cost > maker_cost, "the answer differs enormously between assumptions"
