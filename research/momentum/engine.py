"""Time-series momentum on an aligned daily close matrix.

Classic form, deliberately without refinements: at each rebalance every live
asset is scored by its own trailing L-day return and held long if that return
is positive, short if negative, equal weight, gross notional 1.0. No skip
window, no volatility targeting, no cross-sectional rank — each would be a free
parameter beyond the two the registration admits (lookback, holding period).

**Net exposure floats by construction.** When most assets trended up over the
lookback, most weights are long and the book is net long. That is not a bug to
be engineered away; it is the property the beta control exists to measure,
because a floating-net book in a rising market earns beta while looking like it
earns signal.

Two mechanical rules inherited from C.13, for the same reasons:

- **A death mid-hold is a forced exit at the last printed price**, charged one
  side of fees, never a silent disappearance at entry price. Dead coins are
  disproportionately past losers, so momentum is usually *short* them when they
  die — dropping the exit would flatter the strategy.
- **Positions are held in units between rebalances**, so the book drifts with
  price exactly as a real one would rather than being re-weighted daily for
  free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

BPS = 1e-4
DAYS_PER_YEAR = 365
RISK_FREE_ANNUAL = 0.04
# Below this many scoreable assets the book is a handful of coins, not a
# cross-section. Never binds on the C.10 universe (~58 alive throughout);
# exists so a pathological input degrades loudly in the result rather than
# silently concentrating.
MIN_NAMES = 10
# The C.11 convention for splitting up-trending from down-trending markets.
TREND_WINDOW_DAYS = 30


@dataclass(frozen=True)
class Spec:
    """One registered specification: the grid's two free parameters."""

    lookback_days: int
    hold_days: int

    @property
    def key(self) -> str:
        return f"L{self.lookback_days}/H{self.hold_days}"


@dataclass
class MomentumResult:
    """One specification's realised path on gross notional 1.0."""

    spec: Spec
    days_ns: NDArray[np.int64]
    gross_daily: NDArray[np.float64]
    traded_daily: NDArray[np.float64]
    rebalances: int = 0
    forced_exits: int = 0
    thin_rebalances: int = 0
    mean_names: float = 0.0
    mean_net_exposure: float = 0.0

    def net_daily(self, fee_bps_per_side: float) -> NDArray[np.float64]:
        return self.gross_daily - self.traded_daily * fee_bps_per_side * BPS

    @property
    def traded_total(self) -> float:
        return float(self.traded_daily.sum())

    @property
    def gross_pnl(self) -> float:
        return float(self.gross_daily.sum())

    @property
    def years(self) -> float:
        return self.days_ns.size / DAYS_PER_YEAR

    @property
    def annual_turnover_x_gross(self) -> float:
        return self.traded_total / self.years if self.years > 0 else 0.0

    @property
    def round_trips_per_year(self) -> float:
        """A round trip moves 2x notional (in and out)."""
        return self.annual_turnover_x_gross / 2.0

    @property
    def break_even_fee_bps_per_side(self) -> float:
        """Fee per side at which gross profit exactly pays for the trading.

        ADR-032's ranking: it survives venue changes, which per-venue net
        returns do not.
        """
        if self.traded_total <= 0 or self.gross_pnl <= 0:
            return 0.0
        return self.gross_pnl / self.traded_total / BPS


def sharpe(daily: NDArray[np.float64], rf_annual: float = RISK_FREE_ANNUAL) -> float:
    """Annualised Sharpe on daily returns, excess of the stated risk-free rate."""
    if daily.size < 3:
        return 0.0
    sigma = float(np.std(daily, ddof=1))
    if sigma <= 0.0:
        return 0.0
    excess = float(np.mean(daily)) - rf_annual / DAYS_PER_YEAR
    return excess / sigma * float(np.sqrt(DAYS_PER_YEAR))


