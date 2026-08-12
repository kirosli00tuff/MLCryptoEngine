"""Disk guard and status reporting for continuous operation.

Two properties matter here and neither is cosmetic. The disk guard must warn
and do nothing else — a guard that stops recording or prunes old days to free
space destroys data that cannot be recaptured. And ``make status`` must report
a stale heartbeat as unhealthy: a recorder can hold an open socket while
receiving nothing, so process liveness alone is not evidence of capture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import orjson

from data.config import AppConfig, DiskSettings, RecorderSettings, VenueConfig, load_config
from data.recorder.diskguard import DiskGuard, DiskLevel, DiskStatus, read_disk
from data.recorder.writer import RawFileWriter
from ops.status import day_partition_bytes, latest_heartbeats, module_pids, render, runs_module

NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)
DATE = "2026-07-31"


def _venues() -> dict[str, VenueConfig]:
    # The repo config retires kraken/coinbase (Stage D.1b). These tests
    # exercise liveness mechanics — missing and stale heartbeats — so they
    # re-mark those venues as live here; retired-venue behaviour has its own
    # coverage in tests/test_retired_venues.py.
    return {
        key: (
            vcfg.model_copy(update={"kind": "recorder"}) if key in ("kraken", "coinbase") else vcfg
        )
        for key, vcfg in load_config().venues.items()
    }


def _config(tmp_path: Path, **disk: float) -> AppConfig:
    return AppConfig(
        data_root=tmp_path,
        logs_dir=tmp_path / "logs",
        venues=_venues(),
        recorder=RecorderSettings(heartbeat_interval_s=10.0),
        disk=DiskSettings(**disk) if disk else DiskSettings(),
    )


def _write_heartbeat(logs_dir: Path, venue: str, when: datetime, **fields: object) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "venue": venue,
        "connected": True,
        "msgs_total": 1_000,
        "msgs_per_s": 12.5,
        "last_seq": None,
        "event": "heartbeat",
        "level": "info",
        "logger": "recorder",
        "timestamp": when.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        **fields,
    }
    with (logs_dir / "recorder.log").open("ab") as fh:
        fh.write(orjson.dumps(record) + b"\n")


# --- disk guard: warns, and only warns ---------------------------------------


def test_disk_levels_follow_the_configured_thresholds(tmp_path: Path) -> None:
    # Real filesystem, thresholds chosen relative to its actual free space so
    # each branch is exercised without faking shutil.
    free = read_disk(tmp_path, warn_free_gb=0.0, critical_free_gb=0.0).free_gb

    assert read_disk(tmp_path, free / 2, free / 4).level is DiskLevel.OK
    assert read_disk(tmp_path, free * 2, free / 2).level is DiskLevel.LOW
    assert read_disk(tmp_path, free * 4, free * 2).level is DiskLevel.CRITICAL


def test_read_disk_walks_up_to_an_existing_ancestor(tmp_path: Path) -> None:
    # The data root may not exist yet on a fresh clone; report the filesystem
    # it will land on rather than raising.
    status = read_disk(tmp_path / "raw" / "venue=kraken", warn_free_gb=1.0, critical_free_gb=0.5)

    assert status.total_bytes > 0


def test_guard_never_touches_recorded_data(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    banked = raw / "messages.ndjson.zst"
    banked.write_bytes(b"recorded")
    # Thresholds far above real free space: the guard sees CRITICAL every time.
    guard = DiskGuard(raw, warn_free_gb=1e9, critical_free_gb=1e9, repeat_interval_s=0.0)

    for tick in range(5):
        assert guard.check(now_s=float(tick)).level is DiskLevel.CRITICAL

    assert banked.read_bytes() == b"recorded", "the guard must never delete or rewrite data"
    assert list(raw.iterdir()) == [banked]


def test_guard_logs_on_transition_then_throttles_repeats(tmp_path: Path) -> None:
    guard = DiskGuard(tmp_path, warn_free_gb=1e9, critical_free_gb=0.0, repeat_interval_s=300.0)
    emitted: list[DiskLevel] = []
    guard._emit = lambda status: emitted.append(status.level)  # type: ignore[method-assign]

    guard.check(now_s=0.0)  # first crossing: always logged
    guard.check(now_s=10.0)  # still LOW, inside the throttle window
    guard.check(now_s=299.0)
    guard.check(now_s=300.0)  # throttle window elapsed

    assert emitted == [DiskLevel.LOW, DiskLevel.LOW]


def test_guard_stays_quiet_while_healthy(tmp_path: Path) -> None:
    guard = DiskGuard(tmp_path, warn_free_gb=0.001, critical_free_gb=0.0005)
    emitted: list[DiskLevel] = []
    guard._emit = lambda status: emitted.append(status.level)  # type: ignore[method-assign]

    guard.check(now_s=0.0)  # one line for the initial OK reading
    guard.check(now_s=1_000.0)
    guard.check(now_s=100_000.0)

    assert emitted == [DiskLevel.OK], "a healthy disk must not re-log forever"


def test_disk_status_is_immutable() -> None:
    status = DiskStatus(
        path=Path("/tmp"), free_bytes=42 * 1024**3, total_bytes=100 * 1024**3, level=DiskLevel.OK
    )

    assert status.free_gb == 42
    assert status.total_gb == 100


# --- status reporting --------------------------------------------------------


def test_latest_heartbeat_per_venue_wins(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    _write_heartbeat(logs, "kraken", NOW - timedelta(minutes=5), msgs_total=100)
    _write_heartbeat(logs, "coinbase", NOW - timedelta(seconds=30))
    _write_heartbeat(logs, "kraken", NOW - timedelta(seconds=8), msgs_total=999)

    beats = latest_heartbeats(logs / "recorder.log", NOW)

    assert beats["kraken"].msgs_total == 999
    assert beats["kraken"].age_s == 8
    assert beats["coinbase"].age_s == 30


def test_missing_log_is_reported_as_no_heartbeats_not_an_error(tmp_path: Path) -> None:
    assert latest_heartbeats(tmp_path / "logs" / "recorder.log", NOW) == {}


def test_day_partition_bytes_counts_only_the_requested_venue_day(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    writer = RawFileWriter(raw, "kraken")
    try:
        # 2026-07-31T00:30Z and T01:30Z — two hour files inside DATE.
        writer.write(1_785_456_600 * 1_000_000_000, '{"channel":"book"}')
        writer.write(1_785_460_200 * 1_000_000_000, '{"channel":"book"}')
    finally:
        writer.close()

    hours, size = day_partition_bytes(raw, "kraken", DATE)

    assert hours == 2
    assert size > 0
    assert day_partition_bytes(raw, "coinbase", DATE) == (0, 0)


def test_status_is_unhealthy_when_a_heartbeat_is_stale(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    # Process liveness alone proves nothing: an open socket delivering no
    # messages looks identical until the heartbeat ages.
    for venue in cfg.venues:
        _write_heartbeat(cfg.logs_dir, venue, NOW - timedelta(minutes=4), connected=True)

    text, healthy = render(cfg, NOW)

    assert not healthy
    assert "STALE" in text
    assert "connected" in text


def test_status_flags_a_venue_with_no_heartbeat_at_all(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    _write_heartbeat(cfg.logs_dir, "kraken", NOW - timedelta(seconds=5))

    text, healthy = render(cfg, NOW)

    assert not healthy
    assert "coinbase   no heartbeat in log" in text


def test_status_reports_the_configured_disk_thresholds(tmp_path: Path) -> None:
    cfg = _config(tmp_path, warn_free_gb=50.0, critical_free_gb=20.0)

    text, _ = render(cfg, NOW)

    assert "warn below 50 GB · critical below 20 GB" in text
    assert f"Raw capture for {DATE}" in text
    assert "Processes" in text


def test_module_match_ignores_the_shell_that_launched_the_recorder() -> None:
    # The real shape from `pgrep -af`: a bash -c wrapper whose script mentions
    # both modules, plus the uv wrapper and the interpreter that actually run
    # one of them. Substring matching counted the wrapper as both processes.
    wrapper = [
        "/bin/bash",
        "-c",
        "setsid nohup uv run python -m data.recorder & uv run python -m ops.telemetry &",
    ]
    uv_wrapper = ["uv", "run", "python", "-m", "data.recorder"]
    interpreter = ["/repo/.venv/bin/python3", "-m", "data.recorder"]

    assert not runs_module(wrapper, "data.recorder")
    assert not runs_module(wrapper, "ops.telemetry")
    assert runs_module(uv_wrapper, "data.recorder")
    assert runs_module(interpreter, "data.recorder")
    assert not runs_module(interpreter, "ops.telemetry")


def test_module_match_rejects_a_trailing_dash_m() -> None:
    assert not runs_module(["python", "-m"], "data.recorder")
    assert not runs_module(["python", "data.recorder"], "data.recorder")


def test_module_pids_scans_proc_without_raising() -> None:
    # The scan must tolerate processes exiting mid-iteration; a module nobody
    # runs simply yields nothing.
    assert module_pids("mlce.definitely.not.running") == []
