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
    """One round-trip cost assumption for one venue.

    Two fee shapes, because two kinds of venue charge differently:

    - **Percentage** (crypto spot): a share of notional. Price-independent,
      so ``fee_bps_per_leg`` is the whole story.
    - **Per contract** (futures): a fixed sum per contract per side. Its cost
      in *basis points* depends on the notional it is charged against, which
      is ``price x contract_multiplier``. A micro contract has small notional,
      so a fee that is negligible on a large contract is not negligible here —
      the same $2.99 round turn is 0.88 bps on MES's ~$34,000 notional and
      ~4.6 bps on MBT's ~$6,500. Reusing one venue's bps figure for another
      contract is the specific error this shape exists to prevent (ADR-023).
    """

    venue: str
    mode: CostMode
    fee_bps_per_leg: float = 0.0
    fee_usd_per_contract_per_side: float | None = None
    contract_multiplier: float | None = None

    def __post_init__(self) -> None:
        if self.fee_usd_per_contract_per_side is not None and self.contract_multiplier is None:
            raise ValueError(
                f"{self.venue}: a per-contract fee needs contract_multiplier to convert "
                "to basis points — notional is price x multiplier, and without it the "
                "fee cannot be expressed as a rate at all"
            )

    @property
    def is_per_contract(self) -> bool:
        """Does this venue charge per contract rather than as a share of notional?"""
        return self.fee_usd_per_contract_per_side is not None

    def fee_bps_per_leg_at(self, price: float | None) -> float:
        """Per-leg fee in bps, converted at ``price`` for per-contract venues.

        Refuses rather than guesses: a per-contract model with no price has
        no notional to divide by, and substituting any default would invent a
        cost that was never charged.
        """
        if not self.is_per_contract:
            return self.fee_bps_per_leg
        if price is None or not price > 0.0:
            raise ValueError(
                f"{self.venue} charges per contract, so its cost in bps depends on the "
                f"notional at the time of the trade; got price={price!r}. Treat a sample "
                "with no usable entry price as invalid rather than pricing it."
            )
        assert self.fee_usd_per_contract_per_side is not None  # narrowed by is_per_contract
        assert self.contract_multiplier is not None  # enforced in __post_init__
        notional = price * self.contract_multiplier
        return self.fee_usd_per_contract_per_side / notional * 1e4

    def round_trip_cost_bps(self, spread_bps: float | None, price: float | None = None) -> float:
        """Total cost of entering and exiting one position, in bps of notional.

        Maker: two legs of maker fee; both orders assumed to rest, so no
        spread is paid (queue risk is real but is an execution concern, not a
        labeling one). Taker: two legs of taker fee plus the full spread —
        each leg crosses half of it. When the spread is unknown the taker
        model refuses to understate: it charges fees plus nothing only if the
        spread is genuinely unavailable, which callers should treat as an
        invalid sample rather than a free lunch.

        CME futures have no maker/taker fee split — the exchange charges the
        same either way — so for a per-contract venue the two modes differ
        only in whether the spread is paid. That is not a technicality: on a
        contract whose touch spread is wider than its fee, the spread is the
        dominant cost, and calling both modes "the fee" would hide it.
        """
        fees = 2.0 * self.fee_bps_per_leg_at(price)
        if self.mode == "taker" and spread_bps is not None:
            return fees + spread_bps
        return fees


def cost_model_from_config(
    venue: str,
    vcfg: VenueConfig,
    mode: CostMode,
    volume_usd_30d: float = 0.0,
    symbol: str | None = None,
) -> CostModel:
    """Build a cost model from the venue's documented fee schedule."""
    tier = vcfg.fees_for_volume(volume_usd_30d)
    if tier.fee_usd_per_contract_per_side is not None:
        meta = vcfg.instruments.get(symbol or "")
        multiplier = meta.contract_multiplier if meta is not None else None
        if multiplier is None:
            raise ValueError(
                f"{venue} {symbol or '(no symbol given)'}: fee is quoted per contract but "
                "no contract_multiplier is declared for this instrument, so notional is "
                "unknown. Declare it in the venue config."
            )
        return CostModel(
            venue=venue,
            mode=mode,
            fee_usd_per_contract_per_side=tier.fee_usd_per_contract_per_side,
            contract_multiplier=multiplier,
        )
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
