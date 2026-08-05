"""CLI: ``python -m research.diagnostics`` — C.14 Tasks 1 to 3.

Order follows the pre-registration in progress.md (commit a2d7466): the
confidence-versus-magnitude diagnostic first, because it is the priority and
because it decides how everything after it should be read; then sample
stability across days; then the cross-venue feature delta.

Every threshold this scores itself against was committed before any of it ran.
Nothing here may move a bar.
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
from research.diagnostics import confidence as cf
from research.features.engine import FEATURE_COLUMNS
from research.labels.costs import cost_model_from_config
from research.labels.fixed_horizon import DEFAULT_HORIZONS_MS, embargo_ns_for
from research.pipeline import load_samples, samples_partition_dir, training_columns
from research.validation.experiment_log import log_experiment

# The cross-venue feature class: mid divergence, its z-score, and the lead-lag
# correlation ladder. These ranked near the top of Phase B importance and were
# 100% NaN in the C.8 CME run, so that test ran with its best-scoring feature
# class entirely absent. Task 3 is the A/B that says what they are worth where
# they can actually be computed.
XV_FEATURES = [name for name in FEATURE_COLUMNS if name.startswith("xv_")]
BASE_FEATURES = [name for name in FEATURE_COLUMNS if not name.startswith("xv_")]
N_SPLITS = 5
# The day Phase B's headline rests on, kept as its own comparison so the
# expanded-sample figures can be read against the number they replace.
HEADLINE_DATE = "2026-07-31"


def _dates_with_samples(cfg: AppConfig, venue: str, symbol: str) -> list[str]:
    root = samples_partition_dir(cfg.processed_dir, venue, symbol, "x").parent
    if not root.is_dir():
        return []
    return sorted(
        p.name.removeprefix("date=")
        for p in root.iterdir()
        if p.name.startswith("date=") and (p / PART_NAME).is_file()
    )


# Keep every Nth retained sample. Because samples are event bars, striding by N
# is equivalent to having sampled every N x every_n book updates: it coarsens the
# bar, it does not bias which moments are chosen (ADR-025). It exists because the
# full six-day cross-venue sweep is ~5 hours of LightGBM fits and this stage has
# a deadline. **A coarser bar is a real change to the experiment, not an
# implementation detail, so the value used is reported in every payload.**
STRIDE = 1


def _load(cfg: AppConfig, venue: str, symbol: str, dates: list[str]) -> dict[str, Any]:
    paths = [samples_partition_dir(cfg.processed_dir, venue, symbol, d) / PART_NAME for d in dates]
    return load_samples(
        [p for p in paths if p.is_file()],
        columns=training_columns(),
        dtype=np.float32,
        stride=STRIDE,
    )


def _matrix(data: dict[str, Any], names: list[str]) -> np.ndarray:
    return np.column_stack([data[name] for name in names]).astype(np.float64)


def _round_trip_bps(cfg: AppConfig, venue: str, symbol: str) -> float:
    model = cost_model_from_config(venue, cfg.venues[venue], "maker", symbol=symbol)
    if model.is_per_contract:
        # Per-contract venues price in dollars; the bps figure depends on each
        # sample's own notional (ADR-023) and is not a constant.
        return float("nan")
    return 2.0 * model.fee_bps_per_leg


def task1_confidence(
    cfg: AppConfig, venue: str, symbol: str, dates: list[str], horizons: tuple[int, ...]
) -> dict[str, Any]:
    """Confidence versus realised magnitude, on the expanded sample."""
    data = _load(cfg, venue, symbol, dates)
    if not data:
        return {"skipped": "no samples"}
    ts = data["ts_ns"].astype(np.int64)
    features = _matrix(data, FEATURE_COLUMNS)
    reports: list[cf.ConfidenceReport] = []
    for horizon in horizons:
        column = f"ret_bps_{horizon}ms"
        if column not in data:
            continue
        found = cf.analyse(
            ts,
            features,
            data[column].astype(np.float64),
            horizon,
            N_SPLITS,
            embargo_ns_for((horizon,)),
        )
        if found is not None:
            reports.append(found)
    if not reports:
        return {"skipped": "no horizon produced enough resolved labels"}
    cost = _round_trip_bps(cfg, venue, symbol)
    return {
        "dates": dates,
        "n_days": len(dates),
        "round_trip_cost_bps": cost,
        "per_horizon": [r.summary() for r in reports],
        "verdict": cf.verdict(reports, cost),
    }


def task2_stability(
    cfg: AppConfig, venue: str, symbol: str, dates: list[str], horizons: tuple[int, ...]
) -> dict[str, Any]:
    """Per-day AUC and gross capture. Pooling hides instability, so this does not pool.

    A headline resting on one day that does not reproduce across five is a
    finding in itself, and the only way to see it is per day.
    """
    per_day: dict[str, dict[str, Any]] = {}
    for date in dates:
        data = _load(cfg, venue, symbol, [date])
        if not data:
            per_day[date] = {"skipped": "no samples"}
            continue
        ts = data["ts_ns"].astype(np.int64)
        features = _matrix(data, FEATURE_COLUMNS)
        row: dict[str, Any] = {"n_samples": int(ts.size)}
        for horizon in horizons:
            column = f"ret_bps_{horizon}ms"
            if column not in data:
                continue
            ret = data[column].astype(np.float64)
            usable = ~np.isnan(ret)
            if int(usable.sum()) < max(cf.MIN_SAMPLES, N_SPLITS * 20):
                row[str(horizon)] = None
                continue
            prob, kept, y01 = cf.oof_predictions(
                ts[usable],
                features[usable],
                ret[usable],
                horizon,
                N_SPLITS,
                embargo_ns_for((horizon,)),
            )
            if prob.size < cf.MIN_SAMPLES:
                row[str(horizon)] = None
                continue
            row[str(horizon)] = {
                "auc": round(cf.auc_score(y01, prob), 4),
                "gross_capture_bps": round(cf.gross_capture(prob, kept), 4),
                "n": int(prob.size),
            }
        per_day[date] = row

    spread: dict[str, Any] = {}
    for horizon in horizons:
        rows = [d[str(horizon)] for d in per_day.values() if isinstance(d.get(str(horizon)), dict)]
        if len(rows) < 2:
            continue
        aucs = [r["auc"] for r in rows]
        captures = [r["gross_capture_bps"] for r in rows]
        signs = {int(np.sign(c)) for c in captures if c != 0.0}
        spread[str(horizon)] = {
            "days": len(rows),
            "auc_min": round(min(aucs), 4),
            "auc_max": round(max(aucs), 4),
            "auc_range": round(max(aucs) - min(aucs), 4),
            "capture_min_bps": round(min(captures), 4),
            "capture_max_bps": round(max(captures), 4),
            "capture_sign_flips": len(signs) > 1,
        }

    ranges = [v["auc_range"] for v in spread.values()]
    flips = any(v["capture_sign_flips"] for v in spread.values())
    if not ranges:
        outcome = "INSUFFICIENT DAYS"
    elif max(ranges) > 0.10 or flips:
        outcome = "MATERIALLY UNSTABLE"
    elif max(ranges) <= 0.05:
        outcome = "STABLE"
    else:
        outcome = "MILDLY UNSTABLE"
    return {
        "per_day": per_day,
        "spread_by_horizon": spread,
        "max_auc_range": round(max(ranges), 4) if ranges else None,
        "any_capture_sign_flip": flips,
        "outcome": outcome,
        "bars": {
            "stable": "max AUC range <= 0.05 across days AND no capture sign flip",
            "materially_unstable": "AUC range > 0.10 at any horizon OR any capture sign flip",
            "pre_registered_in": "progress.md, commit a2d7466",
        },
    }


def task3_cross_venue(
    cfg: AppConfig, venue: str, symbol: str, dates: list[str], horizons: tuple[int, ...]
) -> dict[str, Any]:
    """Same folds, same days, cross-venue features on versus off."""
    data = _load(cfg, venue, symbol, dates)
    if not data:
        return {"skipped": "no samples"}
    ts = data["ts_ns"].astype(np.int64)
    full = _matrix(data, FEATURE_COLUMNS)
    base = _matrix(data, BASE_FEATURES)

    # A feature that is entirely NaN is absent, never zero. Reporting coverage
    # beside the delta is what stops "no improvement" being confused with "the
    # features were not there" — the exact confusion that made C.8's headline
    # run without its best-scoring feature class.
    coverage = {
        name: round(float(np.mean(~np.isnan(data[name]))), 4)
        for name in XV_FEATURES
        if name in data
    }

    rows: list[dict[str, Any]] = []
    for horizon in horizons:
        column = f"ret_bps_{horizon}ms"
        if column not in data:
            continue
        ret = data[column].astype(np.float64)
        usable = ~np.isnan(ret)
        if int(usable.sum()) < max(cf.MIN_SAMPLES, N_SPLITS * 20):
            continue
        embargo = embargo_ns_for((horizon,))
        with_prob, with_ret, with_y = cf.oof_predictions(
            ts[usable], full[usable], ret[usable], horizon, N_SPLITS, embargo
        )
        without_prob, without_ret, without_y = cf.oof_predictions(
            ts[usable], base[usable], ret[usable], horizon, N_SPLITS, embargo
        )
        if with_prob.size < cf.MIN_SAMPLES or without_prob.size < cf.MIN_SAMPLES:
            continue
        auc_with = cf.auc_score(with_y, with_prob)
        auc_without = cf.auc_score(without_y, without_prob)
        cap_with = cf.gross_capture(with_prob, with_ret)
        cap_without = cf.gross_capture(without_prob, without_ret)
        rows.append(
            {
                "horizon_ms": horizon,
                "auc_with_xv": round(auc_with, 4),
                "auc_without_xv": round(auc_without, 4),
                "delta_auc": round(auc_with - auc_without, 4),
                "capture_with_xv_bps": round(cap_with, 4),
                "capture_without_xv_bps": round(cap_without, 4),
                "delta_capture_bps": round(cap_with - cap_without, 4),
            }
        )
    if not rows:
        return {"skipped": "no horizon produced enough resolved labels"}

    deltas = [r["delta_auc"] for r in rows]
    best_capture_delta = max(r["delta_capture_bps"] for r in rows)
    material_auc = sum(1 for d in deltas if d >= 0.010) >= len(deltas) / 2
    if material_auc or best_capture_delta >= 0.50:
        outcome = "MATERIAL"
    elif max(deltas) < 0.005:
        outcome = "IMMATERIAL"
    else:
        outcome = "MARGINAL"
    return {
        "xv_features": XV_FEATURES,
        "xv_coverage_fraction_non_nan": coverage,
        "per_horizon": rows,
        "max_delta_auc": round(max(deltas), 4),
        "max_delta_capture_bps": round(best_capture_delta, 4),
        "outcome": outcome,
        "bars": {
            "material": "dAUC >= +0.010 at half or more horizons OR dcapture >= +0.50 bps",
            "immaterial": "dAUC < +0.005 at every horizon",
            "pre_registered_in": "progress.md, commit a2d7466",
        },
    }


def run(
    cfg: AppConfig,
    horizons: tuple[int, ...],
    only: str | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "stage": "C.14",
        "pre_registration_commit": "a2d7466",
        "horizons_ms": list(horizons),
        "n_splits": N_SPLITS,
        "sample_stride": STRIDE,
        "stride_note": (
            "every Nth retained event bar; equivalent to a coarser bar, not a biased "
            "selection of moments (ADR-025). Reported because it is a change to the "
            "experiment."
        ),
        "venues": {},
    }
    for venue in sorted(cfg.venues):
        if only and venue != only:
            continue
        for symbol in cfg.venues[venue].symbols:
            if symbols is not None and symbol not in symbols:
                continue
            dates = _dates_with_samples(cfg, venue, symbol)
            if not dates:
                continue
            key = f"{venue}:{symbol}"
            print(f"--- {key}: {len(dates)} days {dates}", flush=True)
            entry: dict[str, Any] = {"dates": dates}
            entry["task1_confidence_vs_magnitude"] = task1_confidence(
                cfg, venue, symbol, dates, horizons
            )
            entry["task2_stability"] = task2_stability(cfg, venue, symbol, dates, horizons)
            entry["task3_cross_venue"] = task3_cross_venue(cfg, venue, symbol, dates, horizons)
            if HEADLINE_DATE in dates and len(dates) > 1:
                entry["task1_headline_day_only"] = task1_confidence(
                    cfg, venue, symbol, [HEADLINE_DATE], horizons
                )
            out["venues"][key] = entry
            verdict = entry["task1_confidence_vs_magnitude"].get("verdict", {})
            print(
                f"    T1={verdict.get('outcome')}"
                f"  T2={entry['task2_stability'].get('outcome')}"
                f"  T3={entry['task3_cross_venue'].get('outcome')}",
                flush=True,
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.diagnostics")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--venue", type=str, default=None)
    parser.add_argument(
        "--horizons", type=int, nargs="*", default=list(DEFAULT_HORIZONS_MS), help="horizons in ms"
    )
    parser.add_argument("--symbol", action="append", dest="symbols", default=None)
    parser.add_argument(
        "--stride", type=int, default=1, help="keep every Nth sample; reported in the payload"
    )
    args = parser.parse_args(argv)

    global STRIDE
    STRIDE = max(1, args.stride)
    payload = run(load_config(), tuple(args.horizons), only=args.venue, symbols=args.symbols)
    log_experiment(
        {
            "stage": "C.14",
            "study": "diagnostic: confidence vs magnitude, sample stability, cross-venue delta",
            "source": "recorded crypto spot samples (kraken, coinbase, hyperliquid)",
            "dates": sorted(
                {d for entry in payload["venues"].values() for d in entry.get("dates", [])}
            ),
            "cost_summary": "maker round trip from config/venues.yaml per venue",
            "results": {
                key: {
                    "task1": entry.get("task1_confidence_vs_magnitude", {}).get("verdict"),
                    "task2": entry.get("task2_stability", {}).get("outcome"),
                    "task3": entry.get("task3_cross_venue", {}).get("outcome"),
                }
                for key, entry in payload["venues"].items()
            },
            "note": "bars pre-registered in progress.md commit a2d7466 before any result",
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
