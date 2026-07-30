"""BookBuilder: replay of real recorded messages plus targeted unit behaviour."""

from __future__ import annotations

from decimal import Decimal

import orjson

from data.book import ApplyResult, BookBuilder, SequenceTracker, parse_coinbase, parse_kraken
from data.book.coinbase_parse import envelope_sequence
from data.book.kraken_checksum import checksum_fn_for
from data.book.types import BookEvent, Level
from data.validate.stats import ArrivalHistogram
from tests.conftest import FIXTURES_DIR


def _fixture_lines(name: str) -> list[str]:
    text = (FIXTURES_DIR / name).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def _event(
    *,
    is_snapshot: bool,
    bids: list[tuple[str, str]] | None = None,
    asks: list[tuple[str, str]] | None = None,
    seq: int | None = None,
    checksum: int | None = None,
) -> BookEvent:
    return BookEvent(
        venue="test",
        symbol="TEST/USD",
        recv_ns=1,
        is_snapshot=is_snapshot,
        bids=tuple(Level(Decimal(p), Decimal(q)) for p, q in (bids or [])),
        asks=tuple(Level(Decimal(p), Decimal(q)) for p, q in (asks or [])),
        seq=seq,
        checksum=checksum,
    )


# --- replay of real recorded data -------------------------------------------


def test_kraken_fixture_replays_with_zero_checksum_failures() -> None:
    """The strongest correctness proof available: Kraken's own CRC32 agrees
    with our reconstruction for the snapshot and all 60 recorded updates."""
    builder = BookBuilder("kraken", "BTC/USD", depth=100, checksum_fn=checksum_fn_for(1, 8))

    applied = 0
    for line in _fixture_lines("kraken_messages.ndjson"):
        for event in parse_kraken(orjson.loads(line), recv_ns=applied):
            result = builder.apply(event)
            assert result in (ApplyResult.SNAPSHOT, ApplyResult.APPLIED), result
            applied += 1

    assert builder.snapshots_applied == 1
    assert builder.events_applied == 60
    assert builder.checksum_failures == 0
    assert builder.crossed_events == 0
    assert builder.valid
    best_bid, best_ask = builder.best_bid, builder.best_ask
    assert best_bid is not None and best_ask is not None
    assert best_bid.price < best_ask.price


def test_kraken_parser_ignores_non_book_messages() -> None:
    non_book = [
        line for line in _fixture_lines("kraken_messages.ndjson") if '"channel":"book"' not in line
    ]
    assert non_book, "fixture should contain status/ack/trade messages"
    for line in non_book:
        assert parse_kraken(orjson.loads(line), recv_ns=0) == []


def test_coinbase_fixture_is_sequence_contiguous_and_builds_valid_books() -> None:
    tracker = SequenceTracker()
    builders: dict[str, BookBuilder] = {}

    for index, line in enumerate(_fixture_lines("coinbase_messages.ndjson")):
        message = orjson.loads(line)
        seq = envelope_sequence(message)
        assert seq is not None, "every Advanced Trade message carries sequence_num"
        seq_ok = tracker.observe(seq)
        for event in parse_coinbase(message, recv_ns=index):
            builder = builders.setdefault(
                event.symbol, BookBuilder("coinbase", event.symbol, depth=100)
            )
            builder.apply(event, seq_ok=seq_ok)

    assert tracker.gaps == 0
    assert builders, "fixture should contain l2_data"
    for builder in builders.values():
        assert builder.valid
        assert builder.crossed_events == 0
        assert builder.seq_gaps == 0


# --- unit behaviour ----------------------------------------------------------


def test_snapshot_application_replaces_state() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=10)
    # Read through a local: asserting on the attribute directly would narrow
    # it to Literal[False] for the rest of the function under mypy.
    starts_valid = builder.valid
    assert starts_valid is False

    result = builder.apply(
        _event(is_snapshot=True, bids=[("100", "1"), ("99", "2")], asks=[("101", "3")])
    )

    assert result is ApplyResult.SNAPSHOT
    assert builder.valid
    assert builder.best_bid == Level(Decimal("100"), Decimal("1"))
    assert builder.best_ask == Level(Decimal("101"), Decimal("3"))
    assert builder.mid == Decimal("100.5")


