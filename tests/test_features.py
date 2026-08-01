"""Feature functions against hand-computed values."""

from __future__ import annotations

import math

from research.features.book import (
    book_asymmetry,
    depth_weighted_price_minus_mid,
    ofi_best,
    queue_imbalance,
    spread_bps,
)
from research.features.cross_venue import CrossVenueTracker
from research.features.rolling import WindowSum
from research.features.signing import SIGNING_METHOD, sign_trade, tick_rule_sign
from research.stream.events import BookState

NS_PER_S = 1_000_000_000
BASE_NS = 1_785_412_800 * 1_000_000_000


def _book(bid: float, bid_qty: float, ask: float, ask_qty: float, valid: bool = True) -> BookState:
    mid = (bid + ask) / 2
    micro = (bid_qty * ask + ask_qty * bid) / (bid_qty + ask_qty)
    return BookState(
        best_bid=bid,
        bid_qty=bid_qty,
        best_ask=ask,
        ask_qty=ask_qty,
        mid=mid,
        microprice=micro,
        bid_prices=(bid, bid - 1.0),
        bid_qtys=(bid_qty, 2.0),
        ask_prices=(ask, ask + 1.0),
        ask_qtys=(ask_qty, 4.0),
        valid=valid,
    )


def test_ofi_best_matches_cont_kukanov_stoikov_cases() -> None:
    # Arrange: unchanged best prices — e_n = q_bid_now - q_bid_prev - (q_ask_now - q_ask_prev).
    prev = _book(100.0, 3.0, 101.0, 2.0)
    curr = _book(100.0, 5.0, 101.0, 2.5)
    assert ofi_best(prev, curr) == (5.0 - 3.0) - (2.5 - 2.0)

    # Bid improves: full new bid qty counts positive, previous not subtracted.
    improved = _book(100.5, 4.0, 101.0, 2.0)
    assert ofi_best(prev, improved) == 4.0 - (2.0 - 2.0)


def test_queue_imbalance_and_spread_bps() -> None:
    book = _book(100.0, 3.0, 101.0, 1.0)
    assert queue_imbalance(book) == (3.0 - 1.0) / 4.0
    assert math.isclose(spread_bps(book) or 0.0, 1e4 * 1.0 / 100.5)


def test_book_asymmetry_and_depth_weighted_price() -> None:
    book = _book(100.0, 1.0, 101.0, 1.0)
    # Depths: bids (1, 2), asks (1, 4) → asym = (3 - 5) / 8.
    assert book_asymmetry(book, 2) == (3.0 - 5.0) / 8.0
    dwp = depth_weighted_price_minus_mid(book, 1)
    assert dwp is not None and math.isclose(dwp, (100.0 + 101.0) / 2 - 100.5)


def test_invalid_inputs_produce_none_never_zero() -> None:
    empty = BookState(None, None, None, None, None, None, (), (), (), (), False)
    assert queue_imbalance(empty) is None
    assert spread_bps(empty) is None
    assert book_asymmetry(empty, 5) is None


def test_signing_uses_venue_flag_on_kraken_and_tick_rule_on_coinbase() -> None:
    assert SIGNING_METHOD == {"kraken": "venue_flag", "coinbase": "tick_rule"}
    assert sign_trade("kraken", "buy", 100.0, None, 0) == 1
    assert sign_trade("kraken", "sell", 100.0, None, 0) == -1
    # Coinbase ignores its ambiguous flag: uptick > 0, zero-tick carries.
    assert sign_trade("coinbase", "BUY", 101.0, 100.0, 0) == 1
    assert sign_trade("coinbase", "SELL", 101.0, 100.0, 0) == 1
    assert sign_trade("coinbase", "BUY", 101.0, 101.0, -1) == -1
    assert tick_rule_sign(100.0, None, 0) == 0, "no history means unknown, not a guess"


def test_window_sum_prunes_exactly_at_the_window_edge() -> None:
    window = WindowSum(NS_PER_S)
    window.add(BASE_NS, 1.0)
    window.add(BASE_NS + NS_PER_S // 2, 2.0)
    assert window.total(BASE_NS + NS_PER_S // 2) == 3.0
    # First value's timestamp is exactly window-edge: excluded (half-open).
    assert window.total(BASE_NS + NS_PER_S) == 2.0
    assert window.count(BASE_NS + 2 * NS_PER_S) == 0


def test_cross_venue_diff_and_leadlag_detect_a_planted_lead() -> None:
    tracker = CrossVenueTracker(bin_ms=100, window_s=30, offsets_ms=(-500, 0, 500))
    # Reference venue moves first; primary repeats the same return 500 ms later.
    reference_mid = 100.0
    steps = [1.0 if i % 3 else -1.0 for i in range(200)]
    for i, step in enumerate(steps):
        ts = BASE_NS + i * 100 * 1_000_000
        reference_mid += step
        tracker.on_mid("reference", ts, reference_mid)
        if i >= 5:
            primary_mid = 100.0 + sum(steps[: i - 4])  # 5 bins = 500 ms behind
            tracker.on_mid("primary", ts, primary_mid)
    diff = tracker.mid_diff_bps()
    assert diff is not None
    leadlag = tracker.leadlag()
    lagged = leadlag[500]
    contemporaneous = leadlag[0]
    assert lagged is not None and lagged > 0.9, "reference leads primary by 500 ms"
    assert contemporaneous is None or abs(contemporaneous) < 0.5
