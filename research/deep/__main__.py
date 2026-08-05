"""CLI: ``.venv-dl/bin/python -m research.deep`` — C.14 Task 4.

Runs the LightGBM baseline and the two deep models over identical purged folds,
and scores them against the bar committed to progress.md (commit a2d7466)
before any of this was trained:

    at 900 s, out of sample: AUC >= baseline + 0.020 AND gross capture >=
    baseline + 1.00 bps. Both. An AUC win without a capture win is a failure.

The leakage probes run against the deep path specifically, and a model that
clears the bar while failing a probe is reported as a **leak**, not a discovery.
That was decided in advance precisely so the decision is not made while looking
at an attractive number.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from data.config import AppConfig, load_config
from data.store.parquet_writer import PART_NAME
from research.deep import leakage, models
from research.diagnostics import confidence as cf
from research.features.engine import FEATURE_COLUMNS
from research.labels.fixed_horizon import embargo_ns_for
from research.pipeline import load_samples, samples_partition_dir, training_columns
from research.validation.experiment_log import log_experiment

# Pre-registered in progress.md commit a2d7466. Constants here so that reading
# the results cannot move them.
STATED_HORIZON_MS = 900_000
SECONDARY_HORIZON_MS = 1000
AUC_MARGIN = 0.020
CAPTURE_MARGIN_BPS = 1.00
N_SPLITS = 5


def _dates(cfg: AppConfig, venue: str, symbol: str) -> list[str]:
    root = samples_partition_dir(cfg.processed_dir, venue, symbol, "x").parent
    if not root.is_dir():
        return []
    return sorted(
        p.name.removeprefix("date=")
        for p in root.iterdir()
        if p.name.startswith("date=") and (p / PART_NAME).is_file()
    )


def compare(
    ts: np.ndarray,
    features: np.ndarray,
    ret: np.ndarray,
    horizon_ms: int,
    cfg: models.DeepConfig,
) -> dict[str, Any]:
    """Baseline against MLP and GRU on identical folds at one horizon."""
    usable = ~np.isnan(ret)
    ts_u, x_u, ret_u = ts[usable], features[usable], ret[usable]
    if ret_u.size < max(cf.MIN_SAMPLES, N_SPLITS * 20):
        return {"skipped": "too few resolved labels"}
    y01 = (ret_u > 0).astype(np.int64)
    embargo = embargo_ns_for((horizon_ms,))

    base_prob, base_ret, base_y = cf.oof_predictions(
        ts_u, x_u, ret_u, horizon_ms, N_SPLITS, embargo
    )
    base_auc = cf.auc_score(base_y, base_prob)
    base_capture = cf.gross_capture(base_prob, base_ret)
    out: dict[str, Any] = {
        "horizon_ms": horizon_ms,
        "n": int(base_prob.size),
        "baseline_lightgbm": {
            "auc": round(base_auc, 4),
            "gross_capture_bps": round(base_capture, 4),
        },
        "models": {},
    }
    for kind in ("mlp", "gru"):
        prob = models.fit_oof(kind, ts_u, x_u, y01, horizon_ms, N_SPLITS, embargo, cfg)
        covered = ~np.isnan(prob)
        if int(covered.sum()) < cf.MIN_SAMPLES:
            out["models"][kind] = {"skipped": "no fold produced predictions"}
            continue
        auc = cf.auc_score(y01[covered], prob[covered])
        capture = cf.gross_capture(prob[covered], ret_u[covered])
        beats_auc = bool(auc >= base_auc + AUC_MARGIN)
        beats_capture = bool(capture >= base_capture + CAPTURE_MARGIN_BPS)
        out["models"][kind] = {
            "auc": round(auc, 4),
            "gross_capture_bps": round(capture, 4),
            "delta_auc": round(auc - base_auc, 4),
            "delta_capture_bps": round(capture - base_capture, 4),
            "clears_auc_margin": beats_auc,
            "clears_capture_margin": beats_capture,
            # Both required. This is the line the pre-registration insisted on.
            "passes_bar": bool(beats_auc and beats_capture),
        }
    return out


def run(cfg: AppConfig, venue: str, symbol: str) -> dict[str, Any]:
    dates = _dates(cfg, venue, symbol)
    if not dates:
        return {"error": f"no samples for {venue} {symbol}"}
    paths = [samples_partition_dir(cfg.processed_dir, venue, symbol, d) / PART_NAME for d in dates]
    data = load_samples(
        [p for p in paths if p.is_file()], columns=training_columns(), dtype=np.float32
    )
    if not data:
        return {"error": "no samples loaded"}

    ts = data["ts_ns"].astype(np.int64)
    features = np.column_stack([data[name] for name in FEATURE_COLUMNS]).astype(np.float64)
    deep_cfg = models.DeepConfig()

    horizons: dict[str, Any] = {}
    for horizon in (STATED_HORIZON_MS, SECONDARY_HORIZON_MS):
        column = f"ret_bps_{horizon}ms"
        if column in data:
            horizons[str(horizon)] = compare(
                ts, features, data[column].astype(np.float64), horizon, deep_cfg
            )

    probes = leakage.run_probes(ts, features, data, deep_cfg, N_SPLITS)
    stated = horizons.get(str(STATED_HORIZON_MS), {})
    passed = [
        kind
        for kind, row in stated.get("models", {}).items()
        if isinstance(row, dict) and row.get("passes_bar")
    ]
    leaked = not probes.get("all_passed", False)
    if passed and leaked:
        outcome = "LEAK — an improvement that fails a leakage probe is treated as a leak"
    elif passed:
        outcome = "PASS"
    else:
        outcome = "FAIL"
    return {
        "venue": venue,
        "symbol": symbol,
        "dates": dates,
        "n_days": len(dates),
        "config": deep_cfg.describe(),
        "bar": {
            "stated_horizon_ms": STATED_HORIZON_MS,
            "auc_margin": AUC_MARGIN,
            "capture_margin_bps": CAPTURE_MARGIN_BPS,
            "both_required": True,
            "pre_registered_in": "progress.md, commit a2d7466, before training",
        },
        "horizons": horizons,
        "leakage_probes": probes,
        "models_clearing_bar": passed,
        "outcome": outcome,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.deep")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--venue", type=str, default="coinbase")
    parser.add_argument("--symbol", type=str, default="BTC-USD")
    args = parser.parse_args(argv)

    payload = run(load_config(), args.venue, args.symbol)
    log_experiment(
        {
            "stage": "C.14",
            "study": "deep learning capacity test (MLP + GRU) against the LightGBM baseline",
            "source": f"recorded samples {args.venue} {args.symbol}",
            "dates": payload.get("dates", []),
            "cost_summary": "gross capture reported before cost; the bar is a margin, not an EV",
            "results": {
                "outcome": payload.get("outcome"),
                "models_clearing_bar": payload.get("models_clearing_bar"),
                "stated_horizon": payload.get("horizons", {}).get(str(STATED_HORIZON_MS)),
                "leakage_probes": payload.get("leakage_probes"),
            },
            "note": "bar pre-registered in progress.md commit a2d7466 BEFORE training",
        }
    )
    text = json.dumps(payload, indent=1, default=str)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
