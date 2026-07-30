"""CLI: ``python -m data.validate [--venue kraken] [--date 2026-07-30]`` (``make validate``)."""

from __future__ import annotations

import argparse
import sys

from data.config import REPO_ROOT, load_config
from data.recorder.reader import available_dates
from data.validate.replay import DayReport, validate_venue_day
from data.validate.report_writer import append_report, write_summary_json


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m data.validate",
        description="Reconstruct books from raw capture, score data quality, "
        "and append results to report.md.",
    )
    parser.add_argument(
        "--venue",
        action="append",
        dest="venues",
        metavar="KEY",
        help="venue key (repeatable; default: every venue with recorded data)",
    )
    parser.add_argument(
        "--date",
        action="append",
        dest="dates",
        metavar="YYYY-MM-DD",
        help="ISO date (repeatable; default: every recorded date for the venue)",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    venues = args.venues if args.venues else sorted(cfg.venues)

    runs: list[DayReport] = []
    for venue in venues:
        if venue not in cfg.venues:
            print(f"unknown venue: {venue} (configured: {', '.join(sorted(cfg.venues))})")
            return 2
        dates = args.dates if args.dates else available_dates(cfg.raw_dir, venue)
        if not dates:
            print(f"{venue}: no recorded data found under {cfg.raw_dir}")
            continue
        for date in dates:
            print(f"validating {venue} {date} ...", flush=True)
            runs.append(validate_venue_day(cfg, venue, date))

    if not runs:
        print("nothing to validate — run `make record` first")
        return 1

    append_report(REPO_ROOT / "report.md", runs)
    summary_path = write_summary_json(cfg.logs_dir, runs)

    for run in runs:
        verdict = "PASS" if run.passed else "FAIL"
        print(f"{run.venue} {run.date}: {verdict} · {run.msgs_total} msgs")
        for reason in run.failure_reasons:
            print(f"  ✗ {reason}")
    print(f"report.md updated · summary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
