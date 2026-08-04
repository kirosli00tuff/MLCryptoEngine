"""Walk-forward folds, trade counts, and a Sharpe deflated for the search.

Three things this project has learned to insist on, applied at the pair scale.

**Trade count, not just return.** A Sharpe of 2 computed from twelve trades
over three years is not a strong result with a small sample attached; it is a
number with no statistical power at all. The count sits next to every Sharpe.

**Deflated Sharpe.** Screening 1,653 pairs and reporting the best one is the
exact situation deflation exists to penalise. Bailey & López de Prado (2014):
the expected maximum Sharpe under the null grows with the number of trials, so
a raw Sharpe must clear that bar before it means anything. With trials in the
thousands the bar is high, which is the point.

**Embargo at the holding horizon.** The purged-CV machinery from Stage C.2 was
sized for millisecond label horizons. A pairs position is held for days, so the
embargo must be days too — five orders of magnitude larger. The scaling is
checked rather than assumed, because a horizon silently mishandled would
produce folds that look purged and are not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import norm

from research.pairs.backtest import BARS_PER_YEAR, PairBacktest

NS_PER_DAY = 86_400_000_000_000
EULER_MASCHERONI = 0.5772156649015329
# A fold with fewer scored bars than this cannot support a Sharpe worth
# reporting, so it is dropped rather than averaged in.
MIN_FOLD_BARS = 60


@dataclass(frozen=True)
class Fold:
    """One walk-forward test block."""

    index: int
    start_bar: int
    end_bar: int
    active_bars: int
    gross_return: float
    sharpe: float


def embargo_ns_for_holding(max_hold_bars: int, bar_seconds: int = 86_400) -> int:
    """Embargo in nanoseconds for a position held up to ``max_hold_bars``.

    A position opened inside a test block stays open for up to
    ``max_hold_bars`` afterwards, so training samples in that window share its
    outcome and must be excluded — the same argument as ADR-015's millisecond
    label horizons, five orders of magnitude further out.
    """
    if max_hold_bars < 0:
        raise ValueError("max_hold_bars must be non-negative")
    return max_hold_bars * bar_seconds * 1_000_000_000


def walk_forward(
    result: PairBacktest, test_bars: int, min_fold_bars: int = MIN_FOLD_BARS
) -> list[Fold]:
    """Split a scored series into consecutive test blocks.

    The signal is already point-in-time — every estimator looks strictly
    backwards — so folds partition the out-of-sample stretch rather than
    re-fitting anything. What they answer is whether a result is carried by one
    lucky stretch or holds across several.
    """
    if test_bars < 2:
        raise ValueError("test_bars must be at least 2")
    folds: list[Fold] = []
    daily = result.daily_returns
    for index, lo in enumerate(range(0, daily.size, test_bars)):
        hi = min(lo + test_bars, daily.size)
        block = daily[lo:hi]
        if block.size < min_fold_bars:
            continue
        sigma = float(np.std(block, ddof=1))
        sharpe = float(np.mean(block)) / sigma * math.sqrt(BARS_PER_YEAR) if sigma > 0.0 else 0.0
        folds.append(
            Fold(
                index=index,
                start_bar=lo,
                end_bar=hi,
                active_bars=int(np.count_nonzero(block)),
                gross_return=float(np.sum(block)),
                sharpe=sharpe,
            )
        )
    return folds


def expected_max_sharpe(n_trials: int, sharpe_std: float) -> float:
    """Expected maximum Sharpe across ``n_trials`` independent null strategies.

    The benchmark a screened winner has to beat. With thousands of trials it
    sits well above zero, which is exactly why "our best pair had Sharpe 1.8"
    is not on its own evidence of anything.
    """
    if n_trials < 2 or sharpe_std <= 0.0:
        return 0.0
    a = float(norm.ppf(1.0 - 1.0 / n_trials))
    b = float(norm.ppf(1.0 - 1.0 / (n_trials * math.e)))
    return sharpe_std * ((1.0 - EULER_MASCHERONI) * a + EULER_MASCHERONI * b)


def deflated_sharpe(
    sharpe: float,
    n_obs: int,
    n_trials: int,
    skew: float,
    kurtosis: float,
    sharpe_std: float,
) -> float:
    """Probability the true Sharpe exceeds zero, given the search that found it.

    Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*. Inputs are the
    per-bar (not annualised) Sharpe, the sample length, the number of trials
    searched, and the return distribution's third and fourth moments — non-
    normal returns inflate a naive Sharpe and the correction accounts for it.
    """
    if n_obs < 3:
        return 0.0
    benchmark = expected_max_sharpe(n_trials, sharpe_std)
    denominator = 1.0 - skew * sharpe + 0.25 * (kurtosis - 1.0) * sharpe * sharpe
    if denominator <= 0.0:
        return 0.0
    statistic = (sharpe - benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denominator)
    return float(norm.cdf(statistic))


def deflate(result: PairBacktest, n_trials: int, sharpe_std: float) -> dict[str, Any]:
    """Deflated Sharpe for one backtest, with the inputs that produced it."""
    daily = result.daily_returns
    if daily.size < 3:
        return {"deflated_sharpe": 0.0, "reason": "fewer than 3 scored bars"}
    sigma = float(np.std(daily, ddof=1))
    if sigma <= 0.0:
        return {"deflated_sharpe": 0.0, "reason": "zero variance — never traded"}
    per_bar = float(np.mean(daily)) / sigma
    centred = (daily - float(np.mean(daily))) / sigma
    skew = float(np.mean(centred**3))
    kurtosis = float(np.mean(centred**4))
    return {
        "annualised_sharpe": round(per_bar * math.sqrt(BARS_PER_YEAR), 3),
        "per_bar_sharpe": round(per_bar, 5),
        "trials_searched": n_trials,
        "expected_max_sharpe_under_null_per_bar": round(
            expected_max_sharpe(n_trials, sharpe_std), 5
        ),
        "skew": round(skew, 3),
        "kurtosis": round(kurtosis, 3),
        "observations": int(daily.size),
        "deflated_sharpe": round(
            deflated_sharpe(per_bar, daily.size, n_trials, skew, kurtosis, sharpe_std), 4
        ),
    }


def sharpe_dispersion(results: list[PairBacktest]) -> float:
    """Cross-sectional standard deviation of per-bar Sharpe across trials.

    The deflation benchmark needs to know how much Sharpe varies across the
    strategies actually searched. Measuring it from this study's own pairs
    beats assuming a value; it is the quantity Bailey & Lopez de Prado write as
    sigma-hat of SR.
    """
    values: list[float] = []
    for result in results:
        daily = result.daily_returns
        if daily.size < 3:
            continue
        sigma = float(np.std(daily, ddof=1))
        if sigma > 0.0:
            values.append(float(np.mean(daily)) / sigma)
    if len(values) < 2:
        return 0.0
    return float(np.std(np.asarray(values), ddof=1))
