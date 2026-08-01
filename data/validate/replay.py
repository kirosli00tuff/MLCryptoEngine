"""Replay one venue-day from raw capture, score it, and regenerate processed output.

This is the only replay implementation in the codebase: `make validate` both
rebuilds the processed book snapshots (idempotently, via the store layer) and
computes the quality metrics that decide whether Phase A passes.

Memory is bounded regardless of day size: events stream through the current
book state plus running aggregates, and snapshot rows stream to Parquet as
they are emitted. Nothing per-message is retained — a full day at tens of
millions of messages replays in a few hundred MB of RSS. (The original
implementation materialized every emitted row per symbol and was OOM-killed
at 12.8 GB replaying the first real full day.)
"""

from __future__ import annotations

import time
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import orjson
from pydantic import BaseModel, Field

from data.book import (
    BookBuilder,
    SequenceTracker,
    SnapshotEmitter,
    parse_coinbase,
    parse_hyperliquid,
    parse_kraken,
)
from data.book.builder import ApplyResult
from data.book.coinbase_parse import envelope_sequence
from data.book.kraken_checksum import checksum_fn_for
from data.book.types import BookEvent
from data.config import AppConfig
from data.recorder.gaps import GapRecord, merge_windows, read_gaps
from data.recorder.reader import iter_day_records
from data.recorder.sessions import read_sessions
from data.store import BookDayWriter
from data.validate.downtime import derive_downtime_gaps, last_activity_ns
from data.validate.integrity import (
    CHECKSUM,
    IntegrityReport,
    describe,
    mechanisms_for,
    uncertified_reason,
)
from data.validate.stats import ArrivalHistogram, ArrivalStats
from data.validate.warmup import WarmupResult, warm_up


class GapAccountingError(RuntimeError):
    """Gap records contradict recorded data; nothing downstream is trustworthy."""


NS_PER_S = 1_000_000_000
DAY_NS = 86_400 * NS_PER_S
# A crossed book or sequence anomaly this close to a logged reconnect is
# attributed to the reconnect rather than counted as a reconstruction failure.
GAP_SLACK_BEFORE_NS = 1 * NS_PER_S
GAP_SLACK_AFTER_NS = 5 * NS_PER_S
FULL_DAY_THRESHOLD = 0.999
# A full-day replay runs for many minutes; without periodic progress a working
# process is indistinguishable from a hung one.
PROGRESS_EVERY_MSGS = 1_000_000
# Snapshot-stream cadence scoring (Hyperliquid): the l2Book minimum push
# interval is ~0.5 s; an interval above STALE is counted as materially above
# block cadence (observed quiet-market intervals reach ~5 s), and an
# unexplained interval above SILENT fails the day — a snapshot stream silent
# for a minute outside logged gaps is missing data, not a quiet market.
CADENCE_STALE_MS = 10_000
CADENCE_SILENT_FAIL_MS = 60_000

PARSE_FNS = {
    "kraken": parse_kraken,
    "coinbase": parse_coinbase,
    "hyperliquid": parse_hyperliquid,
}


class SymbolReport(BaseModel):
    """Per-symbol scorecard. ``None`` on a check means "not applicable to this
    venue" — a venue that provides no sequence numbers reports ``None``, never
    ``0``, so an unavailable check can never be read as a clean one."""

    symbol: str
    events_applied: int
    snapshots: int
    seq_gaps: int | None
    seq_gaps_unexplained: int | None
    checksum_failures: int | None
    checksum_failures_unexplained: int | None
    checksums_verified: int | None
    crossed_total: int
    crossed_unexplained: int
    locked_total: int
    valid_coverage_day_pct: float
    valid_coverage_excl_gaps_pct: float
    snapshot_compares: int
    snapshot_mismatches: int
    rows_written: int
    # Snapshot-cadence scoring, populated only for snapshot-stream venues
    # (None elsewhere — the Stage 1.6 rule: not-applicable is never 0).
    snap_intervals: int | None = None
    snap_interval_p50_ms: float | None = None
    snap_interval_p95_ms: float | None = None
    snap_interval_max_ms: float | None = None
    snap_stale: int | None = None
    snap_stale_unexplained: int | None = None
    # Book state at the end of the replay — real, but only as fresh as the
    # last `make validate` run; consumers must label it that way.
    last_mid: float | None = None
    last_spread: float | None = None
    last_bid_levels: int = 0
    last_ask_levels: int = 0


