"""Capability matrix: unsupported features raise, and the engine nulls them."""

from __future__ import annotations

import pytest

from data.book import emitted_channels
from research.features.capabilities import (
    ALL_FEATURES,
    BBO_AND_TRADE_FEATURES,
    DEPTH_FEATURES,
    SUB_100MS_FEATURES,
    UnsupportedFeatureError,
    assert_stream_supports,
    require_supported,
    supported_features,
)
from research.features.engine import FEATURE_COLUMNS, FeatureEngine
from research.stream.events import Bbo, BookState, StreamEvent, Trade

BASE_NS = 1_785_412_800 * 1_000_000_000


def test_matrix_stays_in_exact_correspondence_with_the_feature_library() -> None:
    assert frozenset(FEATURE_COLUMNS) == ALL_FEATURES, (
        "capability matrix and FEATURE_COLUMNS drifted — every feature must be classified"
    )
    assert not (DEPTH_FEATURES & BBO_AND_TRADE_FEATURES)


def test_microprice_is_supported_because_bbo_carries_best_level_sizes() -> None:
    """Verified 2026-08-01 against 171,195 recorded bbo updates: every one
    carries px AND sz on both sides, e.g.
    {"px":"62362.0","sz":"13.27152","n":29}. Microprice weights the mid by
    resting size, so this classification is correct — but only at bbo
    resolution, which is why hyperliquid is in REQUIRED_CHANNELS."""
    require_supported("hyperliquid", "micro_minus_mid")
    assert "micro_minus_mid" in supported_features("hyperliquid")


def test_features_binned_finer_than_measured_bbo_cadence_are_unsupported() -> None:
    """100 ms lead-lag bins against a measured 123 ms median bbo interval
    leave most bins empty — a sparse subsample, not a correlation."""
    assert {"xv_leadlag_m100", "xv_leadlag_p100"} == SUB_100MS_FEATURES
    for feature in SUB_100MS_FEATURES:
        assert feature not in supported_features("hyperliquid")
        with pytest.raises(UnsupportedFeatureError, match="not supported"):
            require_supported("hyperliquid", feature)
        # Full-L2 venues update far faster than 100 ms and keep them.
        require_supported("kraken", feature)
    # The coarser cross-venue bins survive.
    for feature in ("xv_leadlag_0", "xv_leadlag_m500", "xv_leadlag_p500", "xv_mid_diff_bps"):
        require_supported("hyperliquid", feature)


def test_crediting_hyperliquid_requires_the_bbo_channel_in_the_stream() -> None:
    """Both directions: raises when bbo is absent from the stream, passes
    when present. l2Book alone is p50 5,387 ms, so computing microprice from
    it would be silently 5 seconds stale."""
    assert_stream_supports("hyperliquid", frozenset({"l2Book", "bbo", "trades"}))
    with pytest.raises(UnsupportedFeatureError, match="requires the 'bbo' channel"):
        assert_stream_supports("hyperliquid", frozenset({"l2Book", "trades"}))
    # Venues with no channel precondition are unaffected.
    assert_stream_supports("kraken", frozenset({"book"}))


def test_the_hyperliquid_parser_now_actually_emits_the_channel_it_requires() -> None:
    """The gate is only meaningful if it reads what the parser really emits:
    the requirement is satisfied by data.book.emitted_channels, not by a
    hand-maintained list that could drift from the parser."""
    assert "bbo" in emitted_channels("hyperliquid")
    assert_stream_supports("hyperliquid", emitted_channels("hyperliquid"))
    # And it would still catch a parser that stopped emitting bbo.
    with pytest.raises(UnsupportedFeatureError, match="requires the 'bbo' channel"):
        assert_stream_supports("hyperliquid", emitted_channels("hyperliquid") - {"bbo"})


def test_requesting_an_unsupported_feature_raises_rather_than_returning() -> None:
    require_supported("hyperliquid", "spread_bps")  # supported: no raise
    with pytest.raises(UnsupportedFeatureError, match="not supported"):
        require_supported("hyperliquid", "ofi_best_1s")
    # qimb_best IS supported: bbo carries best-level sizes (Stage C.2).
    require_supported("hyperliquid", "qimb_best")
    with pytest.raises(UnsupportedFeatureError, match="not supported"):
        require_supported("hyperliquid", "depth_bid_2")
    with pytest.raises(UnsupportedFeatureError, match="no declared capability"):
        require_supported("binance", "spread_bps")
    with pytest.raises(UnsupportedFeatureError, match="unknown feature"):
        require_supported("kraken", "made_up_feature")
    with pytest.raises(UnsupportedFeatureError):
        supported_features("undeclared_venue")


