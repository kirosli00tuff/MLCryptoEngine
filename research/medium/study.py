"""Walk-forward ridge over the registered grid, and the six-bar verdict.

The model is fixed at registration to kill the search dimension: ridge with
λ = 1.0, pooled across BTC and ETH, refit each week on an expanding window.
Purge and embargo are one inequality — a training week ``s`` with an h-week
label is admissible for a decision at week ``t`` only if ``s + 2h <= t``: the
first ``h`` guarantees the label resolved before the decision (purge), the
second is the registered embargo at the horizon's own length. That inequality
is a pure function (:func:`train_indices`) precisely so a test can hold it
down directly rather than trusting the loop that uses it.

Positions are the sign of the prediction (long-only clips to cash), half the
gross per asset, weekly rebalance. Costs are charged on traded notional:
Hyperliquid legs at 1.5 bps/side for every cell (the registered bar column),
and long-only cells additionally report spot at 25 and 40 bps/side — the two
Kraken schedules the audit found disagreeing by roughly two times.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.pairs.validation import deflated_sharpe

WEEKS_PER_YEAR = 52
RISK_FREE_ANNUAL = 0.04
CASH_STAKING_FLOOR_PCT = 4.5
RIDGE_LAMBDA = 1.0
MIN_TRAIN_ROWS = 104  # 52 weeks x 2 assets, pooled
BPS = 1e-4
FEE_HL = 1.5
FEE_SPOT_LOW = 25.0
FEE_SPOT_HIGH = 40.0
HORIZONS_WEEKS = (1, 2, 4, 8)
VARIANTS = ("long_only", "long_short")


def train_indices(n_weeks: int, t_idx: int, horizon_weeks: int) -> list[int]:
    """Admissible training weeks for a decision at ``t_idx``: ``s + 2h <= t``."""
    return list(range(0, max(0, min(n_weeks, t_idx - 2 * horizon_weeks + 1))))


def ridge_fit(
    x: NDArray[np.float64], y: NDArray[np.float64], lam: float = RIDGE_LAMBDA
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Standardise on the given rows, solve ridge; returns (beta, mean, std)."""
    mean = np.nanmean(x, axis=0)
    std = np.nanstd(x, axis=0)
    std[~np.isfinite(std) | (std == 0.0)] = 1.0
    mean[~np.isfinite(mean)] = 0.0
    z = (x - mean) / std
    beta = np.linalg.solve(z.T @ z + lam * np.eye(z.shape[1]), z.T @ y)
    return beta, mean, std


def sharpe_weekly(weekly: NDArray[np.float64], rf_annual: float = RISK_FREE_ANNUAL) -> float:
    if weekly.size < 8:
        return 0.0
    sigma = float(np.std(weekly, ddof=1))
    if sigma <= 0.0:
        return 0.0
    excess = float(np.mean(weekly)) - rf_annual / WEEKS_PER_YEAR
    return excess / sigma * math.sqrt(WEEKS_PER_YEAR)


def beta_alpha_weekly(
    strategy: NDArray[np.float64], benchmark: NDArray[np.float64]
) -> dict[str, float]:
    n = int(min(strategy.size, benchmark.size))
    s, b = strategy[:n], benchmark[:n]
    var_b = float(np.var(b, ddof=1))
    if n < 30 or var_b <= 0.0:
        return {"beta": 0.0, "alpha_annual": 0.0, "alpha_t": 0.0, "r_squared": 0.0}
    beta = float(np.cov(s, b, ddof=1)[0, 1]) / var_b
    alpha_w = float(np.mean(s)) - beta * float(np.mean(b))
    resid = s - (alpha_w + beta * b)
    s2 = float(np.sum(resid**2)) / (n - 2)
    mean_b = float(np.mean(b))
    se = math.sqrt(s2 * (1.0 / n + mean_b**2 / ((n - 1) * var_b)))
    total = float(np.sum((s - np.mean(s)) ** 2))
    return {
        "beta": beta,
        "alpha_annual": alpha_w * WEEKS_PER_YEAR,
        "alpha_t": alpha_w / se if se > 0 else 0.0,
        "r_squared": 1.0 - float(np.sum(resid**2)) / total if total > 0 else 0.0,
    }


