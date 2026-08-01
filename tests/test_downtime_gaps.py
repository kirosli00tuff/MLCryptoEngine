"""Downtime gaps: recorder-not-running periods must be first-class, explained gaps.

gaps.jsonl only records disconnects the recorder observed while running; any
period where the process was not running at all (systemd restart, crash, OOM
kill, reboot) previously left no record, so validation saw an unexplained
coverage hole and Phase B feature windows could span the discontinuity
unflagged. These tests pin the fix: session start/end markers, downtime gaps
derived between them, unclean terminations derived from last observed
activity, and mixed-kind gap accounting that unions rather than double-counts
while staying bounded by the recorded span (the Stage 1.6 invariant).
"""

from __future__ import annotations

from pathlib import Path

from data.recorder.gaps import GapRecord
from data.recorder.sessions import SessionLogger, SessionMarker, read_sessions
from data.recorder.writer import RawFileWriter
from data.validate.downtime import derive_downtime_gaps, last_activity_ns
from data.validate.replay import account_gaps

NS_PER_S = 1_000_000_000
# 2026-07-30T12:00:00Z, consistent with the other synthetic-day tests.
BASE_NS = 1_785_412_800 * NS_PER_S
DAY_BOUNDS = (BASE_NS - 12 * 3600 * NS_PER_S, BASE_NS + 12 * 3600 * NS_PER_S)


def _marker(event: str, ts_ns: int) -> SessionMarker:
    return SessionMarker(venue="kraken", event=event, ts_ns=ts_ns)  # type: ignore[arg-type]


def _no_activity(_before_ns: int) -> int | None:
    raise AssertionError("last_activity must not be consulted for clean stop/start pairs")


def test_session_markers_round_trip(tmp_path: Path) -> None:
    logger = SessionLogger(tmp_path, "kraken")
    logger.log("start", BASE_NS)
    logger.log("end", BASE_NS + NS_PER_S)

    markers = read_sessions(tmp_path, "kraken")

    assert [(m.event, m.ts_ns) for m in markers] == [
        ("start", BASE_NS),
        ("end", BASE_NS + NS_PER_S),
    ]
    assert all(m.venue == "kraken" for m in markers)


def test_end_then_start_yields_one_clean_downtime_gap() -> None:
    end_ns = BASE_NS
    start_ns = BASE_NS + 300 * NS_PER_S
    markers = [
        _marker("start", BASE_NS - 3600 * NS_PER_S),
        _marker("end", end_ns),
        _marker("start", start_ns),
    ]

    gaps = derive_downtime_gaps(markers, _no_activity)

    assert len(gaps) == 1
    (gap,) = gaps
    assert gap.kind == "downtime"
    assert (gap.disconnect_ns, gap.reconnect_ns) == (end_ns, start_ns)
    assert gap.duration_ms == 300_000


def test_start_after_start_yields_unclean_gap_from_last_activity() -> None:
    first_start = BASE_NS
    last_activity = BASE_NS + 500 * NS_PER_S
    second_start = BASE_NS + 900 * NS_PER_S
    markers = [_marker("start", first_start), _marker("start", second_start)]

    gaps = derive_downtime_gaps(markers, lambda before: last_activity)

    assert len(gaps) == 1
    (gap,) = gaps
    assert gap.kind == "unclean"
    assert (gap.disconnect_ns, gap.reconnect_ns) == (last_activity, second_start)
    assert "uncleanly" in gap.reason


def test_unclean_gap_never_starts_before_the_dead_session() -> None:
    """No observed activity (or activity predating the session) falls back to
    the dead session's own start — downtime cannot begin before it existed."""
    first_start = BASE_NS
    second_start = BASE_NS + 900 * NS_PER_S

    for activity in (None, BASE_NS - 3600 * NS_PER_S):
        gaps = derive_downtime_gaps(
            [_marker("start", first_start), _marker("start", second_start)],
            lambda before: activity,  # noqa: B023
        )
        (gap,) = gaps
        assert gap.kind == "unclean"
        assert gap.disconnect_ns == first_start


def test_open_session_and_zero_downtime_day_produce_no_records() -> None:
    # A running recorder (start with no end yet) is not downtime.
    assert derive_downtime_gaps([_marker("start", BASE_NS)], _no_activity) == []
    assert derive_downtime_gaps([], _no_activity) == []


def test_overlapping_feed_and_downtime_gaps_union_not_double_count() -> None:
    span = (BASE_NS, BASE_NS + 1000 * NS_PER_S)
    feed = GapRecord(
        venue="kraken",
        disconnect_ns=BASE_NS + 100 * NS_PER_S,
        reconnect_ns=BASE_NS + 300 * NS_PER_S,
        duration_ms=200_000,
        reason="test feed gap",
    )
    downtime = GapRecord(
        venue="kraken",
        disconnect_ns=BASE_NS + 200 * NS_PER_S,
        reconnect_ns=BASE_NS + 400 * NS_PER_S,
        duration_ms=200_000,
        reason="test downtime",
        kind="downtime",
    )

    accounts = account_gaps([feed, downtime], span, DAY_BOUNDS)

    # Union is 100→400s = 300s, not 200+200 = 400s.
    assert accounts.gap_ms_in_span == 300_000
    assert (accounts.feed_gaps_in_span, accounts.feed_gap_ms_in_span) == (1, 200_000)
    assert (accounts.downtime_gaps_in_span, accounts.downtime_gap_ms_in_span) == (1, 200_000)
    assert (accounts.unclean_gaps_in_span, accounts.unclean_gap_ms_in_span) == (0, 0)


