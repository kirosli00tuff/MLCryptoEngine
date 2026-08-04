"""CLI: ``python -m data.validate [--venue kraken] [--date 2026-07-30]`` (``make validate``).

Scores whatever the run plan says is scoreable and reports everything it
skipped. A venue with nothing to validate for the requested date is never a
reason to abort the other venues — see :mod:`data.validate.scope`.
"""

from __future__ import annotations

import argparse
import sys

from data.config import REPO_ROOT, AppConfig, load_config
from data.databento.rolls import read_rolls
from data.databento.validate import VendorDayReport, validate_vendor_day
from data.validate.replay import DayReport, VenueConfigurationError, validate_venue_day
from data.validate.report_writer import append_report, write_summary_json
from data.validate.scope import RunPlan, VendorDay, plan_run

# Configuration is wrong (unknown venue, or a recorder venue nothing can
# replay). Distinct from 1, which means "nothing to do", so a scripted caller
# can tell a misconfiguration from an empty archive.
EXIT_CONFIG_ERROR = 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m data.validate",
        description="Reconstruct books from raw data, score data quality, "
        "and append results to report.md.",
    )
    parser.add_argument(
        "--venue",
        action="append",
        dest="venues",
        metavar="KEY",
        help="venue key (repeatable; default: every recorder venue with recorded "
        "data — vendor venues are scored only when named explicitly)",
    )
    parser.add_argument(
        "--date",
        action="append",
        dest="dates",
        metavar="YYYY-MM-DD",
        help="ISO date (repeatable; default: every recorded date for the venue)",
    )
    return parser.parse_args(argv)


def _score_vendor_day(cfg: AppConfig, day: VendorDay) -> VendorDayReport:
    """Score one stored vendor contract-day, with its roll boundaries applied."""
    return validate_vendor_day(
        cfg, day.symbol, day.date, schema=day.schema, rolls=read_rolls(cfg, day.symbol)
    )


def _run(cfg: AppConfig, plan: RunPlan) -> tuple[list[DayReport], list[VendorDayReport]]:
    runs: list[DayReport] = []
    for replay in plan.recorder_days:
        print(f"validating {replay.venue} {replay.date} ...", flush=True)
        runs.append(validate_venue_day(cfg, replay.venue, replay.date))
    vendor_runs: list[VendorDayReport] = []
    for day in plan.vendor_days:
        print(f"validating {day.venue} {day.symbol} {day.date} ({day.schema}) ...", flush=True)
        vendor_runs.append(_score_vendor_day(cfg, day))
    return runs, vendor_runs


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    try:
        plan = plan_run(cfg, args.venues, args.dates)
    except VenueConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    # Printed before any scoring so an operator watching a long run knows up
    # front which venues are not in it, rather than inferring it from absence.
    for skip in plan.skipped:
        print(f"skipping {skip.venue} ({skip.kind}): {skip.reason}")
    if plan.is_empty:
        print("nothing to validate — run `make record` first")
        return 1

    runs, vendor_runs = _run(cfg, plan)

    append_report(REPO_ROOT / "report.md", runs, vendor_runs, plan.skipped)
    summary_path = write_summary_json(cfg.logs_dir, runs)

    for run in runs:
        verdict = "PASS" if run.passed else "FAIL"
        print(f"{run.venue} {run.date}: {verdict} · {run.msgs_total} msgs")
        for reason in run.failure_reasons:
            print(f"  ✗ {reason}")
    for vendor in vendor_runs:
        verdict = "PASS" if vendor.passed else "FAIL"
        print(f"{vendor.venue} {vendor.symbol} {vendor.date}: {verdict} · {vendor.events} events")
        for reason in vendor.failure_reasons:
            print(f"  ✗ {reason}")
    print(f"report.md updated · summary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
