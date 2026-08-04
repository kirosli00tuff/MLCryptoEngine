"""The three ways this trade breaks, measured rather than listed.

Every carry write-up names these risks. Naming them is cheap and tells an
operator nothing about whether to take the trade, so each one here is reduced
to a number from the sample:

**Funding flips negative while you are in.** Measured as the worst realised
episode: how deep, how long, what it cost to sit through, and — the decision
that actually has to be made — whether sitting through it beat exiting and
re-entering, given that a round trip costs 83 bps with the spot leg dominating.

**Basis risk.** The legs sit on different venues and do not move identically.
Measured from Hyperliquid's own mark-to-index premium: the distribution of
moves and the worst adverse one, priced on a stated position.

**Liquidation of the perp leg.** The tail risk that matters, because a
liquidated short does not merely lose money — it converts a delta-neutral
position into an unhedged long, at the exact moment the market is running
away. Measured as how often the sample's price path would have breached a
stated maintenance level.

What cannot be measured is stated as such rather than omitted: protocol
failure, venue insolvency, withdrawal freezes and oracle manipulation have no
frequency in a three-year price series, and a backtest that ignores them is
not conservative, it is silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from research.carry.funding import NegativeRun
from research.carry.trade import BPS, CarryConfig

# Hyperliquid liquidates at a maintenance level of half the initial margin
# requirement. Stated rather than derived, because the venue can change it.
MAINTENANCE_FRACTION = 0.5


@dataclass
class NegativeFundingRisk:
    """The worst realised episode of paying instead of collecting."""

    episodes: int
    worst_cost: float
    worst_days: float
    worst_start: str
    longest_days: float
    longest_cost: float
    hold_cost: float
    exit_reenter_cost: float

    @property
    def holding_was_cheaper(self) -> bool:
        return self.hold_cost <= self.exit_reenter_cost

    def summary(self) -> dict[str, Any]:
        return {
            "episodes": self.episodes,
            "worst_episode_start": self.worst_start,
            "worst_episode_days": round(self.worst_days, 1),
            "worst_episode_cost_pct_of_notional": round(100 * self.worst_cost, 2),
            "longest_episode_days": round(self.longest_days, 1),
            "longest_episode_cost_pct": round(100 * self.longest_cost, 2),
            "cost_of_holding_through_worst_pct": round(100 * self.hold_cost, 3),
            "cost_of_exiting_and_reentering_pct": round(100 * self.exit_reenter_cost, 3),
            "cheaper_action": "hold" if self.holding_was_cheaper else "exit and re-enter",
        }


def negative_funding_risk(
    runs: list[NegativeRun], config: CarryConfig | None = None
) -> NegativeFundingRisk | None:
    """Worst negative-funding episode, and whether it was worth exiting.

    The comparison is the one an operator actually faces: keep paying funding,
    or pay a full round trip on both legs to step out and back in. That round
    trip is 2 x (spot + perp) per side, dominated by the 40 bps spot leg — so
    the bar for exiting is high, and where the answer is "hold" that is itself
    the finding.
    """
    if not runs:
        return None
    cfg = config or CarryConfig()
    worst = min(runs, key=lambda r: r.cost)
    longest = max(runs, key=lambda r: r.hours)
    round_trip = 2.0 * (cfg.spot_cost_bps_per_side + cfg.perp_cost_bps_per_side) * BPS
    return NegativeFundingRisk(
        episodes=len(runs),
        worst_cost=worst.cost,
        worst_days=worst.hours / 24,
        worst_start=worst.start_date,
        longest_days=longest.hours / 24,
        longest_cost=longest.cost,
        hold_cost=abs(worst.cost),
        exit_reenter_cost=round_trip,
    )


def basis_risk(premium: np.ndarray, notional: float = 10_000.0) -> dict[str, Any]:
    """Distribution of the perp-to-index premium and its worst adverse move.

    A short-perp carry is hurt when the premium *widens* — the perp gets more
    expensive relative to the index the spot leg tracks — so the adverse tail
    is the upper one. Reported on a stated position size, because a percentage
    move means nothing until it is priced.
    """
    clean = premium[np.isfinite(premium)]
    if clean.size < 100:
        return {"error": f"only {clean.size} premium observations"}
    changes = np.diff(clean)
    worst_widening = float(np.max(changes))
    worst_narrowing = float(np.min(changes))
    return {
        "observations": int(clean.size),
        "premium_mean_bps": round(1e4 * float(clean.mean()), 2),
        "premium_p1_bps": round(1e4 * float(np.percentile(clean, 1)), 2),
        "premium_p99_bps": round(1e4 * float(np.percentile(clean, 99)), 2),
        "premium_max_bps": round(1e4 * float(clean.max()), 2),
        "premium_min_bps": round(1e4 * float(clean.min()), 2),
        "hourly_move_p99_bps": round(1e4 * float(np.percentile(np.abs(changes), 99)), 2),
        "worst_adverse_hourly_move_bps": round(1e4 * worst_widening, 2),
        "worst_adverse_move_cost_usd": round(worst_widening * notional, 2),
        "worst_favourable_hourly_move_bps": round(1e4 * worst_narrowing, 2),
        "note": (
            "Adverse for a short perp is a WIDENING premium. Measured against "
            "Hyperliquid's own index, not against Kraken or Coinbase spot, so it "
            "understates the true cross-venue basis by whatever the index and the "
            "actual long venue differ by."
        ),
    }


def liquidation_risk(
    prices: np.ndarray, config: CarryConfig | None = None, rebalance_band: float | None = None
) -> dict[str, Any]:
    """How often the sample's path would have breached the maintenance level.

    The short leg is liquidated when price rises far enough against it. With a
    margin fraction *m*, the initial buffer is *m* of notional and the venue
    liquidates once :data:`MAINTENANCE_FRACTION` of it is gone — so the breach
    threshold is a rise of ``m * MAINTENANCE_FRACTION`` above the price the
    position is currently carried at.

    Measured deliberately **without** crediting spot-leg gains as margin. Those
    gains sit on another venue, and moving them across in time to rescue a
    position is exactly the operational assumption a backtest cannot make good
    on. The frequency here is therefore the one facing an operator who cannot
    top up within minutes.
    """
    cfg = config or CarryConfig()
    band = rebalance_band if rebalance_band is not None else cfg.rebalance_band
    if prices.size < 24:
        return {"error": "too few prices"}

    threshold = cfg.margin_fraction * MAINTENANCE_FRACTION
    entry = float(prices[0])
    breaches = 0
    worst_excursion = 0.0
    for i in range(1, prices.size):
        rise = (float(prices[i]) - entry) / entry
        worst_excursion = max(worst_excursion, rise)
        if rise >= threshold:
            breaches += 1
            entry = float(prices[i])  # liquidated, re-established at the worst price
        elif abs(rise) > band:
            entry = float(prices[i])  # a rebalance resets the carried reference
    return {
        "margin_fraction": cfg.margin_fraction,
        "maintenance_fraction_of_initial": MAINTENANCE_FRACTION,
        "liquidation_threshold_pct_rise": round(100 * threshold, 1),
        "rebalance_band_pct": round(100 * band, 1),
        "breaches": breaches,
        "worst_adverse_excursion_pct": round(100 * worst_excursion, 2),
        "note": (
            "Counted without crediting spot-leg gains as perp margin: that "
            "collateral sits on another venue, and moving it in time is an "
            "operational assumption a backtest cannot validate."
        ),
    }


def leverage_sweep(
    prices: np.ndarray, margins: tuple[float, ...] = (1.0, 0.5, 0.25, 0.2, 0.1)
) -> list[dict[str, Any]]:
    """Liquidation frequency and capital cost across margin levels.

    The two move in opposite directions, and that trade-off is the whole design
    decision: less margin means less capital deployed and a higher return on
    it, and a closer liquidation threshold.
    """
    out = []
    for margin in margins:
        cfg = CarryConfig(margin_fraction=margin)
        risk = liquidation_risk(prices, cfg)
        out.append(
            {
                "margin_fraction": margin,
                "leverage": round(1.0 / margin, 1),
                "capital_per_notional": round(cfg.capital_multiple, 2),
                "liquidation_threshold_pct": risk.get("liquidation_threshold_pct_rise"),
                "breaches": risk.get("breaches"),
            }
        )
    return out


def unmodellable_risks() -> list[str]:
    """Risks with no frequency in any price series. Stated, never omitted."""
    return [
        "Protocol failure or exploit on Hyperliquid — a chain-level or contract-level "
        "loss has no analogue in three years of price history.",
        "Venue insolvency or withdrawal freeze on either leg. FTX in November 2022 sits "
        "inside the Binance sample used for the decay analysis and outside the "
        "Hyperliquid sample entirely.",
        "Oracle or index manipulation moving the mark against the short with no "
        "corresponding move in the spot leg.",
        "Operational failure by a solo operator: two venues, two sets of credentials, a "
        "rebalance that may fall due while asleep, and no second pair of hands.",
        "Regulatory change closing Canadian access to Hyperliquid, which would strand "
        "the only leg of this trade that can be short.",
    ]


def stamp(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")
