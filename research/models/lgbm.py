"""LightGBM baseline models with fixed, sensible defaults.

Deliberately no hyperparameter search at this stage: searching over a leaky
or unproven pipeline just finds the leak. Search earns its place only after
the leakage suite and the pipeline are trusted. Deep learning is out of
scope for Phase B (see ADR: trees before deep learning) — gradient boosted
trees are cheap to train, strong on tabular microstructure features, and
their feature importances are directly inspectable.
"""

from __future__ import annotations

from typing import Any

import lightgbm as lgb

# Fixed defaults, tuned for "small tabular dataset, avoid overfitting", not
# for any observed result. min_child_samples is deliberately high: with tens
# of thousands of samples per day, leaves fitted on a handful of ticks are
# noise by construction.
DEFAULT_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 100,
    "subsample": 0.9,
    "subsample_freq": 1,
    "colsample_bytree": 0.9,
    "verbosity": -1,
    "n_jobs": -1,
    "random_state": 7,
}


def make_classifier(**overrides: Any) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(**{**DEFAULT_PARAMS, **overrides})


def make_regressor(**overrides: Any) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(**{**DEFAULT_PARAMS, **overrides})
