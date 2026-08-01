"""Trade signing: aggressor flag where trustworthy, tick rule otherwise.

The signing method is a per-venue decision recorded in ``SIGNING_METHOD`` and
stamped into every experiment log entry, so no result can silently depend on
an assumption about venue flag semantics:

- **kraken** — Kraken WS v2 documents the trade ``side`` as the taker
  (aggressor) side, so the venue flag is used directly; tick rule only as a
  fallback when the flag is missing.
- **coinbase** — Advanced Trade ``market_trades`` side semantics are not
  clearly documented (maker vs taker), so the tick rule is used and the venue
  flag is deliberately ignored.

Tick rule reference: Lee & Ready (1991), "Inferring Trade Direction from
Intraday Data" — uptick +1, downtick -1, zero-tick carries the last sign.
"""

from __future__ import annotations

SIGNING_METHOD: dict[str, str] = {
    "kraken": "venue_flag",
    "coinbase": "tick_rule",
    # Hyperliquid trades carry the taker direction ("B"/"A", normalized to
    # buy/sell by the parser) — documented aggressor flag, used directly.
    "hyperliquid": "venue_flag",
    # Databento GLBX.MDP3 trades carry the aggressor side ('A'sk/'B'id,
    # normalized by the adapter); used directly.
    "cme": "venue_flag",
}


def tick_rule_sign(price: float, prev_price: float | None, prev_sign: int) -> int:
    """Lee-Ready tick rule; 0 only when there is no history at all."""
    if prev_price is None:
        return 0
    if price > prev_price:
        return 1
    if price < prev_price:
        return -1
    return prev_sign


def sign_trade(
    venue: str,
    venue_side: str | None,
    price: float,
    prev_price: float | None,
    prev_sign: int,
) -> int:
    """Signed direction (+1 buyer-initiated, -1 seller-initiated, 0 unknown)."""
    if SIGNING_METHOD.get(venue) == "venue_flag" and venue_side is not None:
        lowered = venue_side.lower()
        if lowered == "buy":
            return 1
        if lowered == "sell":
            return -1
    return tick_rule_sign(price, prev_price, prev_sign)
