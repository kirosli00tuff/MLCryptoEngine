"""Trivial baselines: the bar every real model must clear.

Stated up front to prevent celebrating a coin flip: a model that cannot beat
"never trade" (predict zero) and "momentum of one observation" (sign of the
last return) on net-of-cost expected value has found nothing, whatever its
AUC says.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class ZeroBaseline:
    """Predict 0 always — never trade. Net EV is exactly zero by construction."""

    def fit(self, x: NDArray[np.float64], y: NDArray[np.float64]) -> ZeroBaseline:
        return self

    def predict(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.zeros(len(x), dtype=np.float64)


class LastSignBaseline:
    """Predict the sign of the most recent return (one designated feature column)."""

    def __init__(self, ret_column_index: int) -> None:
        self._index = ret_column_index

    def fit(self, x: NDArray[np.float64], y: NDArray[np.float64]) -> LastSignBaseline:
        return self

    def predict(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.sign(np.nan_to_num(x[:, self._index], nan=0.0))
