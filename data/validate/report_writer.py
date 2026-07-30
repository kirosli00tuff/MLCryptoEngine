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


def _symbol_table(report: DayReport) -> list[str]:
    lines = [
        "| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) "
        "| crossed (unexpl.) | locked | day coverage | coverage excl. gaps "
        "| snap compares (mismatch) | rows |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in report.symbols:
        lines.append(
            f"| {s.symbol} | {s.events_applied} | {s.snapshots} "
            f"| {s.seq_gaps} ({s.seq_gaps_unexplained}) "
            f"| {s.checksum_failures} ({s.checksum_failures_unexplained}) "
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
            f"feed gaps: {report.feed_gaps} ({report.feed_gap_ms} ms)"
        )
        lines.append("")
        channels = " · ".join(f"`{k}`: {v}" for k, v in sorted(report.channel_counts.items()))
        lines.append(f"Channels: {channels}")
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
