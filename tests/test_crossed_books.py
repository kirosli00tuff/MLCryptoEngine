"""Crossed books: explained inside a no-match window, excluded from features.

Built from the real MES 2026-07-15 crossings (193 events, 192 in the 21:00Z
maintenance halt, the last 9.9 ms after the 22:00:00Z reopen). Timestamps and
prices below are the measured ones, so this is a regression test against the
actual data on disk rather than an invented scenario.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from data.databento.session import (
    REOPEN_AUCTION_GRACE_MS,
    in_no_match_window,
    no_match_windows_ns,
)
from research.features.engine import FeatureEngine
from research.stream.events import BookState, StreamEvent, Trade

DATE = "2026-07-15"
NS_PER_MS = 1_000_000


def _ns(iso: str) -> int:
    stamp = datetime.fromisoformat(iso).replace(tzinfo=UTC)
    return int(stamp.timestamp()) * 1_000_000_000 + stamp.microsecond * 1000


# Measured crossing timestamps from MES_c_0.mbp-10 on 2026-07-15.
FIRST_CROSSING_NS = _ns("2026-07-15T21:45:22.809237")
MID_CROSSING_NS = _ns("2026-07-15T21:46:11.374326")
LAST_CROSSING_NS = _ns("2026-07-15T22:00:00.009936")
# The measured inverted book: bid 39.25 points above ask, held for minutes.
CROSSED_BID, CROSSED_ASK = 7655.00, 7615.75


def test_measured_crossings_all_fall_inside_a_no_match_window() -> None:
    """The regression: every real crossing must classify as explained."""
    for ts in (FIRST_CROSSING_NS, MID_CROSSING_NS, LAST_CROSSING_NS):
        assert in_no_match_window(ts, DATE), f"{ts} should be inside a no-match window"

    windows = no_match_windows_ns(DATE)
    assert windows, "2026-07-15 has a maintenance halt"
    start, end = windows[-1]
    assert datetime.fromtimestamp(start / 1e9, tz=UTC).hour == 21
    # The window extends past 22:00:00Z by exactly the auction grace.
    assert end == _ns("2026-07-15T22:00:00") + REOPEN_AUCTION_GRACE_MS * NS_PER_MS


def test_a_crossing_during_open_trading_is_not_explained() -> None:
    """The classification must not become a blanket excuse: mid-session
    crossings still fail."""
    assert not in_no_match_window(_ns("2026-07-15T14:30:00"), DATE)
    # And well clear of the reopen grace.
    assert not in_no_match_window(_ns("2026-07-15T22:00:02"), DATE)


def _crossed_book(crossed: bool) -> BookState:
    bid, ask = (CROSSED_BID, CROSSED_ASK) if crossed else (7615.50, 7615.75)
    return BookState(
        best_bid=bid,
        bid_qty=7.0,
        best_ask=ask,
        ask_qty=4.0,
        mid=(bid + ask) / 2,
        microprice=(bid + ask) / 2,
        bid_prices=(bid,),
        bid_qtys=(7.0,),
        ask_prices=(ask,),
        ask_qtys=(4.0,),
        valid=True,
        crossed=crossed,
    )


def test_crossed_state_is_not_usable_and_excludes_the_sample() -> None:
    """A crossed book must produce exclusion, not a value: the pipeline marks
    samples invalid via book_is_valid, exactly as for gaps."""
    assert _crossed_book(crossed=True).usable is False
    assert _crossed_book(crossed=False).usable is True

    engine = FeatureEngine("cme", "MES")
    base = 1_784_000_000 * 1_000_000_000

    engine.on_event(StreamEvent("cme", "MES", base, None, _crossed_book(False), None))
    assert engine.book_is_valid, "a normal book supports features"

    engine.on_event(StreamEvent("cme", "MES", base + 1_000_000, None, _crossed_book(True), None))
    assert not engine.book_is_valid, "a crossed book must exclude the sample"


def test_crossed_book_never_enters_the_return_series() -> None:
    """The inverted mid would be a ~20-point jump against the real price and
    would poison realized vol for the whole window."""
    engine = FeatureEngine("cme", "MES")
    base = 1_784_000_000 * 1_000_000_000
    engine.on_event(StreamEvent("cme", "MES", base, None, _crossed_book(False), None))
    mid_before = engine.last_mid

    engine.on_event(StreamEvent("cme", "MES", base + 1_000_000, None, _crossed_book(True), None))

    assert engine.last_mid == mid_before, "the crossed mid must not update price state"
    features = engine.compute(base + 2_000_000)
    for name in ("spread_bps", "micro_minus_mid", "qimb_best", "dwp_minus_mid"):
        assert features[name] is None, f"{name} must be excluded during a crossed book"
    assert features["rvol_1s"] == pytest.approx(0.0), "no fabricated volatility"


def test_locked_book_is_reported_but_still_usable() -> None:
    """bid == ask is degenerate, not impossible; it is counted, not excluded."""
    locked = BookState(
        best_bid=7615.75,
        bid_qty=1.0,
        best_ask=7615.75,
        ask_qty=1.0,
        mid=7615.75,
        microprice=7615.75,
        bid_prices=(7615.75,),
        bid_qtys=(1.0,),
        ask_prices=(7615.75,),
        ask_qtys=(1.0,),
        valid=True,
        locked=True,
    )
    assert locked.usable is True
    assert locked.locked is True


def test_trades_still_flow_while_the_book_is_crossed() -> None:
    """Excluding the book must not silently drop trade-derived state."""
    engine = FeatureEngine("cme", "MES")
    base = 1_784_000_000 * 1_000_000_000
    engine.on_event(StreamEvent("cme", "MES", base, None, _crossed_book(True), None))
    engine.on_event(StreamEvent("cme", "MES", base + 1, base, None, Trade(7615.75, 2.0, "buy")))

    features = engine.compute(base + 1_000_000)
    assert features["signed_vol_1s"] == pytest.approx(2.0)
    assert features["spread_bps"] is None
