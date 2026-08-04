"""The whole trade: long spot on one venue, short perp on another.

The Canadian structure is not optional and it is not symmetric. Kraken and
Coinbase offer spot only — no margin, no derivatives — so the long leg sits
there at 40 bps maker, while the short leg has to be a Hyperliquid perp at 1.5
bps maker. **A carry position is therefore always a cross-venue position**, and
three consequences follow that a single-venue model would miss.

**Rebalance on the cheap leg.** Price drift breaks the delta match, and
restoring it means trading. Trading the spot leg costs 27x what trading the
perp leg costs, so every rebalance adjusts the perp. This is not an
optimisation, it is the only affordable choice, and it is why rebalancing turns
out not to dominate the cost stack.

**Capital sits on both venues.** The spot leg consumes its full notional; the
perp leg consumes margin on top. Return on notional and return on deployed
capital therefore differ by ``1 + margin_fraction``, which at the low leverage
a liquidation-averse operator actually wants is a factor of 1.5 to 2.
Reporting return on notional would overstate the result by that factor, so
this module reports on capital.

**Funding accrues on the perp notional, which moves.** A short that was $10,000
when opened is $12,000 after a 20% rally, so the funding collected — and the
rebalancing needed — both scale with price. Fixing the notional at entry would
quietly misstate both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

BPS = 1e-4
HOURS_PER_YEAR = 24 * 365

# Hyperliquid maker, per side (C.9 measured the round trip at 3.0 bps).
PERP_COST_BPS_PER_SIDE = 1.5
# Kraken base-tier spot maker, per side, as corrected 2026-08-01 in
# config/venues.yaml. Coinbase's base tier is the same 40 bps.
SPOT_COST_BPS_PER_SIDE = 40.0
# Rebalance when the two legs' notionals diverge by more than this.
DEFAULT_BAND = 0.02
# Margin as a fraction of perp notional. 0.5 is 2x leverage — deliberately
# conservative, because the tail risk here is liquidation of the hedge leg.
DEFAULT_MARGIN_FRACTION = 0.5


@dataclass(frozen=True)
class CarryConfig:
    """Every cost and sizing assumption in one place, all stated."""

    perp_cost_bps_per_side: float = PERP_COST_BPS_PER_SIDE
    spot_cost_bps_per_side: float = SPOT_COST_BPS_PER_SIDE
    rebalance_band: float = DEFAULT_BAND
    margin_fraction: float = DEFAULT_MARGIN_FRACTION
    # Resize BOTH legs back to the target notional when they drift outside the
    # band. This is what "rebalancing" means in a carry trade: not restoring
    # delta (equal units are already delta-flat) but stopping the position —
    # and with it the margin requirement — from growing without limit as price
    # rises. It is the expensive kind, because trimming the spot leg costs 40
    # bps a side. Off means buy-and-hold, which needs unbounded capital.
    reset_to_target: bool = True

    @property
    def capital_multiple(self) -> float:
        """Deployed capital per unit of notional: spot in full, plus perp margin."""
        return 1.0 + self.margin_fraction

    def describe(self) -> dict[str, Any]:
        return {
            "spot_leg": (
                f"long spot, {self.spot_cost_bps_per_side} bps/side "
                "(Kraken/Coinbase base-tier maker)"
            ),
            "perp_leg": (f"short perp, {self.perp_cost_bps_per_side} bps/side (Hyperliquid maker)"),
            "rebalance_band": self.rebalance_band,
            "rebalanced_leg": "perp only — the spot leg costs 27x as much to trade",
            "margin_fraction": self.margin_fraction,
            "capital_per_unit_notional_at_entry": self.capital_multiple,
            "policy": (
                "resize both legs to target notional outside the band"
                if self.reset_to_target
                else "buy and hold, never resized"
            ),
        }


@dataclass
class CarryResult:
    """One instrument's simulated carry over the whole available sample."""

    coin: str
    hours: int
    years: float
    notional: float
    mean_notional: float
    deployed_capital: float
    peak_margin_need: float
    funding_collected: float
    price_pnl: float
    entry_cost: float
    exit_cost: float
    rebalance_cost: float
    rebalances: int
    equity_curve: np.ndarray
    config: CarryConfig

    @property
    def total_cost(self) -> float:
        return self.entry_cost + self.exit_cost + self.rebalance_cost

    @property
    def net_profit(self) -> float:
        return self.funding_collected + self.price_pnl - self.total_cost

    @property
    def return_on_capital(self) -> float:
        return self.net_profit / self.deployed_capital if self.deployed_capital else 0.0

    @property
    def return_on_notional(self) -> float:
        return self.net_profit / self.notional if self.notional else 0.0

    @property
    def annualised_on_capital(self) -> float:
        return self.return_on_capital / self.years if self.years > 0 else 0.0

    @property
    def gross_annualised_on_capital(self) -> float:
        """Funding only, before costs and before price P&L.

        This is the number a naive carry study reports; it is kept so the gap
        to the net figure beside it stays visible.
        """
        if self.deployed_capital <= 0 or self.years <= 0:
            return 0.0
        return self.funding_collected / self.deployed_capital / self.years

    @property
    def max_drawdown(self) -> float:
        """Worst peak-to-trough of the equity curve, as a fraction of capital."""
        if self.equity_curve.size == 0:
            return 0.0
        peak = np.maximum.accumulate(self.equity_curve)
        return float(np.min((self.equity_curve - peak) / self.deployed_capital))

    def row(self) -> dict[str, Any]:
        return {
            "coin": self.coin,
            "years": round(self.years, 2),
            "gross_funding_pct_of_capital_pa": round(100 * self.gross_annualised_on_capital, 2),
            "net_pct_of_capital_pa": round(100 * self.annualised_on_capital, 2),
            "net_pct_of_notional_pa": round(
                100 * self.return_on_notional / self.years if self.years else 0.0, 2
            ),
            "capital_per_unit_entry_notional": round(self.deployed_capital / self.notional, 2),
            "peak_margin_pct_of_entry_notional": round(
                100 * self.peak_margin_need / self.notional, 1
            ),
            "funding_yield_on_mean_notional_pa": round(
                100 * self.funding_collected / self.mean_notional / self.years, 2
            )
            if self.years and self.mean_notional
            else 0.0,
            "funding_collected_pct_of_entry_notional": round(
                100 * self.funding_collected / self.notional, 2
            ),
            "price_pnl_pct": round(100 * self.price_pnl / self.notional, 2),
            "entry_exit_cost_pct": round(
                100 * (self.entry_cost + self.exit_cost) / self.notional, 3
            ),
            "rebalance_cost_pct": round(100 * self.rebalance_cost / self.notional, 3),
            "rebalances": self.rebalances,
            "rebalances_per_year": round(self.rebalances / self.years, 1) if self.years else 0.0,
            "max_drawdown_pct_of_capital": round(100 * self.max_drawdown, 2),
        }


