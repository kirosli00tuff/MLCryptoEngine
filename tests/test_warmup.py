"""Warm-start replay: a day recorded mid-session must begin with live books.

Continuous recording keeps one WebSocket session running for days, so a
calendar day's opening book snapshot usually lives in the *previous* date's
partition. Replaying a day cold leaves every book invalid until the first
intra-day reconnect — the real 2026-08-01 partial day scored 0% coverage and
zero verified checksums for exactly this reason, despite lossless capture.
These tests pin the fix: the replay warms up from the previous day's last
snapshot, scores only the target day, and still detects a sequence break
across the midnight boundary.
"""

from __future__ import annotations

from pathlib import Path

import orjson

from data.config import AppConfig, load_config
from data.recorder.writer import RawFileWriter
from data.validate.replay import validate_venue_day

PREV_DATE = "2026-07-29"
DATE = "2026-07-30"
# 2026-07-30T00:00:00Z; the previous day's snapshot lands 30 minutes earlier.
MIDNIGHT_NS = 1_785_369_600 * 1_000_000_000
NS_PER_S = 1_000_000_000
SNAPSHOT_NS = MIDNIGHT_NS - 1800 * NS_PER_S
SYMBOL = "BTC-USD"
N_PREV_UPDATES = 200
N_DAY_UPDATES = 600


def _snapshot(seq: int) -> str:
    updates = [
        {"side": "bid", "price_level": f"{50_000 - i}.0", "new_quantity": "1.0"} for i in range(5)
    ] + [
        {"side": "offer", "price_level": f"{50_001 + i}.0", "new_quantity": "1.0"} for i in range(5)
    ]
    message = {
        "channel": "l2_data",
        "sequence_num": seq,
        "events": [{"type": "snapshot", "product_id": SYMBOL, "updates": updates}],
    }
    return orjson.dumps(message).decode()


def _update(seq: int) -> str:
    side = "bid" if seq % 2 == 0 else "offer"
    price = 50_000 - (seq % 3) if side == "bid" else 50_001 + (seq % 3)
    message = {
        "channel": "l2_data",
        "sequence_num": seq,
        "events": [
            {
                "type": "update",
                "product_id": SYMBOL,
                "updates": [
                    {"side": side, "price_level": f"{price}.0", "new_quantity": "2.0"},
                ],
            }
        ],
    }
    return orjson.dumps(message).decode()


def _record_two_days(raw_dir: Path, day_first_seq: int) -> None:
    """Previous day: snapshot + updates ending before midnight. Target day:
    updates only, starting at ``day_first_seq``."""
    writer = RawFileWriter(raw_dir, "coinbase")
    try:
        writer.write(SNAPSHOT_NS, _snapshot(0))
        for i in range(1, N_PREV_UPDATES + 1):
            writer.write(SNAPSHOT_NS + i * NS_PER_S, _update(i))
        for i in range(N_DAY_UPDATES):
            writer.write(MIDNIGHT_NS + (i + 1) * NS_PER_S, _update(day_first_seq + i))
    finally:
        writer.close()


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(data_root=tmp_path, logs_dir=tmp_path / "logs", venues=load_config().venues)


def test_day_starting_mid_session_warms_up_from_previous_day(tmp_path: Path) -> None:
    # Arrange: sequence numbers contiguous across the midnight boundary.
    _record_two_days(tmp_path / "raw", day_first_seq=N_PREV_UPDATES + 1)

    # Act
    report = validate_venue_day(_config(tmp_path), "coinbase", DATE)

    # Assert: warmed from the previous day's snapshot, scored only the day.
    assert report.warmup_start_ns == SNAPSHOT_NS
    assert report.msgs_total == N_DAY_UPDATES, "warm-up messages must not be scored"
    assert report.integrity.sequence_checks == N_DAY_UPDATES

    (symbol,) = report.symbols
    assert symbol.snapshots == 0, "the target day itself contains no snapshot"
    assert symbol.events_applied == N_DAY_UPDATES
    assert symbol.seq_gaps == 0
    assert symbol.rows_written >= N_DAY_UPDATES
    # The book was live at midnight, so the recorded span is covered — without
    # warm-up this day scores 0.000%.
    day_fraction_pct = 100 * N_DAY_UPDATES / 86_400
    assert symbol.valid_coverage_day_pct > 0.9 * day_fraction_pct


def test_day_without_previous_data_replays_cold(tmp_path: Path) -> None:
    # Arrange: same target day, but the previous day was never recorded.
    writer = RawFileWriter(tmp_path / "raw", "coinbase")
    try:
        for i in range(N_DAY_UPDATES):
            writer.write(MIDNIGHT_NS + (i + 1) * NS_PER_S, _update(i + 1))
    finally:
        writer.close()

    # Act
    report = validate_venue_day(_config(tmp_path), "coinbase", DATE)

    # Assert: no warm start, book never valid, coverage honestly zero.
    assert report.warmup_start_ns is None
    (symbol,) = report.symbols
    assert symbol.valid_coverage_day_pct == 0.0
    assert not report.passed


def test_sequence_break_across_midnight_is_detected(tmp_path: Path) -> None:
    # Arrange: previous day ends at seq 200; target day starts at 202.
    _record_two_days(tmp_path / "raw", day_first_seq=N_PREV_UPDATES + 2)

    # Act
    report = validate_venue_day(_config(tmp_path), "coinbase", DATE)

    # Assert: the gap straddling the boundary is caught and scored to the day.
    (symbol,) = report.symbols
    assert symbol.seq_gaps == 1
    assert symbol.seq_gaps_unexplained == 1
    assert not report.passed
