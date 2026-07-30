"""Recorder resilience against a fake WebSocket server: reconnect + gap logging."""

from __future__ import annotations

import asyncio
from pathlib import Path

import orjson
from websockets.asyncio.server import ServerConnection, serve

from data.config import (
    AppConfig,
    FeeTier,
    RecorderSettings,
    SnapshotBehaviour,
    VenueConfig,
)
from data.recorder.gaps import GapLogger, read_gaps
from data.recorder.kraken import KrakenRecorder
from data.recorder.reader import available_dates, iter_day_records
from data.recorder.writer import RawFileWriter

FIRST_BATCH = 3
SECOND_BATCH = 2


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


def _app_cfg() -> AppConfig:
    return AppConfig(
        venues={},
        recorder=RecorderSettings(
            backoff_initial_s=0.05,
            backoff_max_s=0.2,
            backoff_jitter=0.0,
            heartbeat_interval_s=1.0,
            dry_run_messages=50,
        ),
    )


async def test_reconnect_logs_gap_and_keeps_recording_losslessly(tmp_path: Path) -> None:
    connections = 0
    second_batch_sent = asyncio.Event()

    async def handler(ws: ServerConnection) -> None:
        nonlocal connections
        connections += 1
        if connections == 1:
            # Wait for the recorder's subscribe payloads so it is guaranteed
            # to be in its read loop before messages start flowing.
            await ws.recv()
            await ws.recv()
            for i in range(FIRST_BATCH):
                await ws.send(orjson.dumps({"conn": 1, "n": i}).decode())
            # Let the client drain the batch, then fail abnormally.
            await asyncio.sleep(0.25)
            await ws.close(code=1011, reason="injected failure")
        else:
            for i in range(SECOND_BATCH):
                await ws.send(orjson.dumps({"conn": 2, "n": i}).decode())
            second_batch_sent.set()
            # Hold the connection open until the client closes it.
            await ws.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        raw_dir = tmp_path / "raw"
        writer = RawFileWriter(raw_dir, "fake")
        gaps = GapLogger(raw_dir, "fake")
        recorder = KrakenRecorder(
            venue_cfg=_venue_cfg(port),
            app_cfg=_app_cfg(),
            writer=writer,
            gaps=gaps,
        )
        stop = asyncio.Event()
        run_task = asyncio.create_task(recorder.run(stop))

        await asyncio.wait_for(second_batch_sent.wait(), timeout=10)
        # Give the client a moment to drain the second batch, then stop.
        await asyncio.sleep(0.3)
        stop.set()
        await asyncio.wait_for(run_task, timeout=10)
        writer.close()

    assert connections == 2, "recorder must reconnect after the abnormal close"

    gap_records = read_gaps(raw_dir, "fake")
    assert len(gap_records) == 1
    gap = gap_records[0]
    assert gap.venue == "fake"
    assert gap.reconnect_ns > gap.disconnect_ns
    assert "ConnectionClosed" in gap.reason

    dates = available_dates(raw_dir, "fake")
    assert len(dates) == 1
    recorded = [orjson.loads(raw) for _ns, raw in iter_day_records(raw_dir, "fake", dates[0])]
    assert len(recorded) == FIRST_BATCH + SECOND_BATCH
    assert [m["conn"] for m in recorded] == [1] * FIRST_BATCH + [2] * SECOND_BATCH
    assert recorder.heartbeat.messages_total == FIRST_BATCH + SECOND_BATCH


async def test_graceful_stop_without_failure_logs_no_gap(tmp_path: Path) -> None:
    sent = asyncio.Event()

    async def handler(ws: ServerConnection) -> None:
        await ws.send(orjson.dumps({"only": 1}).decode())
        sent.set()
        await ws.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        raw_dir = tmp_path / "raw"
        writer = RawFileWriter(raw_dir, "fake")
        recorder = KrakenRecorder(
            venue_cfg=_venue_cfg(port),
            app_cfg=_app_cfg(),
            writer=writer,
            gaps=GapLogger(raw_dir, "fake"),
        )
        stop = asyncio.Event()
        run_task = asyncio.create_task(recorder.run(stop))
        await asyncio.wait_for(sent.wait(), timeout=10)
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(run_task, timeout=10)
        writer.close()

    assert read_gaps(raw_dir, "fake") == []
    assert writer.messages_total == 1
