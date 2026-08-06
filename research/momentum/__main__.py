"""CLI: ``python -m research.momentum`` — the whole C.16 study.

Order is the registered order: universe reused from C.10, the full
specification grid with nothing dropped, the beta/alpha decomposition against
buy-and-hold BTC, deflated Sharpe corrected for the twelve specifications
tried, then costs and the executable subset. Every threshold this scores
itself against was committed in 88b69d8 before anything below ran.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from data.archive import binance, series
from data.archive import hyperliquid as hl
from data.config import AppConfig, load_config
from research.momentum import engine
from research.pairs.validation import deflated_sharpe
from research.validation.experiment_log import log_experiment

# C.10's sample, reused verbatim.
START_PERIOD = "2021-08"
END_PERIOD = "2026-07"
UNIVERSE_CACHE = "pairs/universe_{start}_{end}.json"
MIN_OBSERVATIONS = 200

# The registered grid (progress.md, commit 88b69d8). All cells reported.
LOOKBACKS = (14, 30, 90, 180)
HOLDS = (7, 30, 90)
PRIMARY = engine.Spec(lookback_days=90, hold_days=30)
N_TRIALS = len(LOOKBACKS) * len(HOLDS)

BENCHMARK_SYMBOL = "BTCUSDT"
# Per side. Sources: config/venues.yaml hyperliquid base tier 1.5 bps maker
# (verified 2026-08-01) and kraken base tier 40 bps maker (corrected
# 2026-08-01) — the registered 3 bps and 80 bps round trips.
FEE_SCENARIOS = {"hl": 1.5, "kraken": 40.0}
DSR_FEE = 1.5  # deflated Sharpe is computed on net-of-3bps-RT daily returns


def _load_universe(cfg: AppConfig) -> list[dict[str, Any]]:
    """C.10's cached members, verbatim. A missing cache is an error, not a rebuild."""
    path = cfg.processed_dir / UNIVERSE_CACHE.format(start=START_PERIOD, end=END_PERIOD)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. C.16 reuses C.10's universe construction; rebuilding from "
            "today's listings would reintroduce the survivorship bias C.10 removed. Run "
            "`python -m research.pairs` first if the cache was deleted."
        )
    payload = json.loads(path.read_text())
    members: list[dict[str, Any]] = payload["members"]
    return members


def _size_by_month(members: list[dict[str, Any]]) -> dict[str, int]:
    months = binance.months_between(START_PERIOD, END_PERIOD)
    return {
        month: sum(1 for m in members if m["first_period"] <= month <= m["last_period"])
        for month in months
    }


def _executable_now(cfg: AppConfig, symbols: list[str]) -> dict[str, Any]:
    """Which universe members have a live Hyperliquid perp today.

    Mapping: strip USDT; Binance's 1000X spot tickers map to Hyperliquid's kX
    convention. Kraken adds nothing here — its configured spot symbols are
    BTC/ETH only and spot cannot short, so it is a bound in the cost table,
    not an execution venue for this book.
    """
    live = {a.name for a in hl.fetch_universe(cfg) if not a.is_delisted}
    matched: list[str] = []
    for symbol in symbols:
        base = symbol.removesuffix("USDT")
        candidates = {base, f"k{base[4:]}"} if base.startswith("1000") else {base}
        if candidates & live:
            matched.append(symbol)
    return {
        "hyperliquid_live_perps": len(live),
        "universe_members_with_live_perp": len(matched),
        "matched_symbols": matched,
        "unmatched": sorted(set(symbols) - set(matched)),
    }


def _btc_windows(matrix: series.PriceMatrix, spec: engine.Spec) -> tuple[np.ndarray, np.ndarray]:
    """Benchmark closes and daily returns over exactly the spec's scored window."""
    closes = matrix.column(BENCHMARK_SYMBOL)
    window = closes[spec.lookback_days :]
    prev = closes[spec.lookback_days - 1 : -1]
    with np.errstate(invalid="ignore", divide="ignore"):
        daily = np.where(prev > 0, window / prev - 1.0, np.nan)
    return window, np.nan_to_num(daily, nan=0.0)


