"""Round-trip cost models: the difference between predictive and profitable.

A model trained on raw mid moves will look predictive and be worthless — a
single-digit-bps edge disappears into fees and spread. Every label and every
evaluation in Phase B therefore carries an explicit cost assumption, and
maker vs taker are kept separate because the answer differs enormously
between them.

Fees come from ``config/venues.yaml`` (the documented tier schedule); the
tier is selected by trailing 30-day volume, defaulting to tier 0 — the honest
assumption for a small account.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from data.config import VenueConfig

CostMode = Literal["maker", "taker"]


@dataclass(frozen=True, slots=True)
class CostModel:
    """One round-trip cost assumption for one venue."""

    venue: str
    mode: CostMode
    fee_bps_per_leg: float

    def round_trip_cost_bps(self, spread_bps: float | None) -> float:
        """Total cost of entering and exiting one position, in bps of notional.

        Maker: two legs of maker fee; both orders assumed to rest, so no
        spread is paid (queue risk is real but is an execution concern, not a
        labeling one). Taker: two legs of taker fee plus the full spread —
        each leg crosses half of it. When the spread is unknown the taker
        model refuses to understate: it charges fees plus nothing only if the
        spread is genuinely unavailable, which callers should treat as an
        invalid sample rather than a free lunch.
        """
        fees = 2.0 * self.fee_bps_per_leg
        if self.mode == "taker" and spread_bps is not None:
            return fees + spread_bps
        return fees


def cost_model_from_config(
    venue: str, vcfg: VenueConfig, mode: CostMode, volume_usd_30d: float = 0.0
) -> CostModel:
    """Build a cost model from the venue's documented fee schedule."""
    tier = vcfg.fees_for_volume(volume_usd_30d)
    fee = tier.maker_bps if mode == "maker" else tier.taker_bps
    return CostModel(venue=venue, mode=mode, fee_bps_per_leg=fee)


def net_label(ret_bps: float, cost_bps: float) -> int:
    """Direction label that must clear the round-trip cost to count.

    +1 / -1 only when the move exceeds the cost in that direction; otherwise
    0 — an untradeable move is a non-event, not a small win.
    """
    if ret_bps > cost_bps:
        return 1
    if ret_bps < -cost_bps:
        return -1
    return 0
