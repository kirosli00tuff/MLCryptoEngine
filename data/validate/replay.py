"""Replay one venue-day from raw capture, score it, and regenerate processed output.

This is the only replay implementation in the codebase: `make validate` both
rebuilds the processed book snapshots (idempotently, via the store layer) and
computes the quality metrics that decide whether Phase A passes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import orjson
from pydantic import BaseModel, Field

from data.book import BookBuilder, SequenceTracker, SnapshotEmitter, parse_coinbase, parse_kraken
from data.book.builder import ApplyResult
from data.book.coinbase_parse import envelope_sequence
from data.book.kraken_checksum import checksum_fn_for
from data.book.types import BookEvent
from data.config import AppConfig
from data.recorder.gaps import GapRecord, read_gaps
from data.recorder.reader import iter_day_records
from data.store import write_book_day
from data.validate.stats import ArrivalHistogram, ArrivalStats

NS_PER_S = 1_000_000_000
DAY_NS = 86_400 * NS_PER_S
# A crossed book or sequence anomaly this close to a logged reconnect is
# attributed to the reconnect rather than counted as a reconstruction failure.
GAP_SLACK_BEFORE_NS = 1 * NS_PER_S
GAP_SLACK_AFTER_NS = 5 * NS_PER_S
FULL_DAY_THRESHOLD = 0.999


class SymbolReport(BaseModel):
    symbol: str
    events_applied: int
    snapshots: int
    seq_gaps: int
    seq_gaps_unexplained: int
    checksum_failures: int
    checksum_failures_unexplained: int
    crossed_total: int
    crossed_unexplained: int
    locked_total: int
    valid_coverage_day_pct: float
    valid_coverage_excl_gaps_pct: float
    snapshot_compares: int
    snapshot_mismatches: int
    rows_written: int


class DayReport(BaseModel):
    venue: str
    date: str
    msgs_total: int
    channel_counts: dict[str, int]
    first_ns: int | None
    last_ns: int | None
    feed_gaps: int
    feed_gap_ms: int
    arrival: ArrivalStats
    symbols: list[SymbolReport]
    passed: bool
    failure_reasons: list[str] = Field(default_factory=list)


def _day_bounds_ns(date: str) -> tuple[int, int]:
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    start_ns = int(start.timestamp() * NS_PER_S)
    return start_ns, start_ns + DAY_NS


def _explained(ts: int, gaps: list[GapRecord]) -> bool:
    return any(
        gap.disconnect_ns - GAP_SLACK_BEFORE_NS <= ts <= gap.reconnect_ns + GAP_SLACK_AFTER_NS
        for gap in gaps
    )


def _snapshot_tob(event: BookEvent) -> tuple[Decimal | None, Decimal | None]:
    best_bid = max((lv.price for lv in event.bids if lv.qty > 0), default=None)
    best_ask = min((lv.price for lv in event.asks if lv.qty > 0), default=None)
    return best_bid, best_ask


def validate_venue_day(cfg: AppConfig, venue: str, date: str) -> DayReport:
    """Replay, score, and persist one venue-day. Raises on unsupported venues."""
    if venue not in ("kraken", "coinbase"):
        raise ValueError(f"No replay support for venue '{venue}'")
    vcfg = cfg.venues[venue]

    builders: dict[str, BookBuilder] = {}
    emitters: dict[str, SnapshotEmitter] = {}
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    last_event_ns: dict[str, int] = {}
    valid_ns: dict[str, int] = defaultdict(int)
    anomaly_ns: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {"crossed": [], "seq": [], "checksum": []}
    )
    snap_compares: dict[str, int] = defaultdict(int)
    snap_mismatches: dict[str, int] = defaultdict(int)

    tracker = SequenceTracker()
    channel_counts: Counter[str] = Counter()
    hist = ArrivalHistogram()
    msgs_total = 0
    prev_ns: int | None = None
    first_ns: int | None = None
    last_ns: int | None = None

    def builder_for(symbol: str) -> BookBuilder:
        if symbol not in builders:
            checksum_fn = None
            if venue == "kraken":
                inst = vcfg.instruments.get(symbol)
                if inst is not None:
                    checksum_fn = checksum_fn_for(inst.price_decimals, inst.qty_decimals)
            builders[symbol] = BookBuilder(venue, symbol, vcfg.book_depth, checksum_fn)
            emitters[symbol] = SnapshotEmitter(
                builders[symbol], cfg.book.interval_snapshot_ms, cfg.book.snapshot_depth
            )
        return builders[symbol]

    for recv_ns, raw in iter_day_records(cfg.raw_dir, venue, date):
        msgs_total += 1
        if first_ns is None:
            first_ns = recv_ns
        last_ns = recv_ns
        if prev_ns is not None:
            hist.add((recv_ns - prev_ns) / 1_000_000)
        prev_ns = recv_ns

        message = orjson.loads(raw)
        if not isinstance(message, dict):
            channel_counts["non_object"] += 1
            continue
        channel = message.get("channel") or message.get("method") or message.get("type")
        channel_counts[str(channel or "unknown")] += 1

        if venue == "coinbase":
            seq = envelope_sequence(message)
            seq_ok = tracker.observe(seq) if seq is not None else True
            events = parse_coinbase(message, recv_ns)
        else:
            seq_ok = True
            events = parse_kraken(message, recv_ns)

        for event in events:
            builder = builder_for(event.symbol)
            marks = anomaly_ns[event.symbol]

            if event.is_snapshot and builder.valid:
                snap_compares[event.symbol] += 1
                prev_bid, prev_ask = builder.best_bid, builder.best_ask
                snap_bid, snap_ask = _snapshot_tob(event)
                if (prev_bid.price if prev_bid else None) != snap_bid or (
                    prev_ask.price if prev_ask else None
                ) != snap_ask:
                    snap_mismatches[event.symbol] += 1

            if event.symbol in last_event_ns and builder.valid:
                valid_ns[event.symbol] += recv_ns - last_event_ns[event.symbol]
            last_event_ns[event.symbol] = recv_ns

            crossed_before = builder.crossed_events
            result = builder.apply(event, seq_ok=seq_ok)
            if builder.crossed_events > crossed_before:
                marks["crossed"].append(recv_ns)
            if result is ApplyResult.SEQ_GAP:
                marks["seq"].append(recv_ns)
            elif result is ApplyResult.CHECKSUM_FAILED:
                marks["checksum"].append(recv_ns)

            rows[event.symbol].extend(emitters[event.symbol].on_event(recv_ns, event.seq))

    day_start_ns, day_end_ns = _day_bounds_ns(date)
    gaps = [g for g in read_gaps(cfg.raw_dir, venue) if g.overlaps_ns(day_start_ns, day_end_ns)]
    gap_ns_in_day = sum(
        min(g.reconnect_ns, day_end_ns) - max(g.disconnect_ns, day_start_ns) for g in gaps
    )

    symbol_reports: list[SymbolReport] = []
    for symbol, builder in sorted(builders.items()):
        written = 0
        if rows[symbol]:
            write_book_day(cfg.processed_dir, venue, symbol, date, rows[symbol])
            written = len(rows[symbol])
        marks = anomaly_ns[symbol]
        covered = valid_ns[symbol]
        denominator_excl = max(DAY_NS - gap_ns_in_day, 1)
        symbol_reports.append(
            SymbolReport(
                symbol=symbol,
                events_applied=builder.events_applied,
                snapshots=builder.snapshots_applied,
                seq_gaps=builder.seq_gaps,
                seq_gaps_unexplained=sum(1 for t in marks["seq"] if not _explained(t, gaps)),
                checksum_failures=builder.checksum_failures,
                checksum_failures_unexplained=sum(
                    1 for t in marks["checksum"] if not _explained(t, gaps)
                ),
                crossed_total=builder.crossed_events,
                crossed_unexplained=sum(1 for t in marks["crossed"] if not _explained(t, gaps)),
                locked_total=builder.locked_events,
                valid_coverage_day_pct=round(100 * covered / DAY_NS, 3),
                valid_coverage_excl_gaps_pct=round(100 * covered / denominator_excl, 3),
                snapshot_compares=snap_compares[symbol],
                snapshot_mismatches=snap_mismatches[symbol],
                rows_written=written,
            )
        )

    failure_reasons: list[str] = []
    if not symbol_reports:
        failure_reasons.append("no book data found for this venue-day")
    for report in symbol_reports:
        prefix = f"{report.symbol}: "
        if report.crossed_unexplained:
            failure_reasons.append(
                f"{prefix}{report.crossed_unexplained} unexplained crossed books"
            )
        if report.seq_gaps_unexplained:
            failure_reasons.append(f"{prefix}{report.seq_gaps_unexplained} unexplained seq gaps")
        if report.checksum_failures_unexplained:
            failure_reasons.append(
                f"{prefix}{report.checksum_failures_unexplained} unexplained checksum failures"
            )
        if report.valid_coverage_excl_gaps_pct < FULL_DAY_THRESHOLD * 100:
            failure_reasons.append(
                f"{prefix}coverage outside gaps {report.valid_coverage_excl_gaps_pct:.2f}% "
                f"< {FULL_DAY_THRESHOLD:.1%}"
            )

    return DayReport(
        venue=venue,
        date=date,
        msgs_total=msgs_total,
        channel_counts=dict(channel_counts),
        first_ns=first_ns,
        last_ns=last_ns,
        feed_gaps=len(gaps),
        feed_gap_ms=gap_ns_in_day // 1_000_000,
        arrival=hist.snapshot(),
        symbols=symbol_reports,
        passed=not failure_reasons,
        failure_reasons=failure_reasons,
    )