def _deflate(net_daily: np.ndarray, sharpe_std: float) -> dict[str, float]:
    sigma = float(np.std(net_daily, ddof=1))
    if sigma <= 0:
        return {"per_bar_sharpe": 0.0, "deflated_sharpe": 0.0}
    per_bar = float(np.mean(net_daily)) / sigma
    centred = (net_daily - float(np.mean(net_daily))) / sigma
    return {
        "per_bar_sharpe": round(per_bar, 5),
        "deflated_sharpe": round(
            deflated_sharpe(
                sharpe=per_bar,
                n_obs=int(net_daily.size),
                n_trials=N_TRIALS,
                skew=float(np.mean(centred**3)),
                kurtosis=float(np.mean(centred**4)),
                sharpe_std=sharpe_std,
            ),
            4,
        ),
    }


def run(cfg: AppConfig) -> dict[str, Any]:
    members = _load_universe(cfg)
    symbols = [m["symbol"] for m in members]
    deaths = [m["symbol"] for m in members if m["last_period"] < END_PERIOD]
    months = binance.months_between(START_PERIOD, END_PERIOD)
    matrix = series.build_matrix(cfg, symbols, "1d", months, min_observations=MIN_OBSERVATIONS)
    if BENCHMARK_SYMBOL not in matrix.symbols:
        return {"error": f"{BENCHMARK_SYMBOL} missing from the matrix; benchmark impossible"}

    closes = matrix.closes
    specs = [engine.Spec(lb, hold) for lb in LOOKBACKS for hold in HOLDS]

    results: dict[str, engine.MomentumResult] = {}
    rows: list[dict[str, Any]] = []
    for spec in specs:
        result = engine.simulate(matrix.dates_ns, closes, spec)
        bench_closes, bench_daily = _btc_windows(matrix, spec)
        rows.append(
            engine.SpecMetrics.compute(result, bench_daily, bench_closes, FEE_SCENARIOS).rows
        )
        results[spec.key] = result

    # Deflated Sharpe: C.10's estimator, n_trials = the registered grid size,
    # dispersion measured across the very specifications searched.
    per_bar = []
    for spec in specs:
        net = results[spec.key].net_daily(DSR_FEE)
        sigma = float(np.std(net, ddof=1))
        per_bar.append(float(np.mean(net)) / sigma if sigma > 0 else 0.0)
    sharpe_std = float(np.std(np.asarray(per_bar), ddof=1))
    for spec, row in zip(specs, rows, strict=True):
        row.update(_deflate(results[spec.key].net_daily(DSR_FEE), sharpe_std))

    # Benchmark and verdict on the primary spec's window.
    primary_row = next(r for r in rows if r["spec"] == PRIMARY.key)
    bench_closes, bench_daily = _btc_windows(matrix, PRIMARY)
    btc = {
        "window_days": int(bench_daily.size),
        "annual_return_pct": round(100 * float(np.mean(bench_daily)) * engine.DAYS_PER_YEAR, 2),
        "annual_vol_pct": round(
            100 * float(np.std(bench_daily, ddof=1)) * float(np.sqrt(engine.DAYS_PER_YEAR)), 2
        ),
        "sharpe": round(engine.sharpe(bench_daily), 3),
        "max_drawdown_pct": round(100 * engine.max_drawdown(bench_daily), 2),
    }

    positive_net = sum(1 for r in rows if float(r["net_sharpe_hl"]) > 0)
    beats_btc = float(primary_row["net_sharpe_hl"]) >= float(btc["sharpe"])
    dsr = float(primary_row["deflated_sharpe"])
    alpha_ok = (
        float(primary_row["alpha_annual_vs_btc"]) > 0 and float(primary_row["alpha_t_vs_btc"]) >= 2
    )
    beats_zero = float(primary_row["net_sharpe_hl"]) > 0
    beta_disguise = beats_zero and (
        not beats_btc
        or (
            float(primary_row["alpha_annual_vs_btc"]) <= 0
            and float(primary_row["beta_vs_btc"]) >= 0.5
        )
    )
    if beats_btc and dsr >= 0.95 and alpha_ok and positive_net >= 8:
        outcome = "PASS"
    elif beats_btc and dsr > 0.5:
        outcome = "WEAK"
    elif beta_disguise:
        outcome = "BETA IN DISGUISE"
    else:
        outcome = "FAIL"

    literal = [
        r["spec"]
        for r in rows
        if float(r["net_sharpe_hl"]) >= float(btc["sharpe"]) and float(r["deflated_sharpe"]) > 0.5
    ]

    executable = _executable_now(cfg, list(matrix.symbols))
    exec_idx = [matrix.symbols.index(s) for s in executable["matched_symbols"]]
    exec_row: dict[str, Any] | None = None
    if len(exec_idx) >= engine.MIN_NAMES:
        sub = engine.simulate(matrix.dates_ns, closes[:, exec_idx], PRIMARY)
        exec_row = engine.SpecMetrics.compute(sub, bench_daily, bench_closes, FEE_SCENARIOS).rows
        exec_row.update(_deflate(sub.net_daily(DSR_FEE), sharpe_std))

    return {
        "premise": (
            "Time-series momentum: recent winners keep winning over weeks to months. Long "
            "past-L-day winners, short past losers, equal weight, on C.10's "
            "survivorship-free daily universe. Expected to fail; the value is closing the "
            "trend-following family cheaply."
        ),
        "pre_registration_commit": "88b69d8",
        "universe": {
            "source": "data/processed/pairs/universe_2021-08_2026-07.json (C.10, reused verbatim)",
            "members": len(members),
            "in_matrix": len(matrix.symbols),
            "excluded": matrix.excluded,
            "died_in_sample": len(deaths),
            "died_symbols": deaths,
            "size_by_month": _size_by_month(members),
        },
        "grid": {
            "lookbacks_days": list(LOOKBACKS),
            "holds_days": list(HOLDS),
            "n_specifications": N_TRIALS,
            "primary": PRIMARY.key,
            "cross_spec_per_bar_sharpe_std": round(sharpe_std, 5),
        },
        "specifications": rows,
        "consistency": {
            "positive_net_hl_sharpe": positive_net,
            "of": N_TRIALS,
            "median_net_hl_sharpe": round(
                float(np.median([float(r["net_sharpe_hl"]) for r in rows])), 3
            ),
            "median_gross_sharpe": round(
                float(np.median([float(r["gross_sharpe"]) for r in rows])), 3
            ),
        },
        "btc_buy_and_hold": btc,
        "primary": primary_row,
        "executable": executable,
        "primary_on_executable_subset": exec_row,
        "verdict": {
            "outcome": outcome,
            "beats_btc_risk_adjusted": beats_btc,
            "deflated_sharpe_primary": dsr,
            "alpha_positive_t2": alpha_ok,
            "consistency_met": positive_net >= 8,
            "specs_meeting_literal_criterion": literal,
            "bars_pre_registered_in": "progress.md, commit 88b69d8, before any result",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.momentum")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = run(load_config())
    log_experiment(
        {
            "stage": "C.16",
            "study": "time-series momentum on the C.10 daily archive",
            "source": "binance_spot_klines archive, C.10 universe cache reused (nothing bought)",
            "dates": [START_PERIOD, END_PERIOD],
            "cost_summary": json.dumps(FEE_SCENARIOS) + " bps/side; DSR on net-of-hl",
            "results": {
                "verdict": payload.get("verdict"),
                "consistency": payload.get("consistency"),
                "primary": {
                    k: payload.get("primary", {}).get(k)
                    for k in (
                        "spec",
                        "gross_sharpe",
                        "net_sharpe_hl",
                        "net_sharpe_kraken",
                        "beta_vs_btc",
                        "alpha_annual_vs_btc",
                        "alpha_t_vs_btc",
                        "deflated_sharpe",
                        "break_even_fee_bps_per_side",
                    )
                },
                "btc": payload.get("btc_buy_and_hold"),
            },
            "note": "grid and bars pre-registered in commit 88b69d8 before any computation",
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
