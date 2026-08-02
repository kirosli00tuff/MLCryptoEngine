"""CLI: ``python -m research --date 2026-07-31 [--venue kraken]``.

End to end for each requested venue-day: extract trades (if missing),
extract samples, then train and evaluate per venue/symbol across all
requested dates, append the experiment log entry and the Phase B report
section. Idempotent: extraction overwrites deterministically; re-running a
date replaces its processed outputs and appends a new dated report section.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from data.config import REPO_ROOT, load_config
from data.recorder.reader import available_dates
from data.store import trade_partition_dir
from data.store.parquet_writer import PART_NAME
from data.trades.extract import extract_trades_day
from data.trades.parse import PARSERS
from research.features.engine import FEATURE_COLUMNS
from research.features.signing import SIGNING_METHOD
from research.labels.costs import cost_model_from_config
from research.labels.fixed_horizon import DEFAULT_HORIZONS_MS
from research.pipeline import (
    extract_samples,
    load_samples,
    samples_partition_dir,
    train_and_evaluate,
)
from research.report import append_phase_b_section
from research.validation.experiment_log import log_experiment


def _leakage_suite_status() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_leakage.py", "-q", "--no-header"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "no output"
    status = "PASS" if result.returncode == 0 else "FAIL"
    return f"{status} ({tail})"


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m research")
    parser.add_argument("--date", action="append", dest="dates", required=True)
    parser.add_argument("--venue", action="append", dest="venues")
    parser.add_argument("--skip-leakage-suite", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    requested = args.venues if args.venues else sorted(set(cfg.venues) & set(PARSERS))
    dates: list[str] = args.dates

    # A venue with no recorded data for these dates is skipped, not run: an
    # empty result block reads like a failed experiment when it is really an
    # absent one. Named explicitly so the omission is visible.
    venues = [v for v in requested if set(dates) & set(available_dates(cfg.raw_dir, v))]
    for venue in sorted(set(requested) - set(venues)):
        print(f"skipping {venue}: no recorded data for {', '.join(dates)}", flush=True)
    if not venues:
        print("no venue has recorded data for the requested dates")
        return 1

    results: dict[str, object] = {}
    for venue in venues:
        for date in dates:
            for symbol in cfg.venues[venue].symbols:
                trades_part = trade_partition_dir(cfg.processed_dir, venue, symbol, date)
                if not (trades_part / PART_NAME).is_file():
                    print(f"extracting trades {venue} {date} ...", flush=True)
                    extract_trades_day(cfg, venue, date)
                    break  # extraction covers all symbols of the venue-day
        for symbol in cfg.venues[venue].symbols:
            for date in dates:
                print(f"extracting samples {venue} {symbol} {date} ...", flush=True)
                extract_samples(cfg, venue, symbol, date)
            paths = [
                samples_partition_dir(cfg.processed_dir, venue, symbol, date) / PART_NAME
                for date in dates
            ]
            data = load_samples(paths)
            cost_models = {
                mode: cost_model_from_config(venue, cfg.venues[venue], mode)
                for mode in ("maker", "taker")
            }
            print(f"training {venue} {symbol} on {len(dates)} day(s) ...", flush=True)
            results[f"{venue} {symbol}"] = train_and_evaluate(data, cost_models)

    leakage = "skipped by flag" if args.skip_leakage_suite else _leakage_suite_status()
    cost_summary = " / ".join(
        f"{venue}: maker {cfg.venues[venue].fee_tiers[0].maker_bps} bps, "
        f"taker {cfg.venues[venue].fee_tiers[0].taker_bps} bps per leg (tier 0) + spread"
        for venue in venues
    )
    payload = {
        "dates": dates,
        "volatility_regimes": 1 if len(dates) <= 5 else len(dates) // 5,
        "sampling": "event bars, every 50 book updates",
        "feature_count": len(FEATURE_COLUMNS),
        "horizons_ms": list(DEFAULT_HORIZONS_MS),
        "tb_config": "pt/sl 2.0x rvol_30s, 30 s time limit",
        "cost_summary": cost_summary,
        "signing_methods": SIGNING_METHOD,
        "leakage_tests": leakage,
        "results": results,
    }
    append_phase_b_section(REPO_ROOT / "report.md", payload)
    entry = {k: v for k, v in payload.items() if k != "results"} | {"results": results}
    logged = log_experiment(entry)
    print(f"report.md updated · experiment logged: {logged['run_id']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
