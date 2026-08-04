"""Funding rate carry: income, not prediction.

Four hypotheses closed before this one, all of them predictive in some form.
C.8 needed a model to be right about direction, C.9 needed a quote to be filled
before the market moved, C.10 needed a statistical relationship to persist.
This package tests something structurally different: **a perpetual future
trading above spot pays funding from longs to shorts, and holding long spot
against short perp collects that payment while price exposure cancels.** No
model has to be right about anything.

That is the appeal and it is also the trap. The income is real and mechanical;
the risks are operational and cross-venue, and those are exactly the ones a
backtest is worst at. This package therefore measures the income precisely and
then spends most of its effort on what would take it away.

Almost none of the Phase B research layer is used here. There are no features,
no labels, no model, no cross-validation — a carry trade has nothing to fit.
"""

from research.carry.funding import FundingStats, NegativeRun, characterise, negative_runs
from research.carry.risk import basis_risk, liquidation_risk, unmodellable_risks
from research.carry.trade import CarryConfig, CarryResult, simulate

__all__ = [
    "CarryConfig",
    "CarryResult",
    "FundingStats",
    "NegativeRun",
    "basis_risk",
    "characterise",
    "liquidation_risk",
    "negative_runs",
    "simulate",
    "unmodellable_risks",
]
