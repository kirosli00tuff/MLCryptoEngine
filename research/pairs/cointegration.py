"""Engle-Granger and Johansen, estimated only on data that already existed.

Both tests are thin wrappers over statsmodels — the value here is not the
arithmetic but the two disciplines wrapped around it.

**Point in time.** A cointegrating vector fitted on the whole sample and then
traded across that same sample is look-ahead, and it is the single most common
way this strategy produces fictional results. The hedge ratio at bar *t* is
estimated on a window ending strictly before *t*, so a position taken at *t*
could actually have been taken.

**The two tests answer different questions and both are reported.**
Engle-Granger fixes which series is regressed on which, so it is not symmetric:
``coint(y, x)`` and ``coint(x, y)`` give different p-values, and quietly taking
the better of the two doubles the tests actually run while leaving the count
handed to the multiple-testing correction unchanged. This module tests one
fixed orientation, chosen by symbol order, and says so. Johansen is symmetric
and tests the system, which is why it is worth running alongside rather than
instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen

# Johansen critical values come back as an (n, 3) array of 90%/95%/99% columns.
# 95% is the level everything else in this project quotes.
JOHANSEN_95 = 1
# Lag differences in the VECM. One is the conventional default for daily data
# and is fixed rather than searched: searching it across 1,653 pairs would be
# another multiple-testing dimension that nobody counts.
JOHANSEN_LAGS = 1
# No deterministic trend in the cointegrating relation. Two log price series
# that need a time trend to relate are not the relationship this looks for.
JOHANSEN_DET_ORDER = 0
MIN_OBSERVATIONS = 120


@dataclass(frozen=True)
class EngleGranger:
    """Two-step result for one ordered pair."""

    left: str
    right: str
    observations: int
    t_stat: float
    p_value: float
    beta: float
    intercept: float

    @property
    def orientation(self) -> str:
        return f"{self.left}~{self.right}"


@dataclass(frozen=True)
class Johansen:
    """Trace test for one pair, against the null of no cointegration (r=0)."""

    left: str
    right: str
    observations: int
    trace_stat: float
    critical_95: float

    @property
    def rejects_no_cointegration(self) -> bool:
        return self.trace_stat > self.critical_95


def hedge_ratio(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """OLS slope and intercept of ``y`` on ``x`` — the Engle-Granger first step.

    Returned separately from the test so a caller can re-estimate the vector on
    a rolling window without paying for a p-value it will not use.
    """
    if y.size != x.size:
        raise ValueError(f"length mismatch: {y.size} vs {x.size}")
    if y.size < 2:
        raise ValueError("need at least two observations")
    design = np.column_stack([x, np.ones_like(x)])
    solution, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(solution[0]), float(solution[1])


def engle_granger(left: str, right: str, y: np.ndarray, x: np.ndarray) -> EngleGranger | None:
    """Two-step test on log prices. ``None`` when there is too little overlap."""
    if y.size < MIN_OBSERVATIONS or x.size < MIN_OBSERVATIONS:
        return None
    if not (np.all(np.isfinite(y)) and np.all(np.isfinite(x))):
        raise ValueError(f"{left}/{right}: non-finite prices reached the cointegration test")
    t_stat, p_value, _ = coint(y, x, trend="c", autolag="aic")
    beta, intercept = hedge_ratio(y, x)
    return EngleGranger(
        left=left,
        right=right,
        observations=int(y.size),
        t_stat=float(t_stat),
        p_value=float(p_value),
        beta=beta,
        intercept=intercept,
    )


def johansen(left: str, right: str, y: np.ndarray, x: np.ndarray) -> Johansen | None:
    """Trace test at r=0 on the two-series system. ``None`` on short overlap."""
    if y.size < MIN_OBSERVATIONS or x.size < MIN_OBSERVATIONS:
        return None
    result = coint_johansen(np.column_stack([y, x]), JOHANSEN_DET_ORDER, JOHANSEN_LAGS)
    return Johansen(
        left=left,
        right=right,
        observations=int(y.size),
        trace_stat=float(result.lr1[0]),
        critical_95=float(result.cvt[0][JOHANSEN_95]),
    )


def rolling_hedge_ratios(y: np.ndarray, x: np.ndarray, window: int) -> np.ndarray:
    """Hedge ratio at each bar, fitted on the ``window`` bars strictly before it.

    ``out[i]`` uses ``[i-window, i)`` and is therefore usable at bar ``i``.
    Bars without a full preceding window are NaN rather than fitted on a short
    one: a beta estimated on fifteen observations is not a smaller version of
    the right answer, it is noise with a number attached.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    out = np.full(y.size, np.nan, dtype=np.float64)
    for i in range(window, y.size):
        beta, _ = hedge_ratio(y[i - window : i], x[i - window : i])
        out[i] = beta
    return out
