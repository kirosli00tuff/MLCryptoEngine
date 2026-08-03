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
:func:`assert_stream_supports` checks that against the channels the venue's
parser actually emits (``data.book.emitted_channels``), so the requirement
can never decay into a docstring promise. As of Stage C.2 the Hyperliquid
parser emits both l2Book and bbo and the check passes; before that it
raised, which is what kept 5.4-second-stale microprice out of the feature
set.

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
        # Queue imbalance and microprice consume the identical inputs — best
        # price and size on both sides — so they classify together. Stage
        # C.1 had queue imbalance under DEPTH by analogy with the depth
        # ladder; the Stage C.2 measurement (bbo carries sz) showed that was
        # wrong, and splitting two features with the same inputs across two
        # categories cannot be defended.
        "qimb_best",
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

# Trade-window features whose window is short enough that a thin contract
# leaves them empty by construction. MBT trades a median of 10.3 s apart
# (measured 2026-07-31), so a 1 s or 5 s trade window holds no trade in the
# large majority of samples: the feature would be a constant zero dressed as
# a measurement.
SHORT_TRADE_WINDOW_FEATURES: frozenset[str] = frozenset(
    {
        "signed_vol_1s",
        "signed_vol_5s",
        "trade_count_5s",
        "vwap_minus_mid_5s",
    }
)

CAPABILITIES: dict[str, frozenset[str]] = {
    # Incremental L2 feeds: full library.
    "kraken": ALL_FEATURES,
    "coinbase": ALL_FEATURES,
    # Databento MBP-10 is true incremental depth. Venue-level default; the
    # contracts differ by ~39x in event rate, so both are pinned explicitly
    # in CONTRACT_CAPABILITIES below and this entry is only a fallback for
    # an unmeasured CME contract.
    "cme": ALL_FEATURES,
    # Snapshot stream: spread, microprice (bbo carries size — verified from
    # recorded data), and BBO/trade-derived features, minus anything binned
    # finer than the measured bbo cadence.
    "hyperliquid": BBO_AND_TRADE_FEATURES - SUB_100MS_FEATURES,
}

# Per-contract overrides. A venue is not always homogeneous: CME MES and MBT
# share a feed, a schema and a clock, and differ by 39x in book rate and
# 319x in trade count. One capability entry for "cme" would credit MBT with
# MES's resolution. Measured 2026-07-31, continuous front month:
#   MES  14,989,106 book updates (198.3/s), p50 0.084 ms, p90 7.8 ms;
#        455,192 trades, p50 interval 26.3 ms  -> full library.
#   MBT     380,358 book updates (5.0/s),  p50 1.273 ms, p90 307 ms;
#          1,426 trades, p50 interval 10,292 ms (10.3 s), longest quiet
#          spell 5.7 h -> short trade windows are empty by construction.
# Re-measured 2026-08-02 on a MID-LIFE front month (2026-07-15, MBTN6 with
# 16 days to expiry) after the first measurement turned out to have been
# taken on MBTN6's expiry day. Corrected numbers over 23.00 h scheduled-open:
#   MES (MESU6)  10,649,955 book updates (128.6/s), p50 0.1 ms, p90 50 ms;
#                360,571 trades, p50 interval 50 ms.
#   MBT (MBTN6)   4,275,234 book updates (51.6/s), p50 0.5 ms, p90 50 ms;
#                 15,933 trades, p50 interval 1,000 ms.
# MES/MBT is 2.49x on book events, not the 39x the expiry day suggested.
# MBT book intervals fall below 100 ms 96.38% of the time, so every
# book-derived feature is supported at every horizon; its trade windows are
# thinner than MES but populated (55.7% of trade gaps < 1 s, 80.2% < 5 s) —
# a quiet market, not an absent one, and a zero there is a true observation.
# Both contracts therefore carry the full library. ADR-018 supersedes ADR-016.
CONTRACT_CAPABILITIES: dict[tuple[str, str], frozenset[str]] = {
    ("cme", "MES"): ALL_FEATURES,
    ("cme", "MBT"): ALL_FEATURES,
}

# Venues whose credited features depend on a channel the parser must supply.
# Maps venue -> the channel that must be present in its event stream.
REQUIRED_CHANNELS: dict[str, str] = {"hyperliquid": "bbo"}


def contract_key(symbol: str) -> str:
    """Contract root of an instrument symbol: ``MESU6``/``MES.c.0`` -> ``MES``.

    Continuous symbology, outright months, and the plain root all resolve to
    the same capability entry, so a roll cannot silently change what a
    contract is credited with.
    """
    root = symbol.split(".", 1)[0]
    # Strip a trailing CME month/year code (e.g. U6, Z25) if present.
    while root and root[-1].isdigit():
        root = root[:-1]
    if len(root) > 3 and root[-1].isalpha():
        root = root[:-1]
    return root


def supported_features(venue: str, symbol: str | None = None) -> frozenset[str]:
    """Features this venue — and, where it matters, this contract — supports.

    A per-contract entry always wins over the venue default: CME MES and MBT
    share a feed but differ by 39x in event rate, so one venue-wide answer
    would credit the thin contract with the liquid one's resolution. Venues
    absent from the matrix raise; a contract absent from
    :data:`CONTRACT_CAPABILITIES` falls back to its venue.
    """
    if symbol is not None:
        specific = CONTRACT_CAPABILITIES.get((venue, contract_key(symbol)))
        if specific is not None:
            return specific
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


def require_supported(venue: str, feature: str, symbol: str | None = None) -> None:
    """Raise unless ``feature`` is computable from this venue/contract's feed."""
    if feature not in ALL_FEATURES:
        raise UnsupportedFeatureError(f"unknown feature '{feature}'")
    if feature not in supported_features(venue, symbol):
        where = f"venue '{venue}'" if symbol is None else f"{venue} contract '{symbol}'"
        raise UnsupportedFeatureError(
            f"feature '{feature}' is not supported on {where}: its feed "
            "cannot provide the inputs at meaningful resolution (see the "
            "capability matrix in research/features/capabilities.py)"
        )