def max_drawdown(weekly: NDArray[np.float64]) -> float:
    if weekly.size == 0:
        return 0.0
    equity = np.cumsum(weekly)
    return float(np.min(equity - np.maximum.accumulate(equity)))


@dataclass
class CellInput:
    """Everything one grid cell consumes, aligned on the weekly grid."""

    weeks_ms: NDArray[np.int64]
    x_by_asset: dict[str, NDArray[np.float64]]  # (n_weeks, k) each
    label_by_asset: dict[str, NDArray[np.float64]]  # h-week forward return
    next_week_return: dict[str, NDArray[np.float64]]  # t -> t+1 realised
    btc_weekly_return: NDArray[np.float64]
    btc_trend_up: NDArray[np.bool_]  # trailing-30d BTC trend sign at each week


def simulate_cell(
    data: CellInput, horizon_weeks: int, variant: str
) -> dict[str, NDArray[np.float64]] | None:
    """One cell's walk-forward path. Per-week arrays, or None if unscoreable."""
    assets = sorted(data.x_by_asset)
    n = int(data.weeks_ms.size)
    positions = {a: np.zeros(n) for a in assets}
    scored = np.zeros(n, dtype=bool)

    for t in range(n - 1):  # the final week has no next-week return to earn
        candidates = train_indices(n, t, horizon_weeks)
        rows_x, rows_y = [], []
        for a in assets:
            xa, ya = data.x_by_asset[a], data.label_by_asset[a]
            for s in candidates:
                if np.all(np.isfinite(xa[s])) and np.isfinite(ya[s]):
                    rows_x.append(xa[s])
                    rows_y.append(ya[s])
        if len(rows_x) < MIN_TRAIN_ROWS:
            continue
        beta, mean, std = ridge_fit(np.asarray(rows_x), np.asarray(rows_y))
        live = False
        for a in assets:
            row = data.x_by_asset[a][t]
            if not np.all(np.isfinite(row)):
                positions[a][t] = 0.0
                continue
            pred = float(((row - mean) / std) @ beta)
            pos = math.copysign(1.0, pred) if pred != 0 else 0.0
            if variant == "long_only":
                pos = max(pos, 0.0)
            positions[a][t] = pos
            live = True
        scored[t] = live

    if int(scored.sum()) < 30:
        return None

    first = int(np.argmax(scored))
    idx = np.arange(first, n - 1)
    ret = np.zeros(idx.size)
    traded = np.zeros(idx.size)
    prev = dict.fromkeys(assets, 0.0)
    for j, t in enumerate(int(i) for i in idx):
        for a in assets:
            pos = positions[a][t]
            ret[j] += 0.5 * pos * data.next_week_return[a][t]
            traded[j] += 0.5 * abs(pos - prev[a])
            prev[a] = pos
    traded[-1] += sum(0.5 * abs(prev[a]) for a in assets)  # final unwind

    return {
        "weeks_ms": data.weeks_ms[idx].astype(np.float64),
        "gross": ret,
        "traded": traded,
        "btc": data.btc_weekly_return[idx],
        "trend_up": data.btc_trend_up[idx].astype(np.float64),
        "net_exposure": np.asarray([sum(0.5 * positions[a][t] for a in assets) for t in idx]),
    }


