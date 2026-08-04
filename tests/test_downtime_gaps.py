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

import pytest

from data.recorder.gaps import GapRecord, NegativeGapError
from data.recorder.sessions import SessionLogger, SessionMarker, read_sessions
from data.recorder.writer import RawFileWriter
from data.validate.downtime import derive_downtime_gaps, last_activity_ns
from data.validate.replay import account_gaps

NS_PER_S = 1_000_000_000
# 2026-07-30T12:00:00Z, consistent with the other synthetic-day tests.
BASE_NS = 1_785_412_800 * NS_PER_S
DAY_BOUNDS = (BASE_NS - 12 * 3600 * NS_PER_S, BASE_NS + 12 * 3600 * NS_PER_S)

# data/raw/venue=kraken/sessions.jsonl as it actually stands, in file order,
# including the 2026-08-01T07:26:17 restart where the outgoing process wrote
# its `end` after the incoming process had already written its `start`. Copied
# verbatim rather than synthesised: the point of the regression test is that
# this exact sequence pairs correctly.
ON_DISK_MARKERS: tuple[tuple[str, int], ...] = (
    ("end", 1785546400445906000),  # 08-01 01:06:40.445906
    ("start", 1785568319279027000),  # 08-01 07:11:59.279027
    ("end", 1785568373345944000),  # 08-01 07:12:53.345944
    ("start", 1785568373681722000),  # 08-01 07:12:53.681722
    ("start", 1785569177909450362),  # 08-01 07:26:17.909450  <-- written first
    ("end", 1785569177581971000),  # 08-01 07:26:17.581971  <-- but 327 ms earlier
    ("end", 1785610319364569957),  # 08-01 18:51:59.364570
    ("start", 1785610319913102461),  # 08-01 18:51:59.913102
    ("end", 1785822040408043821),  # 08-04 05:40:40.408044
    ("start", 1785822040982369422),  # 08-04 05:40:40.982369
)


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


def test_out_of_order_markers_on_disk_pair_by_timestamp_not_file_position(
    tmp_path: Path,
) -> None:
    """The real sessions.jsonl, written through the real logger, in file order.

    Two processes append to this file during every restart, so a start can and
    does land above the end it follows. Pairing sequentially would read the
    07:26:17 restart as a 602 ms *unclean termination* — a graceful systemd
    restart reported as a crash — and would lose the 327 ms clean downtime gap
    entirely. ``_no_activity`` raises if the unclean path is ever taken, so
    that misreading cannot pass silently here.
    """
    # Arrange
    logger = SessionLogger(tmp_path, "kraken")
    for event, ts_ns in ON_DISK_MARKERS:
        logger.log(event, ts_ns)  # type: ignore[arg-type]
    markers = read_sessions(tmp_path, "kraken")
    assert [m.ts_ns for m in markers] == [ts for _, ts in ON_DISK_MARKERS], (
        "read_sessions preserves file order — reordering is the derivation's job"
    )

    # Act
    gaps = derive_downtime_gaps(markers, _no_activity)

    # Assert: five clean stop/start pairs, none of them unclean.
    assert [g.kind for g in gaps] == ["downtime"] * 5
    assert [(g.disconnect_ns, g.reconnect_ns) for g in gaps] == [
        (1785546400445906000, 1785568319279027000),
        (1785568373345944000, 1785568373681722000),
        (1785569177581971000, 1785569177909450362),  # the out-of-order pair
        (1785610319364569957, 1785610319913102461),
        (1785822040408043821, 1785822040982369422),
    ]
    assert [g.duration_ms for g in gaps] == [21_918_833, 335, 327, 548, 574]
    assert all(g.reconnect_ns >= g.disconnect_ns for g in gaps), "no gap runs backwards"
    assert sorted(g.disconnect_ns for g in gaps) == [g.disconnect_ns for g in gaps]


def test_markers_sharing_a_timestamp_read_end_before_start() -> None:
    """A restart fast enough to stamp both markers identically is a zero-length
    stop, not an unclean termination. Ordering ends first at a tie is what makes
    the tie-break deterministic instead of dependent on which process won."""
    # Arrange: start written first, same nanosecond on both.
    shared = BASE_NS + 42
    markers = [
        _marker("start", BASE_NS - 3600 * NS_PER_S),
        _marker("start", shared),
        _marker("end", shared),
    ]

    # Act
    gaps = derive_downtime_gaps(markers, _no_activity)

    # Assert
    assert gaps == [], "zero-length stop produces no gap, and never an unclean one"


def test_a_backwards_gap_is_refused_rather_than_silently_produced() -> None:
    """The Stage 1.6 invariant, applied to the window itself.

    After ordering by ts_ns this is structurally unreachable, which is the
    point: if it ever fires, the ordering or the marker file is corrupt.
    Silently dropping the pair — what the previous guard did — would have hidden
    exactly that, and merge_windows drops inverted windows too, so a negative
    gap would vanish from the union while still being counted per-kind.
    """
    with pytest.raises(NegativeGapError, match="cannot run backwards"):
        GapRecord(
            venue="kraken",
            disconnect_ns=BASE_NS,
            reconnect_ns=BASE_NS - 327_479_362,  # the real 327 ms, inverted
            duration_ms=-327,
            reason="end paired with a start that preceded it",
            kind="downtime",
        )

    # Zero-length stays legal: a reconnect inside the clock's resolution is real.
    assert (
        GapRecord(
            venue="kraken",
            disconnect_ns=BASE_NS,
            reconnect_ns=BASE_NS,
            duration_ms=0,
            reason="instantaneous",
            kind="downtime",
        ).duration_ms
        == 0
    )


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
