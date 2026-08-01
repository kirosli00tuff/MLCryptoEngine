"""Evaluation metrics: predictive quality and, separately, tradeability.

Hit rate and AUC measure whether the model knows anything; expected value
per prediction net of assumed cost measures whether that knowledge survives
fees and spread. They are reported side by side per horizon and per cost
assumption because the second routinely dies while the first looks healthy.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import roc_auc_score


def hit_rate(pred_sign: NDArray[np.float64], realized_ret_bps: NDArray[np.float64]) -> float | None:
    """Fraction of non-zero predictions whose sign matched the realized move.

    Secondary diagnostic only: a high hit rate with tiny wins and large
    losses is still a losing strategy — expectancy is the primary number.
    """
    traded = pred_sign != 0
    if not bool(traded.any()):
        return None
    return float((np.sign(realized_ret_bps[traded]) == pred_sign[traded]).mean())


def auc(y_true_binary: NDArray[np.int64], scores: NDArray[np.float64]) -> float | None:
    """ROC AUC; None when the test window contains a single class."""
    if len(set(y_true_binary.tolist())) < 2:
        return None
    return float(roc_auc_score(y_true_binary, scores))


def calibration_bins(
    y_true_binary: NDArray[np.int64],
    prob: NDArray[np.float64],
    n_bins: int = 10,
) -> list[dict[str, float]]:
    """Predicted-vs-observed frequency per probability bin (reliability curve)."""
    out: list[dict[str, float]] = []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for lo, hi in pairwise(edges):
        mask = (prob >= lo) & (prob < hi) if hi < 1.0 else (prob >= lo) & (prob <= hi)
        if not bool(mask.any()):
            continue
        out.append(
            {
                "bin_low": float(lo),
                "bin_high": float(hi),
                "mean_predicted": float(prob[mask].mean()),
                "observed_rate": float(y_true_binary[mask].mean()),
                "count": float(mask.sum()),
            }
        )
    return out


def expected_value_bps(
    pred_sign: NDArray[np.float64],
    realized_ret_bps: NDArray[np.float64],
    cost_bps: NDArray[np.float64] | float,
) -> float | None:
    """Mean net P&L per *prediction that trades*, in bps: sign·move - cost."""
    traded = pred_sign != 0
    if not bool(traded.any()):
        return None
    costs = np.broadcast_to(np.asarray(cost_bps, dtype=np.float64), pred_sign.shape)
    pnl = pred_sign[traded] * realized_ret_bps[traded] - costs[traded]
    return float(pnl.mean())


def feature_importances(model: Any, names: list[str]) -> dict[str, float]:
    """Importances by feature name, descending; empty when unsupported."""
    values = getattr(model, "feature_importances_", None)
    if values is None:
        return {}
    total = float(np.sum(values)) or 1.0
    pairs = sorted(zip(names, values, strict=True), key=lambda kv: -float(kv[1]))
    return {name: float(value) / total for name, value in pairs}
