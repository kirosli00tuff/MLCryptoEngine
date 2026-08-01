"""Purged k-fold, walk-forward, and the experiment log."""

from __future__ import annotations

from pathlib import Path

import pytest

from research.validation.experiment_log import log_experiment, read_experiments
from research.validation.purged_kfold import PurgedKFold
from research.validation.walk_forward import walk_forward

NS_PER_S = 1_000_000_000
BASE_NS = 1_785_412_800 * 1_000_000_000
# 1000 samples, one per second.
TS = [BASE_NS + i * NS_PER_S for i in range(1000)]
HORIZON_NS = 30 * NS_PER_S


def test_purged_kfold_train_label_windows_never_overlap_test() -> None:
    folds = list(PurgedKFold(n_splits=5, label_horizon_ns=HORIZON_NS).split(TS))

    assert len(folds) == 5
    covered_test = sorted(i for _, test in folds for i in test)
    assert covered_test == list(range(1000)), "every sample is tested exactly once"
    for train, test in folds:
        test_start = TS[test[0]]
        test_end = TS[test[-1]] + HORIZON_NS
        for i in train:
            # The purge criterion itself, checked independently: label window
            # [t, t+h] disjoint from the test block, plus the embargo after it.
            assert TS[i] + HORIZON_NS < test_start or TS[i] > test_end + HORIZON_NS, (
                f"train sample {i} label window overlaps test block"
            )


def test_purged_kfold_embargo_removes_more_than_purge_alone() -> None:
    no_embargo = list(PurgedKFold(2, HORIZON_NS, embargo_ns=0).split(TS))
    embargoed = list(PurgedKFold(2, HORIZON_NS).split(TS))
    # First fold: test block at the start, train after it — the embargo bites.
    assert len(embargoed[0][0]) < len(no_embargo[0][0])


def test_purged_kfold_rejects_unsorted_and_tiny_inputs() -> None:
    with pytest.raises(ValueError):
        list(PurgedKFold(2, 0).split([2, 1]))
    with pytest.raises(ValueError):
        list(PurgedKFold(5, 0).split([1, 2, 3]))


def test_walk_forward_windows_roll_and_purge_the_train_tail() -> None:
    folds = list(
        walk_forward(
            TS,
            train_span_ns=400 * NS_PER_S,
            test_span_ns=200 * NS_PER_S,
            label_horizon_ns=HORIZON_NS,
        )
    )

    assert len(folds) == 3
    for train, test in folds:
        train_end_ns = TS[test[0]]
        assert max(TS[i] for i in train) + HORIZON_NS < train_end_ns, (
            "train labels must resolve before the test window opens"
        )
        assert min(TS[i] for i in test) >= train_end_ns
    # Same parameters on longer data yield more folds without code changes.
    longer = [BASE_NS + i * NS_PER_S for i in range(3000)]
    assert len(list(walk_forward(longer, 400 * NS_PER_S, 200 * NS_PER_S))) > len(folds)


def test_experiment_log_appends_complete_records(tmp_path: Path) -> None:
    path = tmp_path / "experiments.jsonl"
    entry = {
        "dates": ["2026-07-31"],
        "feature_set": ["qimb_best"],
        "label": "ret_bps_500ms",
        "cost_assumption": "maker tier0",
        "results": {"auc": 0.5},
    }

    first = log_experiment(entry, path=path)
    second = log_experiment(entry, path=path)

    stored = read_experiments(path)
    assert len(stored) == 2
    assert stored[0]["run_id"] != second["run_id"]
    for record in stored:
        for key in ("run_id", "logged_at", "git_sha", "cost_assumption", "results"):
            assert key in record
    assert first["results"] == {"auc": 0.5}