def _book_event(venue: str, ts_ns: int) -> StreamEvent:
    book = BookState(
        best_bid=100.0,
        bid_qty=2.0,
        best_ask=101.0,
        ask_qty=1.0,
        mid=100.5,
        microprice=100.33,
        bid_prices=(100.0, 99.0),
        bid_qtys=(2.0, 3.0),
        ask_prices=(101.0, 102.0),
        ask_qtys=(1.0, 4.0),
        valid=True,
    )
    return StreamEvent(venue, "BTC", ts_ns, None, book, None)


def _bbo_event(venue: str, ts_ns: int) -> StreamEvent:
    return StreamEvent(
        venue,
        "BTC",
        ts_ns,
        None,
        None,
        None,
        bbo=Bbo(
            best_bid=100.0,
            bid_qty=2.0,
            best_ask=101.0,
            ask_qty=1.0,
            mid=100.5,
            microprice=100.33,
            bid_n=4,
            ask_n=2,
        ),
    )


def test_engine_nulls_unsupported_features_instead_of_computing_garbage() -> None:
    hyperliquid = FeatureEngine("hyperliquid", "BTC")
    kraken = FeatureEngine("kraken", "BTC")
    for i in range(3):
        ts = BASE_NS + i * 1_000_000_000
        # Hyperliquid gets both channels, as the real stream now delivers:
        # depth from l2Book, touch and mid from bbo.
        hyperliquid.on_event(_book_event("hyperliquid", ts))
        hyperliquid.on_event(_bbo_event("hyperliquid", ts + 500_000))
        kraken.on_event(_book_event("kraken", ts))
        trade = StreamEvent("x", "BTC", ts + 1, ts, None, Trade(100.5, 1.0, "buy"))
        hyperliquid.on_event(trade)
        kraken.on_event(trade)

    t = BASE_NS + 10_000_000_000
    hl_features = hyperliquid.compute(t)
    kraken_features = kraken.compute(t)

    for name in DEPTH_FEATURES | SUB_100MS_FEATURES:
        assert hl_features[name] is None, f"{name} must be nulled on a snapshot-stream venue"
    assert hl_features["spread_bps"] is not None
    assert hl_features["micro_minus_mid"] is not None
    assert hl_features["signed_vol_30s"] is not None
    assert kraken_features["qimb_best"] is not None, "full-L2 venues keep the full library"
    assert kraken_features["dwp_minus_mid"] is not None


def test_bbo_drives_touch_features_and_the_slow_book_never_overrides_it() -> None:
    """On a BBO venue the fast touch is authoritative: a stale l2Book
    snapshot arriving afterwards must not overwrite the mid or the spread
    with 5-second-old prices."""
    engine = FeatureEngine("hyperliquid", "BTC")
    ts = BASE_NS
    engine.on_event(
        StreamEvent(
            "hyperliquid",
            "BTC",
            ts,
            None,
            None,
            None,
            bbo=Bbo(
                best_bid=100.0,
                bid_qty=3.0,
                best_ask=100.5,
                ask_qty=1.0,
                mid=100.25,
                microprice=100.375,
                bid_n=5,
                ask_n=2,
            ),
        )
    )
    from_bbo = engine.compute(ts + 1_000_000)
    assert from_bbo["spread_abs"] == 0.5
    assert from_bbo["micro_minus_mid"] == 100.375 - 100.25
    assert from_bbo["qimb_best"] == (3.0 - 1.0) / 4.0

    # A stale, far-off book snapshot arrives; touch features must not move.
    engine.on_event(_book_event("hyperliquid", ts + 2_000_000))
    after_book = engine.compute(ts + 3_000_000)
    assert after_book["spread_abs"] == 0.5, "the slow book must not override the touch"
    assert after_book["micro_minus_mid"] == from_bbo["micro_minus_mid"]


def test_undeclared_venue_cannot_even_construct_an_engine() -> None:
    with pytest.raises(UnsupportedFeatureError):
        FeatureEngine("undeclared_venue", "BTC")