class GapAccounts(BaseModel):
    """Union-based, span-clamped gap accounting for one venue-day.

    ``gaps_in_span``/``gap_ms_in_span`` describe the union across all gap
    kinds — what coverage actually excludes. The per-kind fields report each
    cause separately (each its own clamped union), so feed gaps and recorder
    downtime are never conflated; where kinds overlap, the per-kind sums can
    exceed the overall union, which is why only the union feeds coverage.
    """

    gaps_in_span: int
    gap_ms_in_span: int
    feed_gaps_in_span: int = 0
    feed_gap_ms_in_span: int = 0
    downtime_gaps_in_span: int = 0
    downtime_gap_ms_in_span: int = 0
    unclean_gaps_in_span: int = 0
    unclean_gap_ms_in_span: int = 0
    gaps_partially_outside_span: int
    gap_ms_clipped_outside_span: int
    gaps_outside_span: int
    gap_ms_outside_span: int
    gap_ns_excluded_from_day: int


class DayReport(BaseModel):
    venue: str
    date: str
    msgs_total: int
    channel_counts: dict[str, int]
    first_ns: int | None
    last_ns: int | None
    # Receive timestamp of the previous-day snapshot the replay warmed up
    # from; None when the day replayed cold (no usable prior-day snapshot).
    warmup_start_ns: int | None = None
    # True for venues whose book feed is a full-snapshot stream: warm start is
    # structurally unnecessary and the report says so instead of warning.
    snapshot_stream: bool = False
    # Per-cause gap reporting: feed gaps (the venue dropped us) vs recorder
    # downtime (we were not there) vs unclean terminations (we died without a
    # shutdown record). Coverage excludes the union of all kinds.
    feed_gaps: int
    feed_gap_ms: int
    downtime_gaps: int = 0
    downtime_gap_ms: int = 0
    unclean_gaps: int = 0
    unclean_gap_ms: int = 0
    gap_ms_excluded: int = 0
    gaps_partially_outside_span: int
    gap_ms_clipped_outside_span: int
    gaps_outside_span: int
    gap_ms_outside_span: int
    arrival: ArrivalStats
    integrity: IntegrityReport
    symbols: list[SymbolReport]
    passed: bool
    failure_reasons: list[str] = Field(default_factory=list)


def _clip(windows: list[tuple[int, int]], lo: int, hi: int) -> list[tuple[int, int]]:
    """Intersect half-open ``[start, end)`` windows with ``[lo, hi)``.

    Windows falling entirely outside — and any window whose intersection is
    empty — are dropped, so the result only ever describes time inside the
    bound. Never widens a window.
    """
    clipped = [(max(start, lo), min(end, hi)) for start, end in windows]
    return [(start, end) for start, end in clipped if end > start]


def _in_scope(gap: GapRecord, span: tuple[int, int], day_bounds: tuple[int, int]) -> bool:
    """True if ``gap`` overlaps both the calendar day and the recorded span.

    Half-open ``[start, end)`` on both bounds, delegating to
    :meth:`GapRecord.overlaps_ns` so gap scoping, :func:`merge_windows`, and
    :func:`_clip` all share one convention: a gap ending exactly at
    ``span_start`` does not touch the span, and neither does one starting
    exactly at ``span_end``.
    """
    return gap.overlaps_ns(*day_bounds) and gap.overlaps_ns(*span)


def gaps_touching_span(
    gaps: list[GapRecord],
    span: tuple[int, int] | None,
    day_bounds: tuple[int, int],
) -> list[GapRecord]:
    """The gap records in scope for a venue-day: overlapping the day *and* the span.

    The single definition of "in scope". Coverage accounting
    (:func:`account_gaps`) and anomaly explanation (:func:`_explained`) both
    consume it, so the two can never drift into disagreeing about which gaps
    are real holes in recorded data.
    """
    if span is None:
        return []
    return [g for g in gaps if _in_scope(g, span, day_bounds)]