def test_mixed_kinds_stay_bounded_by_the_recorded_span() -> None:
    """Stage 1.6 invariant with kinds mixed: heavily overlapping feed, downtime
    and unclean windows clamp to the span instead of exceeding it."""
    span = (BASE_NS, BASE_NS + 100 * NS_PER_S)
    records = [
        GapRecord(
            venue="kraken",
            disconnect_ns=BASE_NS - 50 * NS_PER_S,
            reconnect_ns=BASE_NS + 80 * NS_PER_S,
            duration_ms=130_000,
            reason="feed, straddles span start",
        ),
        GapRecord(
            venue="kraken",
            disconnect_ns=BASE_NS + 10 * NS_PER_S,
            reconnect_ns=BASE_NS + 200 * NS_PER_S,
            duration_ms=190_000,
            reason="downtime, straddles span end",
            kind="downtime",
        ),
        GapRecord(
            venue="kraken",
            disconnect_ns=BASE_NS + 20 * NS_PER_S,
            reconnect_ns=BASE_NS + 90 * NS_PER_S,
            duration_ms=70_000,
            reason="unclean, inside both",
            kind="unclean",
        ),
    ]

    accounts = account_gaps(records, span, DAY_BOUNDS)

    span_ms = (span[1] - span[0]) // 1_000_000
    assert accounts.gap_ms_in_span <= span_ms
    assert accounts.gap_ms_in_span == span_ms  # windows fully cover the span
    for kind_ms in (
        accounts.feed_gap_ms_in_span,
        accounts.downtime_gap_ms_in_span,
        accounts.unclean_gap_ms_in_span,
    ):
        assert kind_ms <= span_ms


def test_coverage_numerator_excludes_downtime(tmp_path: Path) -> None:
    """A book left "valid" across recorder downtime must not credit the hole
    as covered time: 5 minutes of data, 5 minutes down, 5 minutes of data is
    ~10 minutes of coverage, never ~15."""
    import orjson

    from data.config import AppConfig, load_config
    from data.validate.replay import validate_venue_day

    def message(seq: int, kind: str) -> str:
        updates = [
            {"side": "bid", "price_level": "50000.0", "new_quantity": "1.0"},
            {"side": "offer", "price_level": "50001.0", "new_quantity": "1.0"},
        ]
        body = {
            "channel": "l2_data",
            "sequence_num": seq,
            "events": [{"type": kind, "product_id": "BTC-USD", "updates": updates}],
        }
        return orjson.dumps(body).decode()

    writer = RawFileWriter(tmp_path / "raw", "coinbase")
    try:
        writer.write(BASE_NS, message(0, "snapshot"))
        for i in range(1, 300):
            writer.write(BASE_NS + i * NS_PER_S, message(i, "update"))
        for i in range(300, 601):
            writer.write(BASE_NS + (300 + i) * NS_PER_S, message(i, "update"))
    finally:
        writer.close()
    sessions = SessionLogger(tmp_path / "raw", "coinbase")
    sessions.log("end", BASE_NS + 300 * NS_PER_S)
    sessions.log("start", BASE_NS + 600 * NS_PER_S)

    cfg = AppConfig(data_root=tmp_path, logs_dir=tmp_path / "logs", venues=load_config().venues)
    report = validate_venue_day(cfg, "coinbase", "2026-07-30")

    assert report.downtime_gaps == 1
    assert report.downtime_gap_ms == 300_000
    assert report.feed_gaps == 0
    assert report.gap_ms_excluded == 300_000
    (symbol,) = report.symbols
    # ~600 s of real data out of 86,400: ≈0.69%. Crediting the 300 s hole
    # would report ≈1.04%.
    assert 0.6 < symbol.valid_coverage_day_pct < 0.75


def test_last_activity_ns_finds_final_message_before_cutoff(tmp_path: Path) -> None:
    writer = RawFileWriter(tmp_path, "kraken")
    try:
        for i in range(5):
            writer.write(BASE_NS + i * NS_PER_S, '{"channel":"book"}')
    finally:
        writer.close()
    cutoff = BASE_NS + 3 * NS_PER_S  # messages at +0..+4 s; last one before is +2 s

    assert last_activity_ns(tmp_path, "kraken", cutoff) == BASE_NS + 2 * NS_PER_S
    assert last_activity_ns(tmp_path, "kraken", BASE_NS) is None
    assert last_activity_ns(tmp_path, "nosuch", cutoff) is None
