"""Cointegration pairs trading: does lower turnover let cost amortise?

Stage C.8 closed directional micro-pattern prediction and C.9 closed spread
capture, both for the same reason — edge per trade below cost per trade. This
package tests the structural response: hold for days instead of milliseconds so
the same cost is spread across a much larger move.

The primary output is not a return. It is the **break-even transaction cost per
pair** — the round-trip cost in basis points at which a pair stops being
profitable — because that, and not the headline return, decides whether any
venue reachable from British Columbia can trade it.
"""

from research.pairs.backtest import PairBacktest, run_pair
from research.pairs.cointegration import EngleGranger, Johansen, engle_granger, johansen
from research.pairs.screening import ScreenResult, persistence, screen
from research.pairs.validation import deflate, walk_forward

__all__ = [
    "EngleGranger",
    "Johansen",
    "PairBacktest",
    "ScreenResult",
    "deflate",
    "engle_granger",
    "johansen",
    "persistence",
    "run_pair",
    "screen",
    "walk_forward",
]
