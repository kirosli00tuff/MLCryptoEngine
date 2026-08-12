"""Operational snapshot of an always-on recorder: ``make status``.

Read-only by construction. It answers the four questions worth asking about a
capture that is supposed to never stop — are the processes alive, is each venue
still delivering, how much did today write, and is there room for tomorrow —
and it touches nothing. Reporting a stale heartbeat is useful; a status command
that restarts something is not.

Heartbeat age, not connection state, is the liveness signal that matters: a
recorder can hold an open socket and receive nothing, and the difference only
shows up as an aging heartbeat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import orjson

from data.config import AppConfig, load_config
from data.recorder import RECORDER_TYPES
from data.recorder.diskguard import DiskLevel, DiskStatus, read_disk
from data.recorder.writer import RAW_FILE_NAME

PROC = Path("/proc")
RECORDER_MODULE = "data.recorder"
TELEMETRY_MODULE = "ops.telemetry"
# A heartbeat older than this many intervals means the venue has gone quiet
# even if the process is alive and the socket is open.
STALE_HEARTBEAT_INTERVALS = 3.0


@dataclass(frozen=True)
class ProcessStatus:
    name: str
    pids: list[int]

    @property
    def alive(self) -> bool:
        return bool(self.pids)


@dataclass(frozen=True)
class VenueHeartbeat:
    venue: str
    age_s: float
    connected: bool
    msgs_total: int
    msgs_per_s: float


def runs_module(argv: list[str], module: str) -> bool:
    """True if ``argv`` invokes ``module`` via ``-m``, token-exactly.

    Substring matching over the whole command line is wrong here: the shell
    that launched the recorder carries the module name inside its ``-c``
    script, so a plain ``in`` test reports the wrapper as a running recorder —
    and a wrapper that spawned both processes as both of them at once. Requiring
    an argv element equal to ``module`` immediately after ``-m`` matches
    ``uv run python -m data.recorder`` and the interpreter it execs, and nothing
    that merely mentions the name.
    """
    return any(flag == "-m" and name == module for flag, name in pairwise(argv))


def module_pids(module: str) -> list[int]:
    """PIDs currently running ``python -m <module>``.

    Reads ``/proc`` directly rather than shelling out, so the status command
    adds no external dependency.
    """
    pids: list[int] = []
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue  # process exited between listing and reading
        argv = raw.decode("utf-8", "replace").split("\0")
        if runs_module(argv, module):
            pids.append(int(entry.name))
    return sorted(pids)


def latest_heartbeats(log_path: Path, now: datetime) -> dict[str, VenueHeartbeat]:
    """Most recent heartbeat per venue from the structured recorder log.

    A missing or unreadable log means no heartbeats, not an error: a fresh
    clone has no log yet, and that is exactly what the caller should be told.
    """
    if not log_path.is_file():
        return {}
    latest: dict[str, VenueHeartbeat] = {}
    with log_path.open("rb") as fh:
        for line in fh:
            if b'"heartbeat"' not in line:
                continue
            try:
                record = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            if record.get("event") != "heartbeat":
                continue
            venue, stamp = record.get("venue"), record.get("timestamp")
            if not isinstance(venue, str) or not isinstance(stamp, str):
                continue
            try:
                seen = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                continue
            latest[venue] = VenueHeartbeat(
                venue=venue,
                age_s=(now - seen).total_seconds(),
                connected=bool(record.get("connected")),
                msgs_total=int(record.get("msgs_total") or 0),
                msgs_per_s=float(record.get("msgs_per_s") or 0.0),
            )
    return latest


def day_partition_bytes(raw_dir: Path, venue: str, date: str) -> tuple[int, int]:
    """``(hour_files, compressed_bytes)`` written for one venue-day so far."""
    base = raw_dir / f"venue={venue}" / f"date={date}"
    files = sorted(base.glob(f"hour=*/{RAW_FILE_NAME}"))
    return len(files), sum(f.stat().st_size for f in files if f.is_file())


def _fmt_bytes(count: int) -> str:
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} TiB"


def _fmt_age(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s ago"
    if seconds < 5400:
        return f"{seconds / 60:.1f}m ago"
    return f"{seconds / 3600:.1f}h ago"


def _disk_line(disk: DiskStatus, cfg: AppConfig) -> str:
    marker = {DiskLevel.OK: "ok", DiskLevel.LOW: "LOW", DiskLevel.CRITICAL: "CRITICAL"}[disk.level]
    return (
        f"{marker:<8} {disk.free_gb:,.1f} GB free of {disk.total_gb:,.1f} GB · "
        f"warn below {cfg.disk.warn_free_gb:g} GB · critical below {cfg.disk.critical_free_gb:g} GB"
    )


def render(cfg: AppConfig, now: datetime) -> tuple[str, bool]:
    """Build the status report. Returns ``(text, healthy)``.

    ``healthy`` is false when a process is down, a venue's heartbeat is stale
    or missing, or free space is below the critical threshold — so ``make
    status`` is usable as a check, not only as a display.
    """
    lines: list[str] = [f"MLCryptoEngine status — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}", ""]
    healthy = True

    lines.append("Processes")
    for proc in (
        ProcessStatus("recorder", module_pids(RECORDER_MODULE)),
        ProcessStatus("telemetry", module_pids(TELEMETRY_MODULE)),
    ):
        if proc.alive:
            lines.append(f"  {proc.name:<10} up    pid {', '.join(str(p) for p in proc.pids)}")
        else:
            healthy = False
            lines.append(f"  {proc.name:<10} DOWN")
    lines.append("")

    stale_after = cfg.recorder.heartbeat_interval_s * STALE_HEARTBEAT_INTERVALS
    heartbeats = latest_heartbeats(cfg.logs_dir / "recorder.log", now)
    # Only venues with a live recorder are expected to heartbeat: vendor-fed
    # venues (cme via Databento) have no recorder process, and retired venues
    # (kraken/coinbase since D.1b) deliberately stopped — neither may read as
    # unhealthy forever.
    live_venues = sorted(
        venue
        for venue in set(cfg.venues) & set(RECORDER_TYPES)
        if cfg.venues[venue].kind == "recorder"
    )
    lines.append(f"Heartbeats (stale after {stale_after:.0f}s)")
    for venue in live_venues:
        beat = heartbeats.get(venue)
        if beat is None:
            healthy = False
            lines.append(f"  {venue:<10} no heartbeat in log")
            continue
        stale = beat.age_s > stale_after
        healthy = healthy and not stale
        state = "connected" if beat.connected else "disconnected"
        lines.append(
            f"  {venue:<10} {'STALE' if stale else 'ok   '} {_fmt_age(beat.age_s):>9} · "
            f"{state} · {beat.msgs_total:,} msgs · {beat.msgs_per_s:,.1f}/s"
        )
    lines.append("")

    date = now.strftime("%Y-%m-%d")
    lines.append(f"Raw capture for {date} (compressed on disk)")
    day_total = 0
    for venue in live_venues:
        hours, size = day_partition_bytes(cfg.raw_dir, venue, date)
        day_total += size
        lines.append(f"  {venue:<10} {hours:>2} hour file(s) · {_fmt_bytes(size)}")
    lines.append(f"  {'total':<10} {_fmt_bytes(day_total)}")
    lines.append("")

    disk = read_disk(cfg.raw_dir, cfg.disk.warn_free_gb, cfg.disk.critical_free_gb)
    if disk.level is DiskLevel.CRITICAL:
        healthy = False
    lines.append("Disk")
    lines.append(f"  {_disk_line(disk, cfg)}")
    return "\n".join(lines), healthy


def main() -> int:
    text, healthy = render(load_config(), datetime.now(UTC))
    print(text)
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
