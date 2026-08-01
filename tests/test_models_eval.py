"""Baselines, metrics, and the purged-CV training loop on planted signal."""

from __future__ import annotations

import numpy as np

from research.features.engine import FEATURE_COLUMNS
from research.labels.costs import CostModel
from research.models.baselines import LastSignBaseline, ZeroBaseline
from research.models.evaluate import auc, calibration_bins, expected_value_bps, hit_rate
from research.pipeline import train_and_evaluate

NS_PER_S = 1_000_000_000
BASE_NS = 1_785_412_800 * 1_000_000_000


def test_zero_baseline_never_trades_and_last_sign_follows_momentum() -> None:
    x = np.array([[0.5], [-1.0], [0.0]])
    assert ZeroBaseline().predict(x).tolist() == [0.0, 0.0, 0.0]
    assert LastSignBaseline(0).predict(x).tolist() == [1.0, -1.0, 0.0]


def test_metrics_handle_edges_honestly() -> None:
    pred = np.array([1.0, -1.0, 0.0, 1.0])
    realized = np.array([2.0, -3.0, 5.0, -1.0])
    assert hit_rate(pred, realized) == 2 / 3, "the abstained prediction is excluded"
    assert hit_rate(np.zeros(4), realized) is None, "never trading has no hit rate"
    assert auc(np.array([1, 1, 1]), np.array([0.1, 0.2, 0.3])) is None, "single class"
    # EV over traded predictions: mean of (2-1, 3-1, -1-1) = mean of (1, 2, -2).
    ev = expected_value_bps(pred, realized, cost_bps=1.0)
    assert ev is not None and np.isclose(ev, (1.0 + 2.0 - 2.0) / 3)
    bins = calibration_bins(np.array([0, 1, 1, 0]), np.array([0.1, 0.9, 0.8, 0.2]))
    assert sum(int(b["count"]) for b in bins) == 4


def test_train_and_evaluate_finds_planted_signal_and_beats_baselines() -> None:
    rng = np.random.default_rng(11)
    n = 1_500
    data: dict[str, np.ndarray] = {"ts_ns": BASE_NS + np.arange(n) * NS_PER_S}
    for name in FEATURE_COLUMNS:
        data[name] = rng.normal(size=n)
    # Plant: the 100 ms forward return follows qimb_best; costs are tiny.
    signal = data["qimb_best"]
    data["ret_bps_100ms"] = 20.0 * np.sign(signal) + rng.normal(scale=2.0, size=n)
    data["spread_bps"] = np.full(n, 1.0)

    results = train_and_evaluate(
        data,
        {"maker": CostModel(venue="kraken", mode="maker", fee_bps_per_leg=0.5)},
        n_splits=2,
        horizons_ms=(100,),
    )

    horizon = results["horizons"]["100"]
    assert horizon["auc"] is not None and horizon["auc"] > 0.9, "planted signal must be found"
    maker = horizon["cost_modes"]["maker"]
    model_ev = maker["model_classifier"]["ev_bps_net"]
    zero_ev = maker["baseline_zero"]["ev_bps_net"]
    last_ev = maker["baseline_last_sign"]["ev_bps_net"]
    assert model_ev is not None and model_ev > 10.0
    assert zero_ev is None, "predict-zero never trades"
    assert last_ev is None or model_ev > last_ev
    assert horizon["feature_importances_top10"], "importances must be reported"