def simulate(
    coin: str,
    times_ms: np.ndarray,
    spot: np.ndarray,
    perp: np.ndarray,
    funding: np.ndarray,
    config: CarryConfig | None = None,
    notional: float = 10_000.0,
) -> CarryResult | None:
    """Run the two-leg carry over an aligned hourly series.

    **Equal units on both legs, held for the whole sample.** That is what makes
    the position delta-neutral, and it has a consequence worth stating because
    it is easy to model wrongly: a 1:1 unit hedge does *not* drift out of delta
    as price moves, since both legs scale together. The only thing that moves
    the two apart is a change in the perp's premium to the index, which is
    basis points. Rebalancing is therefore rare here, and a model that charges
    constant rebalancing against price volatility is charging for work the
    structure does not require.

    **What does grow with price is the short's margin requirement.** Funding
    accrues on the perp notional, and that notional rises with the market — but
    so does the short's unrealised loss, drawn from the same margin. Crediting
    the growing funding while holding margin fixed at entry reports a yield
    that would have been liquidated away long before it was collected. So the
    margin account is tracked explicitly, and the capital reported is the
    **peak** requirement over the path: what an operator would actually have
    had to have on the venue to never be liquidated.

    ``funding[i]`` is the rate charged for the interval ending at
    ``times_ms[i]`` and is applied to the notional carried into that interval.
    """
    cfg = config or CarryConfig()
    n = int(times_ms.size)
    if n < 24 or spot.size != n or perp.size != n or funding.size != n:
        return None

    units = notional / float(spot[0])
    perp_entry = float(perp[0])
    initial_margin = notional * cfg.margin_fraction

    entry_cost = notional * (cfg.spot_cost_bps_per_side + cfg.perp_cost_bps_per_side) * BPS
    exit_cost = entry_cost
    rebalance_cost = 0.0
    rebalances = 0
    funding_collected = 0.0
    price_pnl = 0.0
    perp_units = units

    equity = np.empty(n, dtype=np.float64)
    peak_margin_need = initial_margin
    notional_sum = 0.0

    for i in range(1, n):
        spot_price = float(spot[i])
        perp_price = float(perp[i])
        perp_notional = perp_units * perp_price
        notional_sum += perp_notional

        price_pnl += units * (spot_price - float(spot[i - 1]))
        price_pnl -= perp_units * (perp_price - float(perp[i - 1]))
        funding_collected += float(funding[i]) * perp_notional

        # Margin the venue demands, plus the short's unrealised loss, which is
        # drawn from the same account. Funding already collected offsets it.
        unrealised_short_loss = perp_units * (perp_price - perp_entry)
        need = cfg.margin_fraction * perp_notional + unrealised_short_loss - funding_collected
        peak_margin_need = max(peak_margin_need, need)

        drift = (perp_notional - notional) / notional
        if cfg.reset_to_target and abs(drift) > cfg.rebalance_band:
            # Trim (or add to) both legs back to the entry notional. Both legs
            # trade, so the 40 bps spot side dominates the cost — this is the
            # charge a delta-only model misses entirely.
            target_units = notional / perp_price
            traded_perp = abs(target_units - perp_units) * perp_price
            traded_spot = abs(target_units - units) * spot_price
            rebalance_cost += traded_perp * cfg.perp_cost_bps_per_side * BPS
            rebalance_cost += traded_spot * cfg.spot_cost_bps_per_side * BPS
            perp_units = target_units
            units = target_units
            perp_entry = perp_price
            rebalances += 1

        equity[i] = funding_collected + price_pnl - entry_cost - rebalance_cost

    equity[0] = -entry_cost
    # Capital an operator must actually hold: the spot leg in full on one venue,
    # plus the worst margin the perp leg ever demanded on the other.
    deployed_capital = notional + max(peak_margin_need, initial_margin)
    mean_notional = notional_sum / (n - 1) if n > 1 else notional
    equity = equity + deployed_capital

    return CarryResult(
        coin=coin,
        hours=n,
        years=n / HOURS_PER_YEAR,
        notional=notional,
        mean_notional=mean_notional,
        deployed_capital=deployed_capital,
        peak_margin_need=max(peak_margin_need, initial_margin),
        funding_collected=funding_collected,
        price_pnl=price_pnl,
        entry_cost=entry_cost,
        exit_cost=exit_cost,
        rebalance_cost=rebalance_cost,
        rebalances=rebalances,
        equity_curve=equity,
        config=cfg,
    )