def account_gaps(
    gaps: list[GapRecord],
    span: tuple[int, int] | None,
    day_bounds: tuple[int, int],
) -> GapAccounts:
    """Attribute gap records to a venue-day, merged (never summed) and clamped.

    Only gaps that touch the recorded span count against coverage: a gap logged
    while nothing was being recorded (for example an earlier failed session the
    same day) is unrecorded time, not a hole in recorded data. Such records are
    still surfaced — as ``gaps_outside_span`` — never silently dropped.

    Gap time is counted at its *intersection* with ``[span_start, span_end)``,
    never at the window's full duration. A gap that began before recording
    started contributes only the part that overlaps the recording; the trimmed
    remainder is reported as ``gap_ms_clipped_outside_span`` against
    ``gaps_partially_outside_span`` records, so clamping is visible rather than
    silent. Counting the untrimmed duration is the same class of error as
    counting out-of-span gaps at all: time that is not a hole in recorded data.

    Invariant: unioned, span-clamped gap time can never exceed the span. After
    clamping this is structurally near-impossible to trip, which is the point —
    it no longer fires on an accounting artifact (the old unclamped sum), so a
    :class:`GapAccountingError` now means genuine corruption: ``merge_windows``
    returning overlapping windows, or a span whose end precedes its start
    (records read out of order). Either way the numbers are not trustworthy and
    this raises instead of producing coverage.
    """
    day_start, day_end = day_bounds
    in_day = [g for g in gaps if g.overlaps_ns(day_start, day_end)]

    if span is None:
        outside_windows = merge_windows((g.disconnect_ns, g.reconnect_ns) for g in in_day)
        return GapAccounts(
            gaps_in_span=0,
            gap_ms_in_span=0,
            gaps_partially_outside_span=0,
            gap_ms_clipped_outside_span=0,
            gaps_outside_span=len(in_day),
            gap_ms_outside_span=sum(e - s for s, e in outside_windows) // 1_000_000,
            gap_ns_excluded_from_day=0,
        )

    span_start, span_end = span
    in_records = [g for g in in_day if _in_scope(g, span, day_bounds)]
    out_records = [g for g in in_day if not _in_scope(g, span, day_bounds)]
    in_windows = merge_windows((g.disconnect_ns, g.reconnect_ns) for g in in_records)
    out_windows = merge_windows((g.disconnect_ns, g.reconnect_ns) for g in out_records)

    def kind_in_span(kind: str) -> tuple[int, int]:
        of_kind = [g for g in in_records if g.kind == kind]
        windows = merge_windows((g.disconnect_ns, g.reconnect_ns) for g in of_kind)
        clamped = _clip(windows, span_start, span_end)
        return len(of_kind), sum(e - s for s, e in clamped) // 1_000_000

    feed_n, feed_ms = kind_in_span("feed")
    downtime_n, downtime_ms = kind_in_span("downtime")
    unclean_n, unclean_ms = kind_in_span("unclean")

    span_windows = _clip(in_windows, span_start, span_end)
    in_span_ns = sum(e - s for s, e in span_windows)
    clipped_ns = sum(e - s for s, e in in_windows) - in_span_ns
    span_ns = span_end - span_start
    if in_span_ns > span_ns:
        raise GapAccountingError(
            f"{in_span_ns / 1e6:.0f} ms of unioned, span-clamped gap time inside a recorded "
            f"span of only {span_ns / 1e6:.0f} ms. Clamped gap time cannot exceed the span "
            "unless window merging or the recorded span itself is corrupt; distrust this "
            "venue-day entirely and investigate before using any downstream number."
        )

    return GapAccounts(
        gaps_in_span=len(in_records),
        gap_ms_in_span=in_span_ns // 1_000_000,
        feed_gaps_in_span=feed_n,
        feed_gap_ms_in_span=feed_ms,
        downtime_gaps_in_span=downtime_n,
        downtime_gap_ms_in_span=downtime_ms,
        unclean_gaps_in_span=unclean_n,
        unclean_gap_ms_in_span=unclean_ms,
        gaps_partially_outside_span=sum(
            1 for g in in_records if g.disconnect_ns < span_start or g.reconnect_ns > span_end
        ),
        gap_ms_clipped_outside_span=clipped_ns // 1_000_000,
        gaps_outside_span=len(out_records),
        gap_ms_outside_span=sum(e - s for s, e in out_windows) // 1_000_000,
        gap_ns_excluded_from_day=sum(e - s for s, e in _clip(span_windows, day_start, day_end)),
    )


