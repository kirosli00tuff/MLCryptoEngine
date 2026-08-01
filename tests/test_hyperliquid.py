"""Hyperliquid: channel parsing, snapshot-cadence validation, reconnect+gap."""

from __future__ import annotations

import asyncio
from pathlib import Path

import orjson
from websockets.asyncio.server import ServerConnection, serve

from data.book import parse_hyperliquid
from data.config import AppConfig, load_config
from data.recorder import RECORDER_TYPES
from data.recorder.gaps import GapLogger, read_gaps
from data.recorder.hyperliquid import HyperliquidRecorder
from data.recorder.reader import available_dates, iter_day_records
from data.recorder.writer import RawFileWriter
from data.trades.parse import parse_hyperliquid_trades
from data.validate.integrity import SNAPSHOT_CADENCE
from data.validate.replay import validate_venue_day
from tests.conftest import FIXTURES_DIR
from tests.test_recorder_reconnect import _app_cfg, _venue_cfg

DATE = "2026-07-30"
BASE_NS = 1_785_412_800 * 1_000_000_000  # 2026-07-30T12:00:00Z
NS_PER_MS = 1_000_000


def _fixtures() -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = {}
    text = (FIXTURES_DIR / "hyperliquid_messages.ndjson").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip():
            message = orjson.loads(line)
            out.setdefault(message.get("channel", "?"), []).append(message)
    return out


def test_fixture_file_covers_every_subscribed_channel() -> None:
    channels = set(_fixtures())
    assert {"subscriptionResponse", "l2Book", "bbo", "trades", "activeAssetCtx"} <= channels


def test_l2book_parses_as_full_snapshot_and_other_channels_do_not() -> None:
    fixtures = _fixtures()
    (event,) = parse_hyperliquid(fixtures["l2Book"][0], recv_ns=123)
    assert event.is_snapshot, "every l2Book message is a complete book"
    assert event.venue == "hyperliquid"
    assert event.symbol in ("BTC", "ETH")
    assert len(event.bids) == 20 and len(event.asks) == 20
    assert event.bids[0].price > event.bids[1].price, "bids ordered best-first"
    assert event.asks[0].price < event.asks[1].price
    assert event.bids[0].price < event.asks[0].price, "uncrossed"
    assert event.seq is None and event.checksum is None

    # bbo carries no depth and must NOT fabricate book events; ctx/acks neither.
    assert parse_hyperliquid(fixtures["bbo"][0], 1) == []
    assert parse_hyperliquid(fixtures["activeAssetCtx"][0], 1) == []
    assert parse_hyperliquid(fixtures["subscriptionResponse"][0], 1) == []


def test_trades_parse_with_taker_side_and_both_clocks() -> None:
    fixtures = _fixtures()
    rows = parse_hyperliquid_trades(fixtures["trades"][0], recv_ns=777)
    assert rows, "trades fixture must contain executed fills"
    for row in rows:
        assert row["venue"] == "hyperliquid"
        assert row["venue_side"] in ("buy", "sell"), "B/A normalized to taker direction"
        assert row["ts_ns"] == 777, "ordering clock is the recorder's receive time"
        assert isinstance(row["exchange_ns"], int), "venue ms time kept as exchange_ns"
        assert row["source"] == "recorder"


def test_recorder_subscribes_all_channels_for_all_coins() -> None:
    assert RECORDER_TYPES["hyperliquid"] is HyperliquidRecorder
    cfg = load_config()
    recorder = HyperliquidRecorder.__new__(HyperliquidRecorder)
    recorder.venue_cfg = cfg.venues["hyperliquid"]
    payloads = [orjson.loads(m) for m in recorder.subscribe_messages()]
    assert len(payloads) == 8  # 2 coins x 4 channels
    seen = {(p["subscription"]["coin"], p["subscription"]["type"]) for p in payloads}
    assert seen == {
        (coin, channel)
        for coin in ("BTC", "ETH")
        for channel in ("l2Book", "bbo", "trades", "activeAssetCtx")
    }
    assert recorder.sequence_of({"channel": "l2Book"}) is None


def _l2book_line(time_ms: int) -> str:
    text = (FIXTURES_DIR / "hyperliquid_messages.ndjson").read_text(encoding="utf-8")
    message = next(
        orjson.loads(line)
        for line in text.splitlines()
        if line.strip() and orjson.loads(line).get("channel") == "l2Book"
    )
    message["data"]["time"] = time_ms
    return orjson.dumps(message).decode()


