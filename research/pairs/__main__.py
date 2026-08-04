"""CLI: ``python -m research.pairs`` — the whole C.10 study, end to end.

Order matters and is the order the report reads in: build a point-in-time
universe, screen it with the multiple-testing correction applied before anyone
looks at winners, trade the survivors strictly out of sample, then rank by
break-even cost. Every run appends to ``research/experiments.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from data.archive import binance, series, universe
from data.config import AppConfig, load_config
from research.pairs import backtest as bt
from research.pairs import screening, validation
from research.validation.experiment_log import log_experiment

START_PERIOD = "2021-08"
END_PERIOD = "2026-07"
UNIVERSE_SIZE = 60
# Two years to form, the rest to trade. Fixed before the first run.
FORMATION_BARS = 730
MIN_DAILY_OBSERVATIONS = 252
# A pair with a handful of trades has no statistical power whatever its Sharpe,
# so the headline ranking requires a floor. The unfiltered table is reported
# alongside — dropping the thin results silently would be its own dishonesty,
# and the gap between the two rankings is informative.
MIN_TRADES_FOR_HEADLINE = 20
# Below this the out-of-sample stretch is too short to have exercised the
# signal, regardless of trade count.
MIN_SCORED_BARS = 250

# Hyperliquid perps this project subscribed on 2026-08-03 (Stage C.9). A pair is
# executable only if BOTH legs are here: a pairs trade requires shorting one
# leg, and Canadian residents get spot-only, no-margin access on Kraken and
# Coinbase (CLAUDE.md hard constraint).
HYPERLIQUID_COINS = (
    "BTC",
    "ETH",
    "HYPE",
    "SOL",
    "PUMP",
    "DOT",
    "LINK",
    "ARB",
    "GMX",
    "MERL",
    "TNSR",
    "NOT",
)
EXECUTABLE_SYMBOLS = frozenset(f"{coin}USDT" for coin in HYPERLIQUID_COINS)


def _universe_cache(cfg: AppConfig) -> Path:
    return cfg.processed_dir / "pairs" / f"universe_{START_PERIOD}_{END_PERIOD}.json"


def load_or_build_universe(cfg: AppConfig, refresh: bool) -> universe.Universe:
    """Point-in-time universe, cached so a re-run needs no network."""
    cache = _universe_cache(cfg)
    if cache.is_file() and not refresh:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return universe.Universe(
            start_period=START_PERIOD,
            end_period=END_PERIOD,
            members=[universe.Member(**m) for m in payload["members"]],
            candidates_considered=payload["summary"]["candidates_considered"],
            listed_at_start=payload["summary"]["listed_at_start"],
        )
    built = universe.build(cfg, START_PERIOD, END_PERIOD, UNIVERSE_SIZE)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {"summary": built.summary(), "members": [asdict(m) for m in built.members]}, indent=1
        ),
        encoding="utf-8",
    )
    return built


def _pair_series(
    matrix: series.PriceMatrix, left: str, right: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    dates, a, b = matrix.overlap(left, right)
    if a.size == 0 or np.any(a <= 0) or np.any(b <= 0):
        return None
    return dates, a, b


# Secondary window for the executable question. The main sample starts in
# 2021-08, and seven of the twelve Hyperliquid perps did not exist on Binance
# then — so "no executable pair survives" over that window is partly an
# artifact of the window, and reporting it alone would be reporting a
# conclusion the design guaranteed. This shorter window starts after the bulk
# of them listed, trading sample length for a fair test of the set that can
# actually be shorted.
EXEC_START_PERIOD = "2024-06"
EXEC_FORMATION_BARS = 365


def executable_focus(cfg: AppConfig) -> dict[str, Any]:
    """Screen only the Hyperliquid-executable set, on a window where it exists."""
    periods = binance.months_between(EXEC_START_PERIOD, END_PERIOD)
    listed: list[str] = []
    never: dict[str, str] = {}
    for symbol in sorted(EXECUTABLE_SYMBOLS):
        available = binance.available_periods(symbol, "1d")
        if available and available[0] <= EXEC_START_PERIOD:
            listed.append(symbol)
        else:
            never[symbol] = available[0] if available else "never listed on Binance"

    # These symbols are mostly outside the main universe, so nothing has
    # downloaded them yet. build_matrix reads only what is cached, so without
    # this the focus analysis would silently test five symbols and report it as
    # nine — which is exactly what the first run did.
    focus = universe.Universe(start_period=EXEC_START_PERIOD, end_period=END_PERIOD)
    universe.fetch_history(cfg, focus, "1d", symbols=listed)

    matrix = series.build_matrix(cfg, listed, "1d", periods, min_observations=200)
    total = len(matrix.dates_ns)
    if total <= EXEC_FORMATION_BARS + 2:
        return {"error": f"only {total} bars in the executable window"}

    formation = screening.screen(matrix, 0, EXEC_FORMATION_BARS, min_overlap=200)
    holdout_start_ns = int(matrix.dates_ns[EXEC_FORMATION_BARS])
    rows: list[dict[str, Any]] = []
    for pair in formation.pairs:
        legs = _pair_series(matrix, pair.left, pair.right)
        if legs is None:
            continue
        pair_dates, y_close, x_close = legs
        start = int(np.searchsorted(pair_dates, holdout_start_ns, side="left"))
        result = bt.run_pair(pair.left, pair.right, y_close, x_close, start=start)
        if result is None:
            continue
        result.executable = True
        rows.append(
            {
                **result.row(),
                "eg_p_value": round(pair.eg.p_value, 5),
                "survives_bh": pair.key in {p.key for p in formation.survivors()},
                "johansen_rejects": bool(pair.joh and pair.joh.rejects_no_cointegration),
            }
        )
    return {
        "window": f"{EXEC_START_PERIOD}..{END_PERIOD}",
        "hyperliquid_coins_subscribed": len(HYPERLIQUID_COINS),
        "available_on_binance_at_window_start": listed,
        "unavailable_with_first_month": never,
        "bars": total,
        # Reported, not silently dropped: a symbol that listed in time but did
        # not reach the matrix has still been removed from the executable test,
        # and the reason belongs in the record next to the result.
        "symbols_in_matrix": matrix.symbols,
        "symbols_excluded_from_matrix": matrix.excluded,
        "formation": formation.summary(),
        "pairs": sorted(rows, key=lambda r: r["break_even_bps"], reverse=True),
    }


def run(cfg: AppConfig, refresh: bool) -> dict[str, Any]:
    picked = load_or_build_universe(cfg, refresh)
    periods = binance.months_between(START_PERIOD, END_PERIOD)
    matrix = series.build_matrix(
        cfg, picked.symbols, "1d", periods, min_observations=MIN_DAILY_OBSERVATIONS
    )
    total_bars = len(matrix.dates_ns)
    first, last = int(matrix.dates_ns[0]), int(matrix.dates_ns[-1])
    form_end = series.date_str(int(matrix.dates_ns[FORMATION_BARS - 1]))
    hold_start = series.date_str(int(matrix.dates_ns[FORMATION_BARS]))

    formation = screening.screen(
        matrix, 0, FORMATION_BARS, window_label=f"{series.date_str(first)}..{form_end}"
    )
    holdout = screening.screen(
        matrix, FORMATION_BARS, total_bars, window_label=f"{hold_start}..{series.date_str(last)}"
    )
    persist = screening.persistence(formation, holdout)

    # Traded set: formation-window BH survivors only. Selecting on the same
    # window that is then traded would be the look-ahead this stage exists to
    # avoid, so the trading stretch begins where the formation window ends.
    holdout_start_ns = int(matrix.dates_ns[FORMATION_BARS])
    results: list[bt.PairBacktest] = []
    for pair in formation.survivors():
        legs = _pair_series(matrix, pair.left, pair.right)
        if legs is None:
            continue
        pair_dates, y_close, x_close = legs
        # Map the holdout's START DATE into this pair's own overlapping index.
        # Counting back from the end instead would put every pair whose overlap
        # is shorter than the holdout — i.e. every pair with a leg that died —
        # to trade inside the formation window it was selected on. That is
        # look-ahead, and it is not subtle in its effects: it produced the
        # highest-ranked result in the first run of this study, a pair with a
        # leg dead since 2022-05 showing 223% annualised from four trades.
        overlap_start = int(np.searchsorted(pair_dates, holdout_start_ns, side="left"))
        result = bt.run_pair(pair.left, pair.right, y_close, x_close, start=overlap_start)
        if result is None:
            continue
        result.executable = pair.left in EXECUTABLE_SYMBOLS and pair.right in EXECUTABLE_SYMBOLS
        results.append(result)

    dispersion = validation.sharpe_dispersion(results)
    trials = formation.tested
    ranked = sorted(results, key=lambda r: r.break_even_bps, reverse=True)
    powered = [
        r for r in ranked if r.trades >= MIN_TRADES_FOR_HEADLINE and r.bars >= MIN_SCORED_BARS
    ]
    executable = [r for r in results if r.executable]
    best = powered[0] if powered else None
    best_executable = max(executable, key=lambda r: r.break_even_bps) if executable else None

    payload: dict[str, Any] = {
        "universe": picked.summary(),
        "matrix": {
            "bars": total_bars,
            "first_date": series.date_str(first),
            "last_date": series.date_str(last),
            "formation_ends": form_end,
            "holdout_starts": hold_start,
            "symbols_kept": len(matrix.symbols),
            "symbols_excluded": matrix.excluded,
            "discontinuities": [d.describe() for d in matrix.discontinuities],
        },
        "formation": formation.summary(),
        "holdout": holdout.summary(),
        "persistence": persist,
        "backtest": {
            "signal": {
                "beta_window_bars": bt.BETA_WINDOW,
                "z_window_bars": bt.Z_WINDOW,
                "entry_z": bt.ENTRY_Z,
                "exit_z": bt.EXIT_Z,
                "max_hold_bars": bt.MAX_HOLD_BARS,
                "fixed_a_priori": True,
            },
            "cost_convention": (
                "gross exposure normalised to one unit across both legs; cost_bps is a "
                "round-trip rate on that unit. Hyperliquid maker 3.0 bps, Kraken spot "
                "maker 80.0 bps."
            ),
            "pairs_traded": len(results),
            "pairs_executable_on_hyperliquid": len(executable),
            "embargo_ns_for_holding": validation.embargo_ns_for_holding(bt.MAX_HOLD_BARS),
            "total_trades": sum(r.trades for r in results),
            "median_trades_per_pair": (
                float(np.median([r.trades for r in results])) if results else 0.0
            ),
            "profitable_gross": sum(1 for r in results if r.gross_return > 0),
            "profitable_net_hyperliquid": sum(
                1 for r in results if r.net_return(bt.HYPERLIQUID_MAKER_BPS) > 0
            ),
            "profitable_net_kraken": sum(
                1 for r in results if r.net_return(bt.KRAKEN_SPOT_MAKER_BPS) > 0
            ),
            "power_floor": {
                "min_trades": MIN_TRADES_FOR_HEADLINE,
                "min_scored_bars": MIN_SCORED_BARS,
                "pairs_meeting_floor": len(powered),
                "pairs_below_floor": len(ranked) - len(powered),
            },
            "top_by_break_even_powered": [r.row() for r in powered[:15]],
            "top_by_break_even_unfiltered": [r.row() for r in ranked[:15]],
            "executable_rows": [
                r.row() for r in sorted(executable, key=lambda r: r.break_even_bps, reverse=True)
            ],
        },
        "deflation": {
            "sharpe_dispersion_per_bar": round(dispersion, 5),
            "best_overall": (
                {**best.row(), **validation.deflate(best, trials, dispersion)} if best else None
            ),
            "best_executable": (
                {**best_executable.row(), **validation.deflate(best_executable, trials, dispersion)}
                if best_executable
                else None
            ),
        },
    }
    if best is not None:
        payload["backtest"]["walk_forward_best"] = [
            asdict(f) for f in validation.walk_forward(best, test_bars=90)
        ]
    payload["executable_focus"] = executable_focus(cfg)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.pairs")
    parser.add_argument(
        "--refresh-universe",
        action="store_true",
        help="rebuild the point-in-time universe instead of using the cache",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the JSON payload here")
    args = parser.parse_args(argv)

    cfg = load_config()
    payload = run(cfg, args.refresh_universe)

    log_experiment(
        {
            "stage": "C.10",
            "study": "cointegration pairs trading, daily bars",
            "source": "binance_spot_klines (kind=archive, free public dumps)",
            "dates": [payload["matrix"]["first_date"], payload["matrix"]["last_date"]],
            "universe": payload["universe"],
            "formation": payload["formation"],
            "holdout": payload["holdout"],
            "persistence": payload["persistence"],
            "signal": payload["backtest"]["signal"],
            "cost_summary": payload["backtest"]["cost_convention"],
            "results": {
                "pairs_traded": payload["backtest"]["pairs_traded"],
                "executable": payload["backtest"]["pairs_executable_on_hyperliquid"],
                "total_trades": payload["backtest"]["total_trades"],
                "profitable_net_hyperliquid": payload["backtest"]["profitable_net_hyperliquid"],
                "deflation": payload["deflation"],
            },
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
