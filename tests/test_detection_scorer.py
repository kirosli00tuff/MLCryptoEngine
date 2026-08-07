"""C.24 Task 5 tests for the hard-rug scorer deliverable.

The load-bearing guarantees: features are ordered deterministically with the
missing-sentinel the trained matrix used, the creator-history columns C.23 found
inert are kept OUT, and the scorer plumbs a booster through to a probability that
moves the right way with concentration.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np

from research.detection import scorer as sc


def test_feature_vector_orders_and_fills_missing_with_sentinel() -> None:
    # Arrange — a dict missing several features and carrying an explicit None.
    features = {"top5_concentration_wend": 0.8, "mintable": 1.0, "n_early_holders": None}

    # Act
    vec = sc.feature_vector(features)

    # Assert — length matches FEATURES, values land in order, missing → -1.0.
    assert len(vec) == len(sc.FEATURES)
    assert vec[sc.FEATURES.index("top5_concentration_wend")] == 0.8
    assert vec[sc.FEATURES.index("mintable")] == 1.0
    assert vec[sc.FEATURES.index("n_early_holders")] == sc.MISSING  # None → sentinel
    assert vec[sc.FEATURES.index("freezable")] == sc.MISSING  # absent → sentinel


def test_features_exclude_creator_history_columns() -> None:
    # C.23 measured creator-history features inert on the honest boundary and
    # harmful out of sample; the deliverable must not silently readopt them.
    assert not any(f.startswith("creator_prior") for f in sc.FEATURES)
    assert "creator_days_since_prev_launch" not in sc.FEATURES
    assert "creator_first_seen" not in sc.FEATURES


def _toy_booster() -> lgb.Booster:
    # top5_concentration_wend (index 1) alone separates the classes.
    rng = np.random.default_rng(0)
    n = 240
    x = rng.normal(0.0, 0.05, size=(n, len(sc.FEATURES)))
    y = (np.arange(n) % 2 == 0).astype(int)
    x[:, sc.FEATURES.index("top5_concentration_wend")] = np.where(y == 1, 0.95, 0.30)
    model = lgb.LGBMClassifier(n_estimators=50, learning_rate=0.1, verbose=-1)
    model.fit(x, y)
    return model.booster_


def test_probability_rises_with_concentration() -> None:
    # Arrange — a scorer over a booster where concentration drives the label.
    scorer = sc.HardRugScorer(booster=_toy_booster(), base_rate=0.5)

    # Act
    hi = scorer.probability({"top5_concentration_wend": 0.95})
    lo = scorer.probability({"top5_concentration_wend": 0.30})

    # Assert — both are probabilities, and higher concentration scores higher.
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0
    assert hi > lo


def test_score_mint_composes_injected_feature_fetch() -> None:
    # Arrange — score_mint takes a pool id and a feature provider (no vendor key).
    scorer = sc.HardRugScorer(booster=_toy_booster(), base_rate=0.5)
    fetched: dict[str, dict[str, float | None]] = {"MINT_A": {"top5_concentration_wend": 0.95}}

    # Act
    prob = sc.score_mint("MINT_A", scorer, lambda m: fetched[m])

    # Assert — the provider is called with the mint and its result is scored.
    assert prob == scorer.probability({"top5_concentration_wend": 0.95})


def test_scope_note_leads_with_clearance_and_names_the_weak_flag() -> None:
    # Act
    note = sc.scope_note(
        base_rate=0.483, clear_precision=0.984, clear_recall=0.538, flag_precision=0.464
    )

    # Assert — the note leads with clearance, carries both numbers, and states
    # plainly the two boundaries it does not cross.
    assert "CLEARANCE" in note
    assert "0.984" in note and "0.464" in note
    assert "does NOT detect soft or slow rugs" in note
    assert "not a reliable rug warning" in note
