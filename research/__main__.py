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

import numpy as np

from data.config import REPO_ROOT, AppConfig, load_config
from data.databento.adapter import VENUE as VENDOR_VENUE
from data.recorder.reader import available_dates
from data.store import book_partition_dir, trade_partition_dir
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
    training_columns,
)
from research.report import append_phase_b_section
from research.validation.experiment_log import log_experiment
from research.validation.walk_forward import walk_forward_capacity


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


def _dates_available(cfg: AppConfig, venue: str, symbol: str | None = None) -> list[str]:
    """Dates this venue has data for, whichever way its data arrived.

    Recorder venues are asked about raw captures. The vendor venue has no
    recorder and never will — its data is bought and ingested — so it is
    asked about ingested book partitions instead. Gating it on ``raw_dir``
    would report CME as "no recorded data" while 224 million ingested events
    sat on disk.
    """
    if venue == VENDOR_VENUE:
        symbols = [symbol] if symbol is not None else cfg.venues[venue].symbols
        found: set[str] = set()
        for symbol in symbols:
            # .parent is the symbol directory holding the date= partitions;
            # .parent.parent is the venue directory holding symbol= dirs,
            # which contains no date= entries at all and silently yields an
            # empty date set — reported upstream as "no recorded data".
            root = book_partition_dir(cfg.processed_dir, venue, symbol, "x").parent
            if root.is_dir():
                found |= {
                    p.name.removeprefix("date=")
                    for p in root.iterdir()
                    if p.name.startswith("date=") and (p / PART_NAME).is_file()
                }
        return sorted(found)
    return available_dates(cfg.raw_dir, venue)


def _cost_summary(cfg: AppConfig, venues: list[str]) -> str:
    """One line naming every cost assumption, in the units it is charged in."""
    parts: list[str] = []
    for venue in venues:
        tier = cfg.venues[venue].fee_tiers[0]
        if tier.fee_usd_per_contract_per_side is not None:
            multipliers = {
                symbol: meta.contract_multiplier
                for symbol, meta in cfg.venues[venue].instruments.items()
                if meta.contract_multiplier is not None
            }
            parts.append(
                f"{venue}: ${tier.fee_usd_per_contract_per_side:.2f} per contract per side "
                f"(= ${2 * tier.fee_usd_per_contract_per_side:.2f} round turn), converted to "
                f"bps at each sample's own notional (price x multiplier {multipliers}); "
                f"taker additionally pays the touch spread"
            )
        else:
            parts.append(
                f"{venue}: maker {tier.maker_bps} bps, taker {tier.taker_bps} bps "
                "per leg (tier 0) + spread"
            )
    return " / ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m research")
    parser.add_argument("--date", action="append", dest="dates", required=True)
    parser.add_argument("--venue", action="append", dest="venues")
    parser.add_argument("--skip-leakage-suite", action="store_true")
    parser.add_argument(
        "--sample-stride",
        type=int,
        default=1,
        help=(
            "keep every nth sample when training (default 1 = all). Coarsens the "
            "event bar by this factor; recorded in the report and experiment log "
            "because it changes the experiment."
        ),
    )
    args = parser.parse_args()

    cfg = load_config()
    requested = args.venues if args.venues else sorted(set(cfg.venues) & set(PARSERS))
    dates: list[str] = args.dates

    # A venue with no recorded data for these dates is skipped, not run: an
    # empty result block reads like a failed experiment when it is really an
    # absent one. Named explicitly so the omission is visible.
    venues = [v for v in requested if set(dates) & set(_dates_available(cfg, v))]
    for venue in sorted(set(requested) - set(venues)):
        print(f"skipping {venue}: no recorded data for {', '.join(dates)}", flush=True)
    if not venues:
        print("no venue has recorded data for the requested dates")
        return 1

    results: dict[str, object] = {}
    for venue in venues:
        for date in dates:
            # The vendor venue's trades are ingested from purchased DBN, not
            # extracted from a raw capture that does not exist.
            if venue == VENDOR_VENUE:
                continue
            for symbol in cfg.venues[venue].symbols:
                trades_part = trade_partition_dir(cfg.processed_dir, venue, symbol, date)
                if not (trades_part / PART_NAME).is_file():
                    print(f"extracting trades {venue} {date} ...", flush=True)
                    extract_trades_day(cfg, venue, date)
                    break  # extraction covers all symbols of the venue-day
        for symbol in cfg.venues[venue].symbols:
            available = set(_dates_available(cfg, venue, symbol))
            symbol_dates = [d for d in dates if d in available]
            for date in symbol_dates:
                # Extraction is deterministic, but it is not free: a day of
                # MBT costs ~6 minutes and a range costs hours. Re-running to
                # reach the training step must not silently redo all of it,
                # so an existing partition is reused — the same check the
                # trades step above already makes.
                part = samples_partition_dir(cfg.processed_dir, venue, symbol, date) / PART_NAME
                if part.is_file():
                    continue
                print(f"extracting samples {venue} {symbol} {date} ...", flush=True)
                extract_samples(cfg, venue, symbol, date)
            paths = [
                samples_partition_dir(cfg.processed_dir, venue, symbol, date) / PART_NAME
                for date in symbol_dates
            ]
            paths = [p for p in paths if p.is_file()]
            if not paths:
                print(f"skipping {venue} {symbol}: no samples extracted", flush=True)
                continue
            # Only the columns training reads, and float32 for the feature
            # matrix: 53 days of MBT is ~5.4M samples, where float64 across
            # every written column does not fit alongside the model. float32
            # carries ~7 significant digits, far more than a bps feature
            # resolves to; ts_ns stays integral inside load_samples.
            data = load_samples(
                paths,
                columns=training_columns(),
                dtype=np.float32,
                stride=args.sample_stride,
            )
            cost_models = {
                mode: cost_model_from_config(venue, cfg.venues[venue], mode, symbol=symbol)
                for mode in ("maker", "taker")
            }
            print(f"training {venue} {symbol} on {len(symbol_dates)} day(s) ...", flush=True)
            outcome = train_and_evaluate(data, cost_models)
            stamps = data.get("ts_ns")
            outcome["walk_forward"] = walk_forward_capacity(
                None if stamps is None else [int(v) for v in stamps]
            )
            results[f"{venue} {symbol}"] = outcome

    leakage = "skipped by flag" if args.skip_leakage_suite else _leakage_suite_status()
    cost_summary = _cost_summary(cfg, venues)
    payload = {
        "dates": dates,
        "volatility_regimes": 1 if len(dates) <= 5 else len(dates) // 5,
        "sampling": (
            "event bars, every 50 book updates"
            if args.sample_stride == 1
            else (
                f"event bars, every 50 book updates, then every {args.sample_stride}th "
                f"retained sample kept for training (effective bar ~{50 * args.sample_stride} "
                "book updates) — memory-bounded, see ADR-025"
            )
        ),
        "sample_stride": args.sample_stride,
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
