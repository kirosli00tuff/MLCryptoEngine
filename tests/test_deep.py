"""Tests for the C.14 deep-learning path.

**These skip under ``.venv``**, where ``make test`` runs and torch is not
installed. Torch lives in ``.venv-dl`` because the three live recorders execute
out of ``.venv`` and a ``uv sync`` would rewrite site-packages underneath them.
Run them with ``.venv-dl/bin/python -m pytest tests/test_deep.py``.

The important test is
:func:`test_a_window_never_reads_a_row_from_after_its_own_sample`. Everything
else here is training mechanics; that one decides whether the exercise means
anything. A windowed model with an off-by-one in ``make_windows`` reads its own
future and nothing raises — AUC simply improves, which is the exact shape of
C.10's look-ahead defect that produced the highest-ranked result in the study.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("torch", reason="torch lives in .venv-dl, not .venv")

from research.deep import leakage, models
from research.diagnostics.confidence import auc_score

NS_PER_S = 1_000_000_000


def _panel(n: int = 3000, k: int = 6, seed: int = 2) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    features = rng.normal(0.0, 1.0, (n, k))
    ret = features[:, 0] * 2.0 + rng.normal(0.0, 0.5, n)
    ts = np.arange(n, dtype=np.int64) * NS_PER_S
    return ts, features, ret


# --------------------------------------------------------------------------- #
# windowing: the leak surface a tabular model does not have
# --------------------------------------------------------------------------- #


def test_a_window_never_reads_a_row_from_after_its_own_sample() -> None:
    # Arrange / Act / Assert — exhaustive over a realistic window length.
    for index in range(200):
        rows = models.window_contains_only_past(16, index)
        assert max(rows) <= index, f"window for {index} reads {max(rows)}, which is its future"
        assert rows[-1] == index, "the last window step must be the sample's own bar"


def test_make_windows_stacks_the_bars_ending_at_each_row() -> None:
    # Arrange — a counter per row makes the ordering readable.
    features = np.arange(10, dtype=np.float64).reshape(10, 1)

    # Act
    windows = models.make_windows(features, 3)

    # Assert — row 5 is [3, 4, 5]; early rows pad on the PAST side.
    assert windows[5, :, 0].tolist() == [3.0, 4.0, 5.0]
    assert windows[0, :, 0].tolist() == [0.0, 0.0, 0.0]
    assert windows.shape == (10, 3, 1)


def test_window_causality_probe_flags_an_actual_future_read() -> None:
    # Arrange — a deliberately broken windower that reads one row ahead. A
    # probe that cannot fail here would certify anything.
    original = models.window_contains_only_past
    try:
        models.window_contains_only_past = lambda length, index: [index + 1]

        # Act
        found = leakage.window_causality(4, n=32)

        # Assert
        assert not found["passed"]
        assert found["offenders"]
    finally:
        models.window_contains_only_past = original


def test_a_planted_future_column_is_detected_by_the_canary() -> None:
    # Arrange — the canary must fire on a deliberate leak, or a clean result
    # from it elsewhere proves nothing at all.
    ts, features, ret = _panel(n=2500)

    # Act
    found = leakage.planted_future_canary(ts, features, ret)

    # Assert
    assert found["passed"], f"canary failed to detect a planted future: {found}"
    assert found["auc_with_planted_future"] >= leakage.CANARY_MIN_AUC


# --------------------------------------------------------------------------- #
# training mechanics
# --------------------------------------------------------------------------- #


def test_both_architectures_learn_a_signal_that_is_genuinely_there() -> None:
    # Arrange — feature 0 drives the sign. If the models cannot find this, a
    # null result on real data says nothing about the data.
    ts, features, ret = _panel(n=3000)
    y01 = (ret > 0).astype(np.int64)
    # Small panel: batch 1024 would be ~3 gradient steps an epoch, which
    # tests the batch size rather than the model.
    cfg = models.DeepConfig(epochs=20, hidden=32, window=4, batch_size=128, dropout=0.0)

    for kind in ("mlp", "gru"):
        # Act
        prob = models.fit_oof(kind, ts, features, y01, 1000, 3, NS_PER_S, cfg)
        covered = ~np.isnan(prob)

        # Assert
        assert auc_score(y01[covered], prob[covered]) > 0.8, f"{kind} failed to learn"


def test_standardisation_statistics_come_from_the_training_fold_only() -> None:
    # Arrange — a test block on a wildly different scale. Fitting the scaler on
    # everything would drag the training block's scaled mean away from zero
    # using data it must never have seen.
    train = np.ones((100, 2, 3), dtype=np.float32)
    train[:, :, 0] = np.linspace(0.0, 1.0, 100)[:, None]
    test = np.full((10, 2, 3), 1000.0, dtype=np.float32)

    # Act
    scaled_train, scaled_test = models._standardise(train, test)

    # Assert — train standardises to about zero mean; test lands far away,
    # which is what a fold that never saw it should look like.
    assert abs(float(scaled_train[:, :, 0].mean())) < 0.05
    assert float(scaled_test[:, :, 0].mean()) > 10.0


def test_a_constant_feature_does_not_divide_by_zero() -> None:
    # Arrange — a column with no variance is common in thin instruments.
    train = np.ones((50, 1, 2), dtype=np.float32)
    test = np.ones((5, 1, 2), dtype=np.float32)

    # Act
    scaled_train, scaled_test = models._standardise(train, test)

    # Assert
    assert np.isfinite(scaled_train).all()
    assert np.isfinite(scaled_test).all()


def test_nan_features_are_neutralised_rather_than_propagated() -> None:
    # Arrange — cross-venue features are NaN wherever a reference venue is
    # absent, and one NaN reaching a gradient poisons every weight in the net.
    train = np.ones((50, 1, 2), dtype=np.float32)
    train[0, 0, 0] = np.nan
    test = np.full((5, 1, 2), np.nan, dtype=np.float32)

    # Act
    scaled_train, scaled_test = models._standardise(train, test)

    # Assert
    assert np.isfinite(scaled_train).all()
    assert np.isfinite(scaled_test).all()
