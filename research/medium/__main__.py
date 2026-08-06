"""CLI: ``python -m research.medium`` — the whole C.17 study.

Order is the registered order: availability audit, panel with per-feature lags,
the 40-cell grid in full, the six-bar verdict. The end condition rides on the
verdict: a FAIL here ends the project's alpha search by decision, and that
sentence predates every number this prints (progress.md, commit 370ba41).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from data.archive import binance, binance_futures, series
from data.archive import hyperliquid as hl
from data.config import AppConfig, load_config
from research.medium import data as med_data
from research.medium import features as feat
from research.medium import study
from research.validation.experiment_log import log_experiment

ASSETS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
PRICE_MONTHS = ("2020-07", "2026-07")
FUNDING_MONTHS = ("2020-01", "2026-07")
WEEK_START_MS = 1_596_326_400_000  # 2020-08-02, a Sunday
WEEK_END_MS = 1_753_574_400_000  # 2026-07-26, the sample's last full Sunday
MS_PER_DAY = 86_400_000
TREND_DAYS = 30
N_CLASSES = 5  # A, B, C, D, E — fixed at registration
N_TRIALS = N_CLASSES * len(study.HORIZONS_WEEKS) * len(study.VARIANTS)


def _daily_closes(cfg: AppConfig, symbol: str) -> dict[int, float]:
    months = binance.months_between(*PRICE_MONTHS)
    for month in months:
        binance.fetch_month(cfg, symbol, "1d", month)
    bars = series.load_symbol(cfg, symbol, "1d", months)
    return {ns // 1_000_000: bar.close for ns, bar in bars.items()}


def _funding_rates(cfg: AppConfig, symbol: str) -> dict[int, float]:
    for month in binance.months_between(*FUNDING_MONTHS):
        binance_futures.fetch_funding_month(cfg, symbol, month)
    rows = binance_futures.load_funding(cfg, symbol, *FUNDING_MONTHS)
    return {row.time_ms: row.rate for row in rows}


def _premiums(cfg: AppConfig, coin: str) -> dict[int, float]:
    return {
        row.time_ms: row.premium for row in hl.fetch_funding(cfg, coin) if np.isfinite(row.premium)
    }


def _weekly_close(closes: dict[int, float], weeks: list[int]) -> np.ndarray:
    return np.asarray([closes.get(w, np.nan) for w in weeks], dtype=np.float64)


def _forward_return(weekly: np.ndarray, horizon: int) -> np.ndarray:
    out = np.full(weekly.size, np.nan)
    valid = weekly > 0
    for i in range(weekly.size - horizon):
        if valid[i] and valid[i + horizon]:
            out[i] = weekly[i + horizon] / weekly[i] - 1.0
    return out


def run(cfg: AppConfig) -> dict[str, Any]:
    audit = med_data.audit(cfg)

    weeks = feat.weekly_grid(WEEK_START_MS, WEEK_END_MS)
    weeks_arr = np.asarray(weeks, dtype=np.int64)
    closes = {a: _daily_closes(cfg, s) for a, s in ASSETS.items()}
    weekly = {a: _weekly_close(closes[a], weeks) for a in ASSETS}
    next_week = {a: _forward_return(weekly[a], 1) for a in ASSETS}

    btc_daily = feat.Series.from_map(closes["BTC"])
    trend_up = np.asarray(
        [
            btc_daily.latest_usable(w, 0) > btc_daily.latest_usable(w - TREND_DAYS * MS_PER_DAY, 0)
            for w in weeks
        ],
        dtype=bool,
    )

    # ---- feature classes, each with its registered lag ----
    class_a = feat.stablecoin_class(
        med_data.load_defillama(med_data.fetch_defillama_stablecoins(cfg))
    )
    cm = {
        a: med_data.load_coinmetrics(med_data.fetch_coinmetrics_asset(cfg, a.lower()))
        for a in ASSETS
    }
    class_b = {
        a: feat.netflow_class(
            cm[a].get("FlowInExUSD", {}),
            cm[a].get("FlowOutExUSD", {}),
            cm[a].get("CapMrktCurUSD", cm[a].get("SplyExUSD", {})),
            cm[a].get("SplyExNtv", {}),
        )
        for a in ASSETS
    }
    class_c = {a: feat.funding_class(_funding_rates(cfg, s)) for a, s in ASSETS.items()}
    class_d = {a: feat.basis_class(_premiums(cfg, a)) for a in ASSETS}

    def matrix(parts_by_asset: dict[str, list[feat.FeatureSet]]) -> dict[str, np.ndarray]:
        return {
            a: np.asarray([feat.combined_row(parts_by_asset[a], w) for w in weeks]) for a in ASSETS
        }

    class_inputs: dict[str, dict[str, np.ndarray]] = {
        "A": matrix({a: [class_a] for a in ASSETS}),
        "B": matrix({a: [class_b[a]] for a in ASSETS}),
        "C": matrix({a: [class_c[a]] for a in ASSETS}),
        "D": matrix({a: [class_d[a]] for a in ASSETS}),
        "E": matrix({a: [class_a, class_b[a], class_c[a], class_d[a]] for a in ASSETS}),
    }

    # ---- the grid, every cell, nothing dropped ----
    paths: list[tuple[str, int, str, dict[str, np.ndarray]]] = []
    skipped: list[dict[str, Any]] = []
    for klass, x_by_asset in class_inputs.items():
        for horizon in study.HORIZONS_WEEKS:
            labels = {a: _forward_return(weekly[a], horizon) for a in ASSETS}
            cell = study.CellInput(
                weeks_ms=weeks_arr,
                x_by_asset=x_by_asset,
                label_by_asset=labels,
                next_week_return=next_week,
                btc_weekly_return=next_week["BTC"],
                btc_trend_up=trend_up,
            )
            for variant in study.VARIANTS:
                path = study.simulate_cell(cell, horizon, variant)
                if path is None:
                    skipped.append(
                        {
                            "cell": f"{klass}/h{horizon}w/{variant}",
                            "reason": "under 30 scoreable weeks after lags and min-train",
                        }
                    )
                else:
                    paths.append((klass, horizon, variant, path))

    per_bar = []
    for _, _, _, path in paths:
        net = path["gross"] - path["traded"] * study.FEE_HL * study.BPS
        sigma = float(np.std(net, ddof=1))
        per_bar.append(float(np.mean(net)) / sigma if sigma > 0 else 0.0)
    sharpe_std = float(np.std(np.asarray(per_bar), ddof=1)) if len(per_bar) > 1 else 0.0

    rows = [
        study.cell_metrics(path, klass, horizon, variant, N_TRIALS, sharpe_std)
        for klass, horizon, variant, path in paths
    ]
    result_verdict = study.verdict(rows)

    return {
        "premise": (
            "Medium-horizon prediction on feature classes no model here has seen: "
            "stablecoin flows, exchange netflows, funding regime, basis state. The final "
            "research door; a FAIL ends the alpha search by decision (commit 370ba41)."
        ),
        "pre_registration_commit": "370ba41",
        "availability_audit": audit,
        "lags_applied_days": feat.LAG_DAYS,
        "panel": feat.panel_summary([class_a, class_b["BTC"], class_c["BTC"], class_d["BTC"]]),
        "grid": {
            "classes": sorted(class_inputs),
            "horizons_weeks": list(study.HORIZONS_WEEKS),
            "variants": list(study.VARIANTS),
            "n_trials_registered": N_TRIALS,
            "cells_scored": len(rows),
            "cells_skipped": skipped,
            "cross_cell_per_bar_sharpe_std": round(sharpe_std, 5),
        },
        "kraken_tier_note": (
            "long-only cells ship net at BOTH 25 and 40 bps/side; venues.yaml says 40 "
            "(base tier, corrected 2026-08-01), commonly cited current schedules say 25. "
            "The actual account tier is not readable from Stage 1 by design — "
            "reconciliation is an operator action against the account page."
        ),
        "cells": rows,
        "verdict": result_verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.medium")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = run(load_config())
    log_experiment(
        {
            "stage": "C.17",
            "study": "medium-horizon prediction on untested feature classes (final door)",
            "source": (
                "coinmetrics_community + defillama_stablecoins (new archives) + "
                "binance/hyperliquid funding archives on disk; nothing purchased"
            ),
            "dates": ["2020-08-02", "2026-07-26"],
            "cost_summary": "HL 1.5 bps/side all cells; LO also at 25 and 40 bps/side spot",
            "results": {
                "verdict": payload.get("verdict"),
                "grid": payload.get("grid"),
                "lags_applied_days": payload.get("lags_applied_days"),
            },
            "note": "bars and binding end condition pre-registered in 370ba41 before any data",
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
