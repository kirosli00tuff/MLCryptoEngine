"""Spread, signal, and the number the stage is actually about.

The signal is deliberately dull: a rolling hedge ratio, a z-score against the
spread's own trailing distribution, enter at two sigma, exit at zero, give up
after thirty days. Every constant is fixed before the first run and none is
searched. A parameter sweep over a pipeline nobody has validated does not find
the edge, it finds the leak — and it would additionally be an uncounted
multiple-testing dimension stacked on top of the 1,653 already being corrected.

**Break-even transaction cost is the output, not return.** A pair returning 20%
a year that stops being profitable above 5 bps per round trip is unreachable
from every venue in this project; one returning 8% that survives to 200 bps is
tradeable everywhere, Kraken spot at its punitive 40 bps maker included. So the
ranking is by break-even cost and the return columns are context.

Cost convention, stated once because everything downstream depends on it: gross
exposure is normalised to one unit across both legs, so entering transacts one
unit one-way and exiting transacts another. ``cost_bps`` is therefore a
*round-trip* rate on one unit of gross capital — 3.0 bps at Hyperliquid maker
(1.5 per side, matching C.9) and 80.0 bps at Kraken base-tier spot maker (40
per side, config/venues.yaml as corrected 2026-08-01).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from research.pairs.cointegration import rolling_hedge_ratios

# Fixed a priori. Not tuned, not swept, not chosen after seeing results.
BETA_WINDOW = 90
Z_WINDOW = 60
ENTRY_Z = 2.0
EXIT_Z = 0.0
MAX_HOLD_BARS = 30
BARS_PER_YEAR = 365.0

# Round-trip cost on one unit of gross capital, both legs included.
HYPERLIQUID_MAKER_BPS = 3.0
KRAKEN_SPOT_MAKER_BPS = 80.0
BPS = 1e-4


@dataclass
class PairBacktest:
    """One pair traded over one out-of-sample stretch."""

    left: str
    right: str
    bars: int
    years: float
    gross_return: float
    daily_returns: np.ndarray
    one_way_turns: float
    trades: int
    executable: bool = False

    @property
    def round_trips(self) -> float:
        return self.one_way_turns / 2.0

    @property
    def round_trips_per_year(self) -> float:
        return self.round_trips / self.years if self.years > 0 else 0.0

    @property
    def gross_annual(self) -> float:
        return self.gross_return / self.years if self.years > 0 else 0.0

    def cost_fraction(self, cost_bps: float) -> float:
        """Total cost over the sample as a fraction of deployed capital."""
        return self.one_way_turns * (cost_bps / 2.0) * BPS

    def net_return(self, cost_bps: float) -> float:
        return self.gross_return - self.cost_fraction(cost_bps)

    def net_annual(self, cost_bps: float) -> float:
        return self.net_return(cost_bps) / self.years if self.years > 0 else 0.0

    @property
    def break_even_bps(self) -> float:
        """Round-trip cost in bps at which this pair stops being profitable.

        Zero when the pair loses money before any cost is charged: a losing
        strategy has no cost at which it becomes profitable, and a negative
        break-even would invite being read as a threshold.
        """
        if self.one_way_turns <= 0.0 or self.gross_return <= 0.0:
            return 0.0
        return 2.0 * self.gross_return / (self.one_way_turns * BPS)

    def sharpe(self) -> float:
        """Annualised Sharpe of the gross daily series, zero risk-free."""
        if self.daily_returns.size < 2:
            return 0.0
        sigma = float(np.std(self.daily_returns, ddof=1))
        if sigma == 0.0:
            return 0.0
        return float(np.mean(self.daily_returns)) / sigma * math.sqrt(BARS_PER_YEAR)

    def net_sharpe(self, cost_bps: float) -> float:
        if self.daily_returns.size < 2:
            return 0.0
        drag = self.cost_fraction(cost_bps) / self.daily_returns.size
        net = self.daily_returns - drag
        sigma = float(np.std(net, ddof=1))
        if sigma == 0.0:
            return 0.0
        return float(np.mean(net)) / sigma * math.sqrt(BARS_PER_YEAR)

    def row(self) -> dict[str, Any]:
        return {
            "pair": f"{self.left}/{self.right}",
            "executable_hyperliquid": self.executable,
            "bars": self.bars,
            "years": round(self.years, 2),
            "trades": self.trades,
            "round_trips_per_year": round(self.round_trips_per_year, 1),
            "gross_annual_pct": round(100 * self.gross_annual, 2),
            "net_annual_hyperliquid_pct": round(100 * self.net_annual(HYPERLIQUID_MAKER_BPS), 2),
            "net_annual_kraken_spot_pct": round(100 * self.net_annual(KRAKEN_SPOT_MAKER_BPS), 2),
            "break_even_bps": round(self.break_even_bps, 1),
            "gross_sharpe": round(self.sharpe(), 2),
            "net_sharpe_hyperliquid": round(self.net_sharpe(HYPERLIQUID_MAKER_BPS), 2),
        }


def zscores(spread: np.ndarray, window: int) -> np.ndarray:
    """z of each bar against the ``window`` bars strictly before it.

    Strictly before, so the bar being scored contributes neither its own mean
    nor its own dispersion. Including it is a small leak that flatters every
    entry, because a bar is always less extreme against a window it belongs to
    than against one it does not.
    """
    out = np.full(spread.size, np.nan, dtype=np.float64)
    for i in range(window, spread.size):
        history = spread[i - window : i]
        if not np.all(np.isfinite(history)) or not np.isfinite(spread[i]):
            continue
        sigma = float(np.std(history, ddof=1))
        if sigma <= 0.0:
            continue
        out[i] = (spread[i] - float(np.mean(history))) / sigma
    return out


def positions_from_z(z: np.ndarray, entry: float, exit_at: float, max_hold: int) -> np.ndarray:
    """Position in {-1, 0, +1} per bar, decided from that bar's z only.

    ``+1`` is long the spread (long the left leg, short the right). The value at
    bar ``i`` uses ``z[i]``, itself computed from bars strictly before ``i``, so
    the position is takeable at ``i`` and earns the move from ``i`` to ``i+1``.
    """
    pos = np.zeros(z.size, dtype=np.float64)
    state = 0.0
    held = 0
    for i in range(z.size):
        zi = z[i]
        if not np.isfinite(zi):
            state, held = 0.0, 0
            pos[i] = 0.0
            continue
        if state == 0.0:
            if zi <= -entry:
                state, held = 1.0, 0
            elif zi >= entry:
                state, held = -1.0, 0
        else:
            held += 1
            crossed = (state > 0 and zi >= -exit_at) or (state < 0 and zi <= exit_at)
            if crossed or held >= max_hold:
                state, held = 0.0, 0
        pos[i] = state
    return pos


def run_pair(
    left: str,
    right: str,
    y_close: np.ndarray,
    x_close: np.ndarray,
    start: int = 0,
    beta_window: int = BETA_WINDOW,
    z_window: int = Z_WINDOW,
    entry: float = ENTRY_Z,
    exit_at: float = EXIT_Z,
    max_hold: int = MAX_HOLD_BARS,
) -> PairBacktest | None:
    """Trade one pair from bar ``start`` onward. ``None`` if the series is too short.

    ``y_close``/``x_close`` must already be the overlapping, finite closes for
    this pair. Bars before ``start`` warm the rolling estimators and are never
    scored.
    """
    if y_close.size != x_close.size:
        raise ValueError("legs must be the same length")
    warmup = beta_window + z_window
    if y_close.size <= warmup + 2 or start >= y_close.size - 2:
        return None

    y, x = np.log(y_close), np.log(x_close)
    betas = rolling_hedge_ratios(y, x, beta_window)
    spread = y - betas * x
    z = zscores(spread, z_window)
    pos = positions_from_z(z, entry, exit_at, max_hold)

    simple_y = y_close[1:] / y_close[:-1] - 1.0
    simple_x = x_close[1:] / x_close[:-1] - 1.0
    # Gross exposure normalised to one unit across both legs, so the cost of a
    # one-way turn is a fixed fraction of capital whatever the hedge ratio is.
    scale = 1.0 + np.abs(betas)
    w_y = 1.0 / scale
    w_x = -betas / scale

    held = pos[:-1]
    daily = held * (w_y[:-1] * simple_y + w_x[:-1] * simple_x)
    previous = np.concatenate([[0.0], pos[:-1]])
    turns = np.abs(pos - previous)

    lo = max(start, warmup)
    daily_scored = np.nan_to_num(daily[lo:], nan=0.0)
    turns_scored = turns[lo:-1]
    if daily_scored.size < 2:
        return None
    opened = int(np.sum((pos[lo:-1] != 0.0) & (previous[lo:-1] == 0.0)))

    return PairBacktest(
        left=left,
        right=right,
        bars=int(daily_scored.size),
        years=daily_scored.size / BARS_PER_YEAR,
        gross_return=float(np.sum(daily_scored)),
        daily_returns=daily_scored,
        one_way_turns=float(np.sum(turns_scored)),
        trades=opened,
    )