def cell_metrics(
    path: dict[str, NDArray[np.float64]],
    klass: str,
    horizon_weeks: int,
    variant: str,
    n_trials: int,
    sharpe_std: float,
) -> dict[str, Any]:
    gross, traded, btc = path["gross"], path["traded"], path["btc"]
    years = gross.size / WEEKS_PER_YEAR
    net_hl = gross - traded * FEE_HL * BPS

    row: dict[str, Any] = {
        "class": klass,
        "horizon_weeks": horizon_weeks,
        "variant": variant,
        "scored_weeks": int(gross.size),
        "years": round(years, 2),
        "mean_net_exposure": round(float(np.mean(path["net_exposure"])), 3),
        "round_trips_per_year": round(float(traded.sum()) / 2.0 / years, 2) if years else 0.0,
        "gross_annual_return_pct": round(100 * float(np.mean(gross)) * WEEKS_PER_YEAR, 2),
        "gross_sharpe": round(sharpe_weekly(gross), 3),
        "net_annual_return_pct_hl": round(100 * float(np.mean(net_hl)) * WEEKS_PER_YEAR, 2),
        "net_sharpe_hl": round(sharpe_weekly(net_hl), 3),
        "max_drawdown_pct": round(100 * max_drawdown(gross), 2),
        "break_even_fee_bps_per_side": round(float(gross.sum()) / float(traded.sum()) / BPS, 2)
        if traded.sum() > 0 and gross.sum() > 0
        else 0.0,
    }
    if variant == "long_only":
        for name, fee in (("spot25", FEE_SPOT_LOW), ("spot40", FEE_SPOT_HIGH)):
            net = gross - traded * fee * BPS
            row[f"net_annual_return_pct_{name}"] = round(
                100 * float(np.mean(net)) * WEEKS_PER_YEAR, 2
            )
            row[f"net_sharpe_{name}"] = round(sharpe_weekly(net), 3)

    row.update({f"{k}_vs_btc": round(v, 3) for k, v in beta_alpha_weekly(net_hl, btc).items()})
    up = path["trend_up"] > 0.5
    row["up_weeks"] = int(up.sum())
    row["down_weeks"] = int((~up).sum())
    row["up_annual_return_pct"] = (
        round(100 * float(np.mean(net_hl[up])) * WEEKS_PER_YEAR, 2) if up.any() else None
    )
    row["down_annual_return_pct"] = (
        round(100 * float(np.mean(net_hl[~up])) * WEEKS_PER_YEAR, 2) if (~up).any() else None
    )

    sigma = float(np.std(net_hl, ddof=1))
    if sigma > 0:
        per_bar = float(np.mean(net_hl)) / sigma
        centred = (net_hl - float(np.mean(net_hl))) / sigma
        row["deflated_sharpe"] = round(
            deflated_sharpe(
                sharpe=per_bar,
                n_obs=int(net_hl.size),
                n_trials=n_trials,
                skew=float(np.mean(centred**3)),
                kurtosis=float(np.mean(centred**4)),
                sharpe_std=sharpe_std,
            ),
            4,
        )
    else:
        row["deflated_sharpe"] = 0.0

    row["btc_sharpe_same_window"] = round(sharpe_weekly(btc), 3)
    row["btc_annual_return_pct_same_window"] = round(100 * float(np.mean(btc)) * WEEKS_PER_YEAR, 2)
    return row


def verdict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The six registered bars, applied cell by cell, consistency by class."""
    by_class: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_class.setdefault(str(row["class"]), []).append(row)
    consistency = {
        klass: sum(1 for r in group if float(r["net_sharpe_hl"]) > 0) / len(group)
        for klass, group in by_class.items()
    }

    passing: list[dict[str, Any]] = []
    near: list[dict[str, Any]] = []
    for row in rows:
        bars = {
            "1_net_sharpe_ge_btc": float(row["net_sharpe_hl"])
            >= float(row["btc_sharpe_same_window"]),
            "2_alpha_pos_t2": float(row["alpha_annual_vs_btc"]) > 0
            and float(row["alpha_t_vs_btc"]) >= 2.0,
            "3_dsr_ge_095": float(row["deflated_sharpe"]) >= 0.95,
            "4_net_return_gt_floor": float(row["net_annual_return_pct_hl"])
            > CASH_STAKING_FLOOR_PCT,
            # BTC/ETH only: long-only executes as Kraken/Coinbase spot and the
            # long-short shorts exist on Hyperliquid, so every registered cell
            # is executable as specced — the bar exists for future universes.
            "5_executable": True,
            "6_class_consistency_ge_2of3": consistency.get(str(row["class"]), 0.0) >= 2 / 3,
        }
        entry = {"cell": f"{row['class']}/h{row['horizon_weeks']}w/{row['variant']}", **bars}
        met = sum(1 for v in bars.values() if v)
        if met == 6:
            passing.append(entry)
        elif met >= 4:
            near.append(entry)

    return {
        "outcome": "PASS" if passing else "FAIL",
        "cells_passing_all_six": passing,
        "cells_meeting_4_or_5": near,
        "class_consistency_positive_fraction": {
            k: round(v, 3) for k, v in sorted(consistency.items())
        },
        "bars_pre_registered_in": "progress.md, commit 370ba41, before any data was touched",
        "end_condition": (
            "binding, agreed in advance: FAIL ends the alpha search of this project by decision"
        ),
    }
