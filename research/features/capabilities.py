"""Feature capability matrix: which features each venue's feed can honestly support.

A snapshot-stream feed (Hyperliquid: full l2Book every ~0.5 s minimum, bbo
only on top-of-book change) cannot support order-flow imbalance, queue
imbalance, depth ladders, or book slope at meaningful resolution — computing
them from snapshot deltas produces garbage that looks like data. This module
is the single authority the feature pipeline consults: unsupported features
are nulled per venue, and *requesting* one explicitly raises rather than
returning a value.

Venues absent from the matrix raise too — an undeclared venue is never
credited with capabilities, the same defaults-closed rule the integrity
scoring uses (Stage 1.6).

Feature names are string literals here (not imported from the engine) to
keep this module import-cycle-free; ``tests/test_capabilities.py`` asserts
they stay in exact correspondence with ``FEATURE_COLUMNS``.
"""

from __future__ import annotations


class UnsupportedFeatureError(ValueError):
    """A feature was requested for a venue whose feed cannot support it."""


# Features that require incremental L2 depth (per-update book deltas).
DEPTH_FEATURES: frozenset[str] = frozenset(
    {
        "ofi_best_1s",
        "ofi_best_5s",
        "ofi_deep_1s",
        "ofi_deep_5s",
        "qimb_best",
        "depth_bid_1",
        "depth_bid_2",
        "depth_bid_3",
        "depth_bid_4",
        "depth_bid_5",
        "depth_ask_1",
        "depth_ask_2",
        "depth_ask_3",
        "depth_ask_4",
        "depth_ask_5",
        "slope_bid",
        "slope_ask",
        "book_asym",
        "dwp_minus_mid",
    }
)

# BBO/mid-derived, trade-derived, and cross-venue features — computable from
# any feed with a best bid/offer, a mid, and a trade stream.
BBO_AND_TRADE_FEATURES: frozenset[str] = frozenset(
    {
        "micro_minus_mid",
        "spread_abs",
        "spread_bps",
        "signed_vol_1s",
        "signed_vol_5s",
        "signed_vol_30s",
        "trade_count_5s",
        "interarrival_mean_ms",
        "interarrival_std_ms",
        "vwap_minus_mid_5s",
        "time_since_trade_ms",
        "rvol_1s",
        "rvol_5s",
        "rvol_30s",
        "ret_1s",
        "abs_ret_1s",
        "xv_mid_diff_bps",
        "xv_diff_z",
        "xv_leadlag_m500",
        "xv_leadlag_m100",
        "xv_leadlag_0",
        "xv_leadlag_p100",
        "xv_leadlag_p500",
    }
)

ALL_FEATURES: frozenset[str] = DEPTH_FEATURES | BBO_AND_TRADE_FEATURES

CAPABILITIES: dict[str, frozenset[str]] = {
    # Incremental L2 feeds: full library.
    "kraken": ALL_FEATURES,
    "coinbase": ALL_FEATURES,
    # Databento MBP-10 is true incremental depth: full library.
    "cme": ALL_FEATURES,
    # Snapshot stream: spread, microprice, and BBO/trade-derived only.
    "hyperliquid": BBO_AND_TRADE_FEATURES,
}


def supported_features(venue: str) -> frozenset[str]:
    """The features this venue's feed can support; raises for undeclared venues."""
    try:
        return CAPABILITIES[venue]
    except KeyError:
        raise UnsupportedFeatureError(
            f"venue '{venue}' has no declared capability set — declare it in "
            "research/features/capabilities.py; undeclared venues are never "
            "credited with capabilities"
        ) from None


def require_supported(venue: str, feature: str) -> None:
    """Raise unless ``feature`` is computable from ``venue``'s feed."""
    if feature not in ALL_FEATURES:
        raise UnsupportedFeatureError(f"unknown feature '{feature}'")
    if feature not in supported_features(venue):
        raise UnsupportedFeatureError(
            f"feature '{feature}' is not supported on venue '{venue}': its feed "
            "cannot provide the inputs at meaningful resolution (see the "
            "capability matrix in research/features/capabilities.py)"
        )