def _day_bounds_ns(date: str) -> tuple[int, int]:
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    start_ns = int(start.timestamp() * NS_PER_S)
    return start_ns, start_ns + DAY_NS


def _explained(ts: int, gaps: list[GapRecord]) -> bool:
    return any(
        gap.disconnect_ns - GAP_SLACK_BEFORE_NS <= ts <= gap.reconnect_ns + GAP_SLACK_AFTER_NS
        for gap in gaps
    )


class _AnomalyLedger:
    """Unexplained-anomaly counting in bounded memory.

    The final unexplained count must be judged against the gaps that touch the
    recorded span, and the span is only known once the replay finishes — but
    retaining every anomaly timestamp until then is exactly the unbounded
    pattern that OOM-killed the first full-day validation. Instead: a
    timestamp nowhere near *any* logged gap window (a superset of the
    span-scoped list) is unexplained no matter what the span turns out to be,
    so it is counted immediately and discarded. Only timestamps within slack
    of some gap window are kept for re-evaluation against the span-scoped
    list. Semantics are identical to evaluating everything at the end; memory
    is bounded by anomalies adjacent to gap windows, which any credible
    venue-day has few of.
    """

    def __init__(self, candidate_gaps: list[GapRecord]) -> None:
        self._candidates = candidate_gaps
        self._definitely_unexplained = 0
        self._near_gap_ns: list[int] = []

    def mark(self, ts: int) -> None:
        if _explained(ts, self._candidates):
            self._near_gap_ns.append(ts)
        else:
            self._definitely_unexplained += 1

    def unexplained(self, span_gaps: list[GapRecord]) -> int:
        return self._definitely_unexplained + sum(
            1 for ts in self._near_gap_ns if not _explained(ts, span_gaps)
        )


