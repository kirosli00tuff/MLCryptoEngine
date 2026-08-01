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

from data.validate.replay import DayReport


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
    return (
        f"Integrity mechanism: **{integrity.mechanism}** · "
        f"{_volume('sequence numbers', integrity.sequence_checks)} · "
        f"{_volume('book checksums', integrity.checksum_checks)}"
    )


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
            f"feed gaps in span: {report.feed_gaps} ({report.feed_gap_ms} ms, unioned "
            "and clamped to the span)"
        )
        if report.warmup_start_ns is not None:
            warm_stamp = datetime.fromtimestamp(report.warmup_start_ns / 1e9, tz=UTC).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            lines.append(
                f"\nWarm start: previous-day tail replayed from {warm_stamp}Z so books "
                "are live at midnight (state only — nothing before the day is scored)."
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
        lines.extend(_arrival_table(report))
        lines.append("")
    return "\n".join(lines)


def append_report(report_path: Path, runs: list[DayReport]) -> None:
    """Append a dated section to report.md (created if missing)."""
    with report_path.open("a", encoding="utf-8") as fh:
        fh.write(render_section(runs))


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