def max_drawdown(daily: NDArray[np.float64]) -> float:
    """Worst peak-to-trough of the arithmetic equity curve, on gross 1.0."""
    if daily.size == 0:
        return 0.0
    equity = np.cumsum(daily)
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def beta_alpha(
    strategy_daily: NDArray[np.float64], benchmark_daily: NDArray[np.float64]
) -> dict[str, float]:
    """Daily OLS of strategy on benchmark: beta, annualised alpha, alpha t-stat.

    This is the control that decides the stage. A momentum book in a bull
    market is mostly beta; alpha is what survives after the market's own drift
    is charged for.
    """
    n = int(min(strategy_daily.size, benchmark_daily.size))
    s, b = strategy_daily[:n], benchmark_daily[:n]
    var_b = float(np.var(b, ddof=1))
    if n < 30 or var_b <= 0.0:
        return {"beta": 0.0, "alpha_annual": 0.0, "alpha_t": 0.0, "r_squared": 0.0}
    beta = float(np.cov(s, b, ddof=1)[0, 1]) / var_b
    alpha_daily = float(np.mean(s)) - beta * float(np.mean(b))
    residuals = s - (alpha_daily + beta * b)
    s2 = float(np.sum(residuals**2)) / (n - 2)
    mean_b = float(np.mean(b))
    se_alpha = float(np.sqrt(s2 * (1.0 / n + mean_b**2 / ((n - 1) * var_b))))
    total = float(np.sum((s - np.mean(s)) ** 2))
    r_squared = 1.0 - float(np.sum(residuals**2)) / total if total > 0 else 0.0
    return {
        "beta": beta,
        "alpha_annual": alpha_daily * DAYS_PER_YEAR,
        "alpha_t": alpha_daily / se_alpha if se_alpha > 0 else 0.0,
        "r_squared": r_squared,
    }


def up_down_split(
    strategy_daily: NDArray[np.float64], benchmark_closes: NDArray[np.float64]
) -> dict[str, Any]:
    """Strategy return on days the benchmark's trailing 30d trend was up vs down."""
    n = int(min(strategy_daily.size, benchmark_closes.size))
    trend = np.full(n, np.nan)
    for i in range(TREND_WINDOW_DAYS, n):
        past, now = benchmark_closes[i - TREND_WINDOW_DAYS], benchmark_closes[i]
        if np.isfinite(past) and np.isfinite(now) and past > 0:
            trend[i] = now / past - 1.0
    up = np.isfinite(trend) & (trend > 0)
    down = np.isfinite(trend) & (trend <= 0)
    out: dict[str, Any] = {"up_days": int(up.sum()), "down_days": int(down.sum())}
    for name, mask in (("up", up), ("down", down)):
        block = strategy_daily[:n][mask]
        out[f"{name}_annual_return_pct"] = (
            round(100 * float(np.mean(block)) * DAYS_PER_YEAR, 2) if block.size else None
        )
    return out


