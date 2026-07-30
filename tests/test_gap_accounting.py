"""Gap accounting: union semantics, the span invariant, and dry-run hygiene.

Regression suite for the 2026-07-30 finding where 28 gap records from an
earlier failed dry-run session (websockets 1 MiB frame-cap reconnect storm)
were summed into "32,402 ms of gaps inside a 24-second recording".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import orjson
import pytest
from websockets.asyncio.server import ServerConnection, serve

from data.config import AppConfig, FeeTier, RecorderSettings, SnapshotBehaviour, VenueConfig
from data.recorder.base import DryRunLimiter
from data.recorder.gaps import GapLogger, GapRecord, merge_windows, read_gaps
from data.recorder.kraken import KrakenRecorder
from data.recorder.writer import RawFileWriter
from data.validate.replay import GapAccountingError, account_gaps

S = 1_000_000_000  # ns per second


def _gap(disconnect_s: float, reconnect_s: float) -> GapRecord:
    return GapRecord(
        venue="test",
        disconnect_ns=int(disconnect_s * S),
        reconnect_ns=int(reconnect_s * S),
        duration_ms=int((reconnect_s - disconnect_s) * 1000),
        reason="test",
    )


DAY = (0, 86_400 * S)


# --- merge_windows -----------------------------------------------------------


def test_merge_windows_unions_overlaps_duplicates_and_touching() -> None:
    windows = [(10, 20), (15, 25), (15, 25), (25, 30), (40, 50), (42, 44)]
    assert merge_windows(windows) == [(10, 30), (40, 50)]


def test_merge_windows_drops_empty_and_inverted() -> None:
    assert merge_windows([(5, 5), (9, 3)]) == []


# --- coverage computation with dirty records ---------------------------------


def test_overlapping_and_duplicate_gaps_are_counted_once() -> None:
    # Three records describing the same 10s outage plus a partial overlap:
    # summing durations would claim 35s; the union is exactly 15s.
    gaps = [
        _gap(100, 110),
        _gap(100, 110),  # duplicate
        _gap(105, 115),  # overlap extending 5s
        _gap(102, 108),  # fully contained
    ]
    accounts = account_gaps(gaps, span=(0, 1000 * S), day_bounds=DAY)

    assert accounts.gaps_in_span == 4  # every record is attributed...
    assert accounts.gap_ms_in_span == 15_000  # ...but the union is measured once
    assert accounts.gap_ns_excluded_from_day == 15 * S
    assert accounts.gaps_outside_span == 0


def test_gaps_outside_recorded_span_are_reported_not_counted() -> None:
    # The 2026-07-30 shape: a reconnect storm before recording ever started.
    storm = [_gap(t, t + 1.1) for t in range(0, 56, 2)]  # 28 gaps, ~31s total
    span = (200 * S, 224 * S)  # the real 24-second recording, later

    accounts = account_gaps(storm, span, DAY)

    assert accounts.gaps_in_span == 0
    assert accounts.gap_ms_in_span == 0
    assert accounts.gap_ns_excluded_from_day == 0
    assert accounts.gaps_outside_span == 28
    # Reported duration is the union, still bounded by the storm window.
    assert accounts.gap_ms_outside_span <= 56_000


def test_gap_spanning_midnight_is_clamped_to_the_day() -> None:
    day = (100 * S, 200 * S)
    gaps = [_gap(90, 120)]  # starts before the day
    accounts = account_gaps(gaps, span=(95 * S, 190 * S), day_bounds=day)

    assert accounts.gap_ns_excluded_from_day == 20 * S  # only [100, 120)


def test_no_recorded_span_means_no_coverage_exclusions() -> None:
    accounts = account_gaps([_gap(10, 20)], span=None, day_bounds=DAY)

    assert accounts.gaps_in_span == 0
    assert accounts.gaps_outside_span == 1
    assert accounts.gap_ns_excluded_from_day == 0


# --- the invariant -----------------------------------------------------------


def test_invariant_fires_when_gap_time_exceeds_recorded_span() -> None:
    # A gap record claiming a 100s outage that encloses a 24s recorded span:
    # messages on disk contradict the gap, so accounting must refuse.
    gaps = [_gap(0, 100)]
    with pytest.raises(GapAccountingError, match="contradict"):
        account_gaps(gaps, span=(30 * S, 54 * S), day_bounds=DAY)


def test_invariant_accepts_gap_time_equal_to_bounded_outages() -> None:
    # A legitimate mid-recording outage: 10s gap inside a 100s span.
    gaps = [_gap(40, 50)]
    accounts = account_gaps(gaps, span=(0, 100 * S), day_bounds=DAY)
    assert accounts.gap_ms_in_span == 10_000


# --- dry-run hygiene ---------------------------------------------------------


def _venue_cfg(port: int) -> VenueConfig:
    return VenueConfig(
        name="Fake venue",
        ws_url=f"ws://127.0.0.1:{port}",
        rest_status_url="http://127.0.0.1/unused",
        symbols=["BTC/USD"],
        book_depth=10,
        snapshot=SnapshotBehaviour(on_subscribe=True, checksum=False),
        aws_region="local",
        fee_tiers=[FeeTier(volume_usd_30d=0, maker_bps=0, taker_bps=0)],
    )


async def test_dry_run_never_writes_gap_records(tmp_path: Path) -> None:
    connections = 0
    reconnected = asyncio.Event()

    async def handler(ws: ServerConnection) -> None:
        nonlocal connections
        connections += 1
        await ws.recv()
        await ws.recv()
        await ws.send(orjson.dumps({"conn": connections}).decode())
        if connections == 1:
            await asyncio.sleep(0.15)
            await ws.close(code=1011, reason="injected failure")
        else:
            reconnected.set()
            await ws.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        raw_dir = tmp_path / "raw"
        app_cfg = AppConfig(
            venues={},
            recorder=RecorderSettings(
                backoff_initial_s=0.05,
                backoff_max_s=0.2,
                backoff_jitter=0.0,
                heartbeat_interval_s=1.0,
                dry_run_messages=50,
            ),
        )
        recorder = KrakenRecorder(
            venue_cfg=_venue_cfg(port),
            app_cfg=app_cfg,
            writer=RawFileWriter(raw_dir, "fake"),
            gaps=GapLogger(raw_dir, "fake"),
            dry_run=DryRunLimiter(50),
        )
        stop = asyncio.Event()
        run_task = asyncio.create_task(recorder.run(stop))
        await asyncio.wait_for(reconnected.wait(), timeout=10)
        stop.set()
        await asyncio.wait_for(run_task, timeout=10)

    assert connections == 2, "the disconnect/reconnect cycle must actually have happened"
    assert read_gaps(raw_dir, "fake") == [], "dry-run must not pollute the gap sidecar"
