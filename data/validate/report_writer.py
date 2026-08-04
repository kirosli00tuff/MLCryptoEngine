"""Persist validation results: dated sections in report.md and a JSON summary.

The JSON summary (``logs/validation_summary.json``) is the machine-readable
mirror consumed by the desktop app's coverage panel.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import orjson

from data.databento.validate import VendorDayReport
from data.validate.replay import DayReport
from data.validate.scope import Skipped


def _check_cell(failures: int | None, unexplained: int | None) -> str:
    """Render one integrity check, or "n/a" when it does not apply to the venue.

    Never renders 0 for an unavailable check: on a feed with no sequence
    numbers, "0 (0)" would read as a clean continuity check that in fact never
    ran. See :mod:`data.validate.integrity`.
    """
    if failures is None:
        return "n/a"
    return f"{failures} ({unexplained})"


def _volume(label: str, count: int | None) -> str:
    if count is None:
        return f"{label}: n/a (this feed provides none)"
    return f"{label}: {count:,} checked"


def _integrity_line(report: DayReport) -> str:
    """Name the mechanism that certified this venue-day and how much it checked.

    The crossed/locked-book criterion is only meaningful alongside whatever
    keeps the book honest between snapshots, and that differs per venue — so
    the mechanism is named here rather than left implicit.
    """
    integrity = report.integrity
    line = (
        f"Integrity mechanism: **{integrity.mechanism}** · "
        f"{_volume('sequence numbers', integrity.sequence_checks)} · "
        f"{_volume('book checksums', integrity.checksum_checks)}"
    )
    if integrity.snapshot_checks is not None:
        line += f" · book snapshots: {integrity.snapshot_checks:,} applied"
    return line


def _symbol_table(report: DayReport) -> list[str]:
    lines = [
        "| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) "
        "| cksums verified | crossed (unexpl.) | locked | day coverage "
        "| coverage excl. gaps | snap compares (mismatch) | rows |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in report.symbols:
        verified = "n/a" if s.checksums_verified is None else str(s.checksums_verified)
        lines.append(
            f"| {s.symbol} | {s.events_applied} | {s.snapshots} "
            f"| {_check_cell(s.seq_gaps, s.seq_gaps_unexplained)} "
            f"| {_check_cell(s.checksum_failures, s.checksum_failures_unexplained)} "
            f"| {verified} "
            f"| {s.crossed_total} ({s.crossed_unexplained}) | {s.locked_total} "
            f"| {s.valid_coverage_day_pct:.2f}% | {s.valid_coverage_excl_gaps_pct:.2f}% "
            f"| {s.snapshot_compares} ({s.snapshot_mismatches}) | {s.rows_written} |"
        )
    return lines


def _arrival_table(report: DayReport) -> list[str]:
    arrival = report.arrival
    lines = ["| inter-message arrival | count |", "|---|---|"]
    previous = "0"
    for bound, count in zip(arrival.bounds_ms, arrival.counts, strict=False):
        lines.append(f"| {previous} to {bound:g} ms | {count} |")
        previous = f"{bound:g}"
    lines.append(f"| >{previous} ms | {arrival.counts[-1]} |")
    lines.append(
        f"\np50 ≤ {arrival.p50_ms:g} ms · p90 ≤ {arrival.p90_ms:g} ms · "
        f"p99 ≤ {arrival.p99_ms:g} ms · max {arrival.max_ms:g} ms"
    )
    return lines


def render_section(runs: list[DayReport]) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\n## Validation run — {stamp}\n"]
    for report in runs:
        verdict = "PASS" if report.passed else "FAIL"
        lines.append(f"### {report.venue} — {report.date} — **{verdict}**\n")
        if report.failure_reasons:
            lines.extend(f"- ✗ {reason}" for reason in report.failure_reasons)
            lines.append("")
        span = "n/a"
        if report.first_ns is not None and report.last_ns is not None:
            span = f"{(report.last_ns - report.first_ns) / 1e9:.0f}s"
        lines.append(
            f"Messages: **{report.msgs_total}** · recorded span: {span} · "
            f"feed gaps in span: {report.feed_gaps} ({report.feed_gap_ms} ms) · "
            f"recorder downtime: {report.downtime_gaps} ({report.downtime_gap_ms} ms) · "
            f"unclean terminations: {report.unclean_gaps} ({report.unclean_gap_ms} ms) · "
            f"excluded from coverage: {report.gap_ms_excluded} ms "
            "(all kinds unioned and clamped to the span)"
        )
        if report.warmup_start_ns is not None:
            warm_stamp = datetime.fromtimestamp(report.warmup_start_ns / 1e9, tz=UTC).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            lines.append(
                f"\nWarm start: previous-day tail replayed from {warm_stamp}Z so books "
                "are live at midnight (state only — nothing before the day is scored)."
            )
        elif report.snapshot_stream:
            lines.append(
                "\nSnapshot stream: every l2Book message is a full book, so warm "
                "start is structurally unnecessary; this venue is scored on "
                "snapshot cadence."
            )
        else:
            lines.append(
                "\n⚠ Cold start: no usable previous-day snapshot; books are invalid "
                "until the first snapshot inside the day."
            )
        if report.gaps_partially_outside_span:
            lines.append(
                f"\n⚠ {report.gaps_partially_outside_span} gap record(s) extend past the "
                f"recorded span; {report.gap_ms_clipped_outside_span} ms of their duration "
                "lies outside it and is excluded. Only the intersected portion counts "
                "against coverage — the clamp is reported, never silent."
            )
        if report.gaps_outside_span:
            lines.append(
                f"\n⚠ {report.gaps_outside_span} gap record(s) totalling "
                f"{report.gap_ms_outside_span} ms fall outside the recorded span "
                "(e.g. an earlier failed session the same day) — excluded from "
                "coverage, listed here so they are never silently dropped."
            )
        lines.append("")
        channels = " · ".join(f"`{k}`: {v}" for k, v in sorted(report.channel_counts.items()))
        lines.append(f"Channels: {channels}")
        lines.append("")
        lines.append(_integrity_line(report))
        lines.append("")
        lines.extend(_symbol_table(report))
        lines.append("")
        for s in report.symbols:
            if s.snap_intervals is None:
                continue
            lines.append(
                f"Snapshot cadence {s.symbol}: {s.snap_intervals:,} intervals · "
                f"p50 {s.snap_interval_p50_ms:.0f} ms · p95 {s.snap_interval_p95_ms:.0f} ms · "
                f"max {s.snap_interval_max_ms:.0f} ms · stale >{10}s: {s.snap_stale} "
                f"({s.snap_stale_unexplained} unexplained)"
                if s.snap_intervals
                else f"Snapshot cadence {s.symbol}: no intervals observed"
            )
        if any(s.snap_intervals is not None for s in report.symbols):
            lines.append("")
        lines.extend(_arrival_table(report))
        lines.append("")
    return "\n".join(lines)


def _hours(ns: int) -> str:
    return f"{ns / 3_600_000_000_000:.2f} h"


def render_vendor_section(runs: list[VendorDayReport], skipped: list[Skipped]) -> str:
    """Render vendor contract-days and skipped venues.

    Deliberately a different shape from the recorder section, because a vendor
    day is scored on different things: coverage is measured against
    scheduled-open time rather than the calendar day, there is no book checksum
    and no snapshot stream (both render "n/a", never 0), and roll exclusions are
    reported as their own number instead of being absorbed into coverage.
    """
    lines: list[str] = []
    for report in runs:
        verdict = "PASS" if report.passed else "FAIL"
        lines.append(
            f"### {report.venue} {report.symbol} — {report.date} — "
            f"**{verdict}** (vendor, `{report.schema}`)\n"
        )
        if report.failure_reasons:
            lines.extend(f"- ✗ {reason}" for reason in report.failure_reasons)
            lines.append("")
        lines.append(
            f"Events: **{report.events:,}** · scheduled open: "
            f"{_hours(report.scheduled_open_ns)} · covered: "
            f"{_hours(report.covered_open_ns)} ({report.coverage_pct:.2f}%) · "
            f"unexplained quiet: {_hours(report.quiet_open_ns)} "
            f"({len(report.quiet_windows)} window(s)) · roll exclusions: "
            f"{report.roll_windows} ({_hours(report.roll_excluded_open_ns)} of open time)"
        )
        lines.append("")
        lines.append(
            f"Ordering clock: {report.ordering_clock} · reference only: {report.reference_clock}"
        )
        lines.append("")
        lines.append(
            f"Integrity: {_volume('MDP3 sequence numbers', report.sequence_checks)} "
            f"({report.sequence_regressions if report.sequence_checks else 'n/a'} "
            f"regressions) · {_volume('book checksums', report.checksum_checks)} · "
            f"{_volume('book snapshots', report.snapshot_checks)}"
        )
        lines.append("")
        lines.append(
            f"Crossed: {report.crossed} ({report.crossed_explained} inside a scheduled "
            f"no-match window, so expected) · locked: {report.locked} · out of order on "
            f"ts_recv: {report.out_of_order_recv} · exchange-clock regressions: "
            f"{report.exchange_clock_regressions} (reference clock, not a defect)"
        )
        lines.append("")
    if skipped:
        lines.append("### Venues skipped\n")
        lines.extend(f"- **{s.venue}** (kind `{s.kind}`) — {s.reason}" for s in skipped)
        lines.append("")
    return "\n".join(lines)


def append_report(
    report_path: Path,
    runs: list[DayReport],
    vendor_runs: list[VendorDayReport] | None = None,
    skipped: list[Skipped] | None = None,
) -> None:
    """Append a dated section to report.md (created if missing).

    Skipped venues are written into the report rather than only printed: a
    section that lists two venues where three were expected must say what
    happened to the third, or a venue can quietly fall out of validation and
    the record will not show it.
    """
    body = render_section(runs) + render_vendor_section(vendor_runs or [], skipped or [])
    with report_path.open("a", encoding="utf-8") as fh:
        fh.write(body)


def write_summary_json(logs_dir: Path, runs: list[DayReport]) -> Path:
    """Atomically write the machine-readable summary the desktop app reads."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "validation_summary.json"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "runs": [run.model_dump() for run in runs],
    }
    fd, tmp_name = tempfile.mkstemp(dir=logs_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path