def test_incremental_update_changes_levels() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=10)
    builder.apply(_event(is_snapshot=True, bids=[("100", "1")], asks=[("101", "1")]))

    builder.apply(_event(is_snapshot=False, bids=[("100.5", "2")]))

    assert builder.best_bid == Level(Decimal("100.5"), Decimal("2"))


def test_zero_quantity_removes_level() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=10)
    builder.apply(_event(is_snapshot=True, bids=[("100", "1"), ("99", "5")], asks=[("101", "1")]))

    builder.apply(_event(is_snapshot=False, bids=[("100", "0")]))

    assert builder.best_bid == Level(Decimal("99"), Decimal("5"))


def test_updates_ignored_while_invalid_until_fresh_snapshot() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=10)
    builder.apply(_event(is_snapshot=True, bids=[("100", "1")], asks=[("101", "1")]))

    gap_result = builder.apply(_event(is_snapshot=False, bids=[("100", "2")]), seq_ok=False)
    assert gap_result is ApplyResult.SEQ_GAP
    valid_after_gap = builder.valid
    assert valid_after_gap is False
    assert builder.seq_gaps == 1

    ignored = builder.apply(_event(is_snapshot=False, bids=[("100", "3")]))
    assert ignored is ApplyResult.IGNORED_INVALID
    assert builder.ignored_while_invalid == 1

    restored = builder.apply(_event(is_snapshot=True, bids=[("102", "1")], asks=[("103", "1")]))
    assert restored is ApplyResult.SNAPSHOT
    assert builder.valid
    assert builder.best_bid == Level(Decimal("102"), Decimal("1"))


def test_crossed_and_locked_books_are_counted_not_repaired() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=10)
    builder.apply(_event(is_snapshot=True, bids=[("100", "1")], asks=[("101", "1")]))

    builder.apply(_event(is_snapshot=False, bids=[("102", "1")]))
    assert builder.is_crossed
    assert builder.crossed_events == 1
    assert builder.valid  # flagged, never silently repaired

    builder.apply(_event(is_snapshot=False, bids=[("102", "0"), ("101", "1")]))
    assert builder.is_locked
    assert builder.locked_events == 1


def test_checksum_failure_invalidates_book() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=10, checksum_fn=lambda bids, asks: 12345)
    builder.apply(_event(is_snapshot=True, bids=[("100", "1")], asks=[("101", "1")]))

    result = builder.apply(_event(is_snapshot=False, bids=[("100", "2")], checksum=99999))

    assert result is ApplyResult.CHECKSUM_FAILED
    assert builder.checksum_failures == 1
    assert not builder.valid


def test_depth_truncation_keeps_best_levels() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=2)
    builder.apply(
        _event(
            is_snapshot=True,
            bids=[("100", "1"), ("99", "1"), ("98", "1")],
            asks=[("101", "1"), ("102", "1"), ("103", "1")],
        )
    )

    assert [lv.price for lv in builder.bid_levels(10)] == [Decimal("100"), Decimal("99")]
    assert [lv.price for lv in builder.ask_levels(10)] == [Decimal("101"), Decimal("102")]


def test_microprice_is_queue_weighted() -> None:
    builder = BookBuilder("test", "TEST/USD", depth=10)
    builder.apply(_event(is_snapshot=True, bids=[("100", "3")], asks=[("101", "1")]))

    # (bid_qty*ask_px + ask_qty*bid_px) / total = (3*101 + 1*100) / 4
    assert builder.microprice == Decimal("403") / 4


def test_sequence_tracker_detects_forward_gaps_and_resets_backward() -> None:
    tracker = SequenceTracker()
    assert tracker.observe(1)
    assert tracker.observe(2)
    assert not tracker.observe(5)  # forward jump = data loss
    assert tracker.gaps == 1
    assert tracker.observe(6)
    assert tracker.observe(1)  # backward = new connection, not a gap
    assert tracker.gaps == 1
    assert tracker.observe(2)


def test_arrival_histogram_percentiles() -> None:
    hist = ArrivalHistogram()
    for _ in range(98):
        hist.add(0.4)  # falls in the ≤0.5 ms bucket
    hist.add(60.0)
    hist.add(2_000.0)

    stats = hist.snapshot()
    assert stats.count == 100
    assert stats.p50_ms == 0.5
    assert stats.p99_ms == 100.0
    assert stats.max_ms == 2_000.0
