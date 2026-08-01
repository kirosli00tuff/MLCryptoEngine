"""Feature capability matrix: which features each venue's feed can honestly support.

A snapshot-stream feed (Hyperliquid) cannot support order-flow imbalance,
queue imbalance, depth ladders, or book slope at meaningful resolution —
computing them from snapshot deltas produces garbage that looks like data.
This module is the single authority the feature pipeline consults:
unsupported features are nulled per venue, and *requesting* one explicitly
raises rather than returning a value.

**Measured 2026-08-01 from 242,907 recorded Hyperliquid messages** (Stage
C.2; documented behaviour was wrong in both directions, so these numbers
govern, not the venue docs):

- ``bbo`` DOES carry size at both touches — ``{"px":"62362.0",
  "sz":"13.27152","n":29}`` per side — so microprice is genuinely
  supported. It also fires on size-only changes (164,821 of 171,195
  updates), not only price changes, at p50 123 ms / p90 404 ms per coin.
- ``l2Book`` arrives at **p50 5,387 ms**, not the documented ~0.5 s
  minimum — an order of magnitude slower. Nothing sub-5-second is
  measurable from l2Book alone.

Hence ``SUB_100MS_FEATURES``: 100 ms lead-lag bins against a 123 ms median
update interval leave most bins empty, so those two features are not
supported on Hyperliquid even from bbo.

``BBO_DEPENDENT_FEATURES`` is the load-bearing caveat: every feature
Hyperliquid is credited with needs the bbo channel in the event stream.
``data/book/hyperliquid_parse.py`` currently maps **only l2Book**, so until
bbo is plumbed through, these features would be computed at 5.4 s
resolution. :func:`assert_stream_supports` exists so that plumbing gap
fails loudly instead of silently producing 5-second-stale microprice.

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

# Features whose bin width is finer than Hyperliquid's measured 123 ms median
# bbo interval: most 100 ms bins hold no update, so the correlation is
# computed on a sparse, unrepresentative subsample.
SUB_100MS_FEATURES: frozenset[str] = frozenset({"xv_leadlag_m100", "xv_leadlag_p100"})

# Features that need best-level prices and sizes as they change — i.e. the
# bbo channel, not the 5.4 s l2Book snapshot stream. Crediting a venue with
# these obliges the event stream to actually carry its bbo updates.
BBO_DEPENDENT_FEATURES: frozenset[str] = BBO_AND_TRADE_FEATURES - SUB_100MS_FEATURES

CAPABILITIES: dict[str, frozenset[str]] = {
    # Incremental L2 feeds: full library.
    "kraken": ALL_FEATURES,
    "coinbase": ALL_FEATURES,
    # Databento MBP-10 is true incremental depth: full library.
    "cme": ALL_FEATURES,
    # Snapshot stream: spread, microprice (bbo carries size — verified from
    # recorded data), and BBO/trade-derived features, minus anything binned
    # finer than the measured bbo cadence.
    "hyperliquid": BBO_AND_TRADE_FEATURES - SUB_100MS_FEATURES,
}

# Venues whose credited features depend on a channel the parser must supply.
# Maps venue -> the channel that must be present in its event stream.
REQUIRED_CHANNELS: dict[str, str] = {"hyperliquid": "bbo"}


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


def assert_stream_supports(venue: str, channels_in_stream: frozenset[str]) -> None:
    """Raise unless the event stream carries the channel this venue's features need.

    Hyperliquid's credited features (microprice, spread, returns, realized
    vol) are only honest at bbo resolution — p50 123 ms. Fed l2Book alone
    they would be computed from 5.4 s snapshots: stale by orders of
    magnitude and silently wrong. Any pipeline building features for a venue
    in :data:`REQUIRED_CHANNELS` must call this with the channels its parser
    actually emits.
    """
    required = REQUIRED_CHANNELS.get(venue)
    if required is not None and required not in channels_in_stream:
        raise UnsupportedFeatureError(
            f"venue '{venue}' requires the '{required}' channel in the event stream: "
            f"its credited features are measured at bbo cadence (p50 123 ms), and "
            f"l2Book alone arrives at p50 5,387 ms. Stream carries: "
            f"{sorted(channels_in_stream) or 'nothing'}"
        )


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