def simulate(
    dates_ns: NDArray[np.int64],
    closes: NDArray[np.float64],
    spec: Spec,
    gross: float = 1.0,
) -> MomentumResult:
    """Run one specification over the aligned matrix.

    ``closes[r, i]`` is NaN outside symbol ``i``'s life. The signal at row
    ``r`` uses only ``closes[r - L]`` and ``closes[r]`` — nothing later; the
    look-ahead trap test in ``tests/test_momentum.py`` holds this to account
    with an anti-persistent panel that trailing information must lose on.
    """
    n_days, n_sym = closes.shape
    start = spec.lookback_days
    if n_days <= start + 1:
        return MomentumResult(
            spec=spec,
            days_ns=np.empty(0, dtype=np.int64),
            gross_daily=np.empty(0),
            traded_daily=np.empty(0),
        )

    units = np.zeros(n_sym)
    last = np.full(n_sym, np.nan)
    scored = n_days - start
    gross_daily = np.zeros(scored)
    traded_daily = np.zeros(scored)
    result = MomentumResult(
        spec=spec,
        days_ns=dates_ns[start:],
        gross_daily=gross_daily,
        traded_daily=traded_daily,
    )
    names_sum = 0.0
    net_sum = 0.0

    for r in range(start, n_days):
        i = r - start
        price = closes[r]
        finite = np.isfinite(price)
        held = units != 0.0

        # Mark held positions through the day against their carried last price.
        alive = held & finite
        gross_daily[i] += float(np.sum(units[alive] * (price[alive] - last[alive])))

        # A held symbol with no price left is a death: exit at the last print.
        dead = held & ~finite
        if bool(dead.any()):
            traded_daily[i] += float(np.sum(np.abs(units[dead]) * last[dead]))
            result.forced_exits += int(dead.sum())
            units[dead] = 0.0

        last = np.where(finite, price, last)

        if i % spec.hold_days == 0:
            past = closes[r - spec.lookback_days]
            eligible = finite & np.isfinite(past) & (past > 0)
            momentum = np.zeros(n_sym)
            momentum[eligible] = price[eligible] / past[eligible] - 1.0
            signal = np.sign(momentum) * eligible
            n_names = int(np.count_nonzero(signal))
            if n_names < MIN_NAMES:
                result.thin_rebalances += 1
                target = np.zeros(n_sym)
            else:
                target = signal * (gross / n_names)
            current = np.where(units != 0.0, units * np.where(finite, price, last), 0.0)
            traded_daily[i] += float(np.sum(np.abs(target - current)))
            with np.errstate(invalid="ignore", divide="ignore"):
                units = np.where(target != 0.0, target / price, 0.0)
            result.rebalances += 1
            names_sum += n_names
            net_sum += float(np.sum(target))

    # The last position is not free to exit.
    traded_daily[-1] += float(np.sum(np.abs(units) * np.where(np.isfinite(last), last, 0.0)))

    if result.rebalances:
        result.mean_names = names_sum / result.rebalances
        result.mean_net_exposure = net_sum / result.rebalances
    return result


@dataclass
class SpecMetrics:
    """Everything the report says about one grid cell."""

    result: MomentumResult
    rows: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def compute(
        cls,
        result: MomentumResult,
        benchmark_daily: NDArray[np.float64],
        benchmark_closes: NDArray[np.float64],
        fee_scenarios: dict[str, float],
    ) -> SpecMetrics:
        gross = result.gross_daily
        entry: dict[str, Any] = {
            "spec": result.spec.key,
            "lookback_days": result.spec.lookback_days,
            "hold_days": result.spec.hold_days,
            "scored_days": int(gross.size),
            "rebalances": result.rebalances,
            "mean_names": round(result.mean_names, 1),
            "mean_net_exposure": round(result.mean_net_exposure, 3),
            "forced_exits": result.forced_exits,
            "thin_rebalances": result.thin_rebalances,
            "annual_turnover_x_gross": round(result.annual_turnover_x_gross, 2),
            "round_trips_per_year": round(result.round_trips_per_year, 2),
            "gross_annual_return_pct": round(100 * float(np.mean(gross)) * DAYS_PER_YEAR, 2),
            "gross_sharpe": round(sharpe(gross), 3),
            "max_drawdown_pct_of_gross": round(100 * max_drawdown(gross), 2),
            "break_even_fee_bps_per_side": round(result.break_even_fee_bps_per_side, 2),
        }
        for name, fee in fee_scenarios.items():
            net = result.net_daily(fee)
            entry[f"net_annual_return_pct_{name}"] = round(
                100 * float(np.mean(net)) * DAYS_PER_YEAR, 2
            )
            entry[f"net_sharpe_{name}"] = round(sharpe(net), 3)
        entry.update(
            {f"{k}_vs_btc": round(v, 3) for k, v in beta_alpha(gross, benchmark_daily).items()}
        )
        entry["up_down"] = up_down_split(gross, benchmark_closes)
        return cls(result=result, rows=entry)
