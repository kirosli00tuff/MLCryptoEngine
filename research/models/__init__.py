"""Baselines, LightGBM defaults, and cost-aware evaluation."""

from research.models.baselines import LastSignBaseline, ZeroBaseline
from research.models.evaluate import (
    auc,
    calibration_bins,
    expected_value_bps,
    feature_importances,
    hit_rate,
)
from research.models.lgbm import DEFAULT_PARAMS, make_classifier, make_regressor

__all__ = [
    "DEFAULT_PARAMS",
    "LastSignBaseline",
    "ZeroBaseline",
    "auc",
    "calibration_bins",
    "expected_value_bps",
    "feature_importances",
    "hit_rate",
    "make_classifier",
    "make_regressor",
]