def _rss_mb() -> float | None:
    """Current resident set size, or None where /proc is unavailable."""
    try:
        with Path("/proc/self/status").open(encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        return None
    return None


def _log_progress(venue: str, date: str, msgs: int, recv_ns: int, started: float) -> None:
    position = datetime.fromtimestamp(recv_ns / NS_PER_S, tz=UTC).strftime("%H:%M:%S")
    elapsed = time.monotonic() - started
    rss = _rss_mb()
    rss_part = f" · rss {rss:.0f} MB" if rss is not None else ""
    print(
        f"  {venue} {date}: {msgs:,} msgs · at {position}Z · {elapsed:.0f}s elapsed{rss_part}",
        flush=True,
    )


def _snapshot_tob(event: BookEvent) -> tuple[Decimal | None, Decimal | None]:
    best_bid = max((lv.price for lv in event.bids if lv.qty > 0), default=None)
    best_ask = min((lv.price for lv in event.asks if lv.qty > 0), default=None)
    return best_bid, best_ask


def validate_venue_day(cfg: AppConfig, venue: str, date: str) -> DayReport:
    """Replay, score, and persist one venue-day. Raises on unsupported venues."""
    if venue not in PARSE_FNS:
        raise ValueError(f"No replay support for venue '{venue}'")
    vcfg = cfg.venues[venue]
    mechanisms = mechanisms_for(vcfg)
    seq_applies = vcfg.sequence_numbers
    checksum_applies = vcfg.snapshot.checksum

    # Gap records are loaded up front so anomalies can be triaged as they
    # occur (see _AnomalyLedger) instead of retaining every timestamp.
    # Recorder-downtime gaps derived from session markers join the feed gaps
    # here: identical clamping/union/explanation treatment, separate report.
    all_gaps = read_gaps(cfg.raw_dir, venue) + derive_downtime_gaps(
        read_sessions(cfg.raw_dir, venue),
        lambda before_ns: last_activity_ns(cfg.raw_dir, venue, before_ns),
    )
    # Valid-book time credited between events must not include time inside a
    # gap window: a book that stayed "valid" across a reconnect or recorder
    # downtime would otherwise credit the entire hole as covered — while the
    # coverage denominator excludes it. Numerator and denominator agree on
    # what a gap is, or the percentage means nothing.
    gap_union = merge_windows((g.disconnect_ns, g.reconnect_ns) for g in all_gaps)
    gap_union_starts = [start for start, _ in gap_union]

    def credit_outside_gaps(start_ns: int, end_ns: int) -> int:
        """Length of ``[start_ns, end_ns)`` minus its overlap with gap windows."""
        if end_ns <= start_ns:
            return 0
        credited = end_ns - start_ns
        index = bisect_right(gap_union_starts, end_ns) - 1
        while index >= 0:
            win_start, win_end = gap_union[index]
            if win_end <= start_ns:
                break
            credited -= min(win_end, end_ns) - max(win_start, start_ns)
            index -= 1
        return credited

    builders: dict[str, BookBuilder] = {}
    emitters: dict[str, SnapshotEmitter] = {}
    writers: dict[str, BookDayWriter] = {}
    last_event_ns: dict[str, int] = {}
    valid_ns: dict[str, int] = defaultdict(int)
    ledgers: dict[str, dict[str, _AnomalyLedger]] = defaultdict(
        lambda: {
            "crossed": _AnomalyLedger(all_gaps),
            "seq": _AnomalyLedger(all_gaps),
            "checksum": _AnomalyLedger(all_gaps),
        }
    )
    snap_compares: dict[str, int] = defaultdict(int)
    snap_mismatches: dict[str, int] = defaultdict(int)
    # Snapshot-cadence tracking (snapshot-stream venues only). Interval lists
    # are bounded by day-length / block cadence, not by message count.
    snap_prev_ns: dict[str, int] = {}
    snap_intervals_ms: dict[str, list[float]] = defaultdict(list)
    snap_stale_windows: dict[str, list[tuple[int, int]]] = defaultdict(list)
    snap_silent_counts: dict[str, int] = defaultdict(int)

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
            writers[symbol] = BookDayWriter(cfg.processed_dir, venue, symbol, date)
        return builders[symbol]

    day_start_ns, day_end_ns = _day_bounds_ns(date)
    parse_fn = PARSE_FNS[venue]
    if vcfg.snapshot_stream:
        # Every message is a full book; the day's first snapshot arrives
        # within a block interval of midnight, so warm start buys nothing.
        warmup = WarmupResult(None, 0)
    else:
        warmup = warm_up(
            cfg.raw_dir, venue, date, vcfg.symbols, parse_fn, builder_for, tracker, seq_applies
        )
    if warmup.start_ns is not None:
        # The warmed book is the day's starting state; the events that built
        # it are the previous day's and must not be scored against this one.
        for symbol, warmed in builders.items():
            warmed.reset_counters()
            if warmed.valid:
                # Live at midnight — coverage counts from the day's first
                # instant, not from its first event.
                last_event_ns[symbol] = day_start_ns
        tracker.reset_counts()

    started = time.monotonic()
    for recv_ns, raw in iter_day_records(cfg.raw_dir, venue, date):
        msgs_total += 1
        if msgs_total % PROGRESS_EVERY_MSGS == 0:
            _log_progress(venue, date, msgs_total, recv_ns, started)
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

        # Gated on config, not on the venue name: a feed we have not declared
        # as sequence-numbered is never scored on sequence continuity, so it
        # cannot bank an unearned clean check. Venues without envelope
        # sequence numbers simply yield None here.
        seq = envelope_sequence(message) if seq_applies else None
        seq_ok = tracker.observe(seq) if seq is not None else True
        events = parse_fn(message, recv_ns)

        for event in events:
            builder = builder_for(event.symbol)
            ledger = ledgers[event.symbol]

            if vcfg.snapshot_stream and event.is_snapshot:
                prev_snap = snap_prev_ns.get(event.symbol)
                if prev_snap is not None:
                    interval_ms = (recv_ns - prev_snap) / 1e6
                    snap_intervals_ms[event.symbol].append(interval_ms)
                    if interval_ms > CADENCE_STALE_MS:
                        snap_stale_windows[event.symbol].append((prev_snap, recv_ns))
                snap_prev_ns[event.symbol] = recv_ns

            if event.is_snapshot and builder.valid:
                snap_compares[event.symbol] += 1
                prev_bid, prev_ask = builder.best_bid, builder.best_ask
                snap_bid, snap_ask = _snapshot_tob(event)
                if (prev_bid.price if prev_bid else None) != snap_bid or (
                    prev_ask.price if prev_ask else None
                ) != snap_ask:
                    snap_mismatches[event.symbol] += 1

            if event.symbol in last_event_ns and builder.valid:
                valid_ns[event.symbol] += credit_outside_gaps(last_event_ns[event.symbol], recv_ns)
            last_event_ns[event.symbol] = recv_ns

            crossed_before = builder.crossed_events
            result = builder.apply(event, seq_ok=seq_ok)
            if builder.crossed_events > crossed_before:
                ledger["crossed"].mark(recv_ns)
            if result is ApplyResult.SEQ_GAP:
                ledger["seq"].mark(recv_ns)
            elif result is ApplyResult.CHECKSUM_FAILED:
                ledger["checksum"].mark(recv_ns)

            writers[event.symbol].append(emitters[event.symbol].on_event(recv_ns, event.seq))

    span = (first_ns, last_ns) if first_ns is not None and last_ns is not None else None
    accounts = account_gaps(all_gaps, span, (day_start_ns, day_end_ns))
    # Gaps that touch the recorded span are the only trustworthy exclusions from
    # the coverage denominator, and the only ones that can explain an anomaly.
    gaps = gaps_touching_span(all_gaps, span, (day_start_ns, day_end_ns))
    gap_ns_in_day = accounts.gap_ns_excluded_from_day

    symbol_reports: list[SymbolReport] = []
    for symbol, builder in sorted(builders.items()):
        writers[symbol].close()
        written = writers[symbol].rows_written
        ledger = ledgers[symbol]
        covered = valid_ns[symbol]
        denominator_excl = max(DAY_NS - gap_ns_in_day, 1)
        best_bid, best_ask = builder.best_bid, builder.best_ask
        last_spread = (
            float(best_ask.price - best_bid.price)
            if builder.valid and best_bid is not None and best_ask is not None
            else None
        )
        snap_kwargs: dict[str, Any] = {}
        if vcfg.snapshot_stream:
            ordered = sorted(snap_intervals_ms[symbol])
            stale = snap_stale_windows[symbol]
            # A stale interval overlapping a logged gap window (feed gap or
            # recorder downtime) is explained; the rest are the venue going
            # quiet on its own.
            unexplained = [(s, e) for s, e in stale if not any(g.overlaps_ns(s, e) for g in gaps)]
            snap_silent_counts[symbol] = sum(
                1 for s, e in unexplained if (e - s) / 1e6 > CADENCE_SILENT_FAIL_MS
            )
            snap_kwargs = {
                "snap_intervals": len(ordered),
                "snap_interval_p50_ms": ordered[len(ordered) // 2] if ordered else None,
                "snap_interval_p95_ms": (
                    ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)] if ordered else None
                ),
                "snap_interval_max_ms": ordered[-1] if ordered else None,
                "snap_stale": len(stale),
                "snap_stale_unexplained": len(unexplained),
            }
        symbol_reports.append(
            SymbolReport(
                seq_gaps=builder.seq_gaps if seq_applies else None,
                seq_gaps_unexplained=(ledger["seq"].unexplained(gaps) if seq_applies else None),
                checksum_failures=builder.checksum_failures if checksum_applies else None,
                checksum_failures_unexplained=(
                    ledger["checksum"].unexplained(gaps) if checksum_applies else None
                ),
                checksums_verified=builder.checksums_verified if checksum_applies else None,
                last_mid=float(builder.mid) if builder.valid and builder.mid is not None else None,
                last_spread=last_spread,
                last_bid_levels=len(builder.bid_levels(vcfg.book_depth)) if builder.valid else 0,
                last_ask_levels=len(builder.ask_levels(vcfg.book_depth)) if builder.valid else 0,
                symbol=symbol,
                events_applied=builder.events_applied,
                snapshots=builder.snapshots_applied,
                crossed_total=builder.crossed_events,
                crossed_unexplained=ledger["crossed"].unexplained(gaps),
                locked_total=builder.locked_events,
                valid_coverage_day_pct=round(100 * covered / DAY_NS, 3),
                valid_coverage_excl_gaps_pct=round(100 * covered / denominator_excl, 3),
                snapshot_compares=snap_compares[symbol],
                snapshot_mismatches=snap_mismatches[symbol],
                rows_written=written,
                **snap_kwargs,
            )
        )

    integrity = IntegrityReport(
        mechanism=describe(mechanisms),
        sequence_checks=tracker.observations if seq_applies else None,
        checksum_checks=(
            sum(b.checksums_verified for b in builders.values()) if checksum_applies else None
        ),
        snapshot_checks=(
            sum(b.snapshots_applied for b in builders.values()) if vcfg.snapshot_stream else None
        ),
    )

    failure_reasons: list[str] = []
    if not symbol_reports:
        failure_reasons.append("no book data found for this venue-day")
    # The crossed/locked criterion is only as good as the mechanism that keeps
    # the book honest between snapshots. Refuse to certify a venue-day whose
    # declared mechanism never ran; "zero crossed books" from an unchecked
    # reconstruction is not evidence of anything.
    uncertified = uncertified_reason(venue, mechanisms, integrity) if symbol_reports else None
    if uncertified is not None:
        failure_reasons.append(uncertified)
    for report in symbol_reports:
        prefix = f"{report.symbol}: "
        if report.crossed_unexplained:
            failure_reasons.append(
                f"{prefix}{report.crossed_unexplained} unexplained crossed books "
                f"(integrity mechanism: {integrity.mechanism})"
            )
        if report.seq_gaps_unexplained:
            failure_reasons.append(f"{prefix}{report.seq_gaps_unexplained} unexplained seq gaps")
        if report.checksum_failures_unexplained:
            failure_reasons.append(
                f"{prefix}{report.checksum_failures_unexplained} unexplained checksum failures"
            )
        # Per-symbol counterpart to the venue-level check: on Kraken a symbol
        # missing its instruments precisions builds no checksum function, so it
        # replays entirely unverified while its siblings verify normally.
        if report.checksums_verified == 0 and report.events_applied > 0:
            failure_reasons.append(
                f"{prefix}0 of {report.events_applied} updates verified against "
                f"{CHECKSUM} — no instrument precisions configured for this symbol, "
                "so zero checksum failures is not evidence of integrity"
            )
        if report.valid_coverage_excl_gaps_pct < FULL_DAY_THRESHOLD * 100:
            failure_reasons.append(
                f"{prefix}coverage outside gaps {report.valid_coverage_excl_gaps_pct:.2f}% "
                f"< {FULL_DAY_THRESHOLD:.1%}"
            )
        if snap_silent_counts.get(report.symbol):
            failure_reasons.append(
                f"{prefix}{snap_silent_counts[report.symbol]} unexplained snapshot silence(s) "
                f"longer than {CADENCE_SILENT_FAIL_MS / 1000:.0f}s — a snapshot stream this "
                "quiet outside logged gaps is missing data, not a quiet market"
            )

    return DayReport(
        venue=venue,
        date=date,
        msgs_total=msgs_total,
        channel_counts=dict(channel_counts),
        first_ns=first_ns,
        last_ns=last_ns,
        warmup_start_ns=warmup.start_ns,
        snapshot_stream=vcfg.snapshot_stream,
        feed_gaps=accounts.feed_gaps_in_span,
        feed_gap_ms=accounts.feed_gap_ms_in_span,
        downtime_gaps=accounts.downtime_gaps_in_span,
        downtime_gap_ms=accounts.downtime_gap_ms_in_span,
        unclean_gaps=accounts.unclean_gaps_in_span,
        unclean_gap_ms=accounts.unclean_gap_ms_in_span,
        gap_ms_excluded=accounts.gap_ms_in_span,
        gaps_partially_outside_span=accounts.gaps_partially_outside_span,
        gap_ms_clipped_outside_span=accounts.gap_ms_clipped_outside_span,
        gaps_outside_span=accounts.gaps_outside_span,
        gap_ms_outside_span=accounts.gap_ms_outside_span,
        arrival=hist.snapshot(),
        integrity=integrity,
        symbols=symbol_reports,
        passed=not failure_reasons,
        failure_reasons=failure_reasons,
    )