def _write_day(raw_dir: Path, offsets_ms: list[int]) -> str:
    writer = RawFileWriter(raw_dir, "hyperliquid")
    try:
        for offset in offsets_ms:
            writer.write(BASE_NS + offset * NS_PER_MS, _l2book_line(offset))
    finally:
        writer.close()
    coin = orjson.loads(_l2book_line(0))["data"]["coin"]
    return str(coin)


def test_validation_scores_snapshot_cadence_with_na_integrity(tmp_path: Path) -> None:
    # Arrange: 40 snapshots at 500 ms, one 15 s stale interval, then resume.
    offsets = [i * 500 for i in range(40)]
    offsets += [offsets[-1] + 15_000 + i * 500 for i in range(10)]
    symbol = _write_day(tmp_path / "raw", offsets)
    cfg = AppConfig(data_root=tmp_path, logs_dir=tmp_path / "logs", venues=load_config().venues)

    report = validate_venue_day(cfg, "hyperliquid", DATE)

    assert report.snapshot_stream
    assert report.integrity.mechanism == SNAPSHOT_CADENCE
    assert report.integrity.sequence_checks is None, "no sequence numbers: n/a, never 0"
    assert report.integrity.checksum_checks is None, "no checksums: n/a, never 0"
    assert report.integrity.snapshot_checks == len(offsets)
    symbol_report = next(s for s in report.symbols if s.symbol == symbol)
    assert symbol_report.seq_gaps is None and symbol_report.checksum_failures is None
    assert symbol_report.snap_intervals == len(offsets) - 1
    assert symbol_report.snap_interval_p50_ms == 500.0
    assert symbol_report.snap_interval_max_ms == 15_000.0
    assert symbol_report.snap_stale == 1
    assert symbol_report.snap_stale_unexplained == 1, "no gap logged, so not explained"
    # 15 s stale is reported, not fatal; the partial day still fails coverage.
    assert not any("snapshot silence" in reason for reason in report.failure_reasons)
    assert any("coverage outside gaps" in reason for reason in report.failure_reasons)


def test_unexplained_snapshot_silence_beyond_a_minute_fails(tmp_path: Path) -> None:
    offsets = [i * 500 for i in range(10)]
    offsets += [offsets[-1] + 70_000 + i * 500 for i in range(5)]
    _write_day(tmp_path / "raw", offsets)
    cfg = AppConfig(data_root=tmp_path, logs_dir=tmp_path / "logs", venues=load_config().venues)

    report = validate_venue_day(cfg, "hyperliquid", DATE)

    assert any("snapshot silence" in reason for reason in report.failure_reasons)


async def test_reconnect_logs_gap_and_resubscribe_snapshot_recovers(tmp_path: Path) -> None:
    """The existing reconnect/gap machinery applies unchanged: an abnormal
    close logs a gap, and the fresh snapshot after resubscribe is captured."""
    connections = 0
    done = asyncio.Event()
    snapshot_line = _l2book_line(0)

    async def handler(ws: ServerConnection) -> None:
        nonlocal connections
        connections += 1
        for _ in range(4):  # one coin x four channel subscriptions
            await ws.recv()
        if connections == 1:
            await ws.send(snapshot_line)
            await asyncio.sleep(0.2)
            await ws.close(code=1011, reason="injected failure")
        else:
            await ws.send(snapshot_line)  # the post-resubscribe snapshot
            done.set()
            await ws.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        venue_cfg = _venue_cfg(port).model_copy(update={"symbols": ["BTC"]})
        raw_dir = tmp_path / "raw"
        recorder = HyperliquidRecorder(
            venue_cfg,
            _app_cfg(),
            RawFileWriter(raw_dir, "hyperliquid"),
            GapLogger(raw_dir, "hyperliquid"),
        )
        stop = asyncio.Event()
        task = asyncio.create_task(recorder.run(stop))
        await asyncio.wait_for(done.wait(), timeout=10)
        stop.set()
        await asyncio.wait_for(task, timeout=10)
        recorder.writer.close()

    gaps = read_gaps(raw_dir, "hyperliquid")
    assert len(gaps) == 1, "the disconnect must be logged as a gap"
    captured = sum(
        1
        for date in available_dates(raw_dir, "hyperliquid")
        for _, raw in iter_day_records(raw_dir, "hyperliquid", date)
        if raw == snapshot_line
    )
    assert captured == 2, "both the pre-close and post-resubscribe snapshots are on disk"
