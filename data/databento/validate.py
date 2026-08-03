"""Score one vendor (Databento) contract-day the way Phase A scores a venue-day.

Same discipline as :mod:`data.validate.replay`, adapted to what a vendor feed
actually provides:

- **Ordering clock.** ``ts_recv`` — Databento's capture-server hardware
  timestamp — orders every event, because it is the one clock stamped by a
  single machine and monotone with respect to arrival. ``ts_event`` is the
  CME matching-engine clock and is kept for reference only; it can move
  backwards across instruments. Neither is this project's recorder clock,
  and rows carrying them are never ordered against recorder rows (ADR-011).
- **Integrity.** MDP3 carries per-instrument sequence numbers, so continuity
  is verified and counted. There is no book checksum and no snapshot stream,
  so those two checks report ``None``/"n/a" rather than zero — the Stage 1.6
  rule: a check that never ran must never read as a clean pass.
- **Coverage.** Measured against scheduled-open time only. The daily
  maintenance halt and the weekend close are expected absence, not gaps.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from data.config import AppConfig
from data.databento.adapter import NULL_PRICE
from data.databento.ingest import record_to_dict, vendor_path
from data.databento.rolls import RollBoundary, roll_windows_ns
from data.databento.session import closed_windows_ns, no_match_windows_ns, open_ns
from data.recorder.gaps import merge_windows
from research.labels.fixed_horizon import DEFAULT_HORIZONS_MS, MAX_HORIZON_MS

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000
# A quiet stretch longer than this outside a scheduled halt is reported as a
# coverage anomaly worth a human look, not silently absorbed.
QUIET_ANOMALY_MS = 60_000
# Roll exclusion width, derived from configuration rather than fixed: the
# feature lookback backward and the longest label horizon forward, so
# extending the horizon set widens the exclusion automatically.
FEATURE_LOOKBACK_NS = 60 * NS_PER_S
MAX_LABEL_HORIZON_NS = MAX_HORIZON_MS * NS_PER_MS


class IntervalStats:
    """Bounded inter-event interval statistics.

    Measurability of a label horizon depends on how often a fresh
    observation exists inside that window, so the counters are keyed on the
    label horizons themselves. Percentiles come from a log-spaced histogram
    rather than a retained list — a 15-million-element float list is exactly
    the unbounded pattern that OOM-killed Phase A validation.
    """

    BOUNDS_MS: tuple[float, ...] = (
        0.01,
        0.05,
        0.1,
        0.5,
        1.0,
        5.0,
        10.0,
        50.0,
        100.0,
        500.0,
        1_000.0,
        5_000.0,
        30_000.0,
        300_000.0,
    )

    def __init__(self, horizons_ms: tuple[int, ...] = DEFAULT_HORIZONS_MS) -> None:
        self.horizons_ms = horizons_ms
        self.count = 0
        self.max_ms = 0.0
        self._buckets = [0] * (len(self.BOUNDS_MS) + 1)
        self.below_horizon: dict[int, int] = dict.fromkeys(horizons_ms, 0)

    def add(self, delta_ms: float) -> None:
        self.count += 1
        if delta_ms > self.max_ms:
            self.max_ms = delta_ms
        self._buckets[bisect_left(self.BOUNDS_MS, delta_ms)] += 1
        for horizon in self.horizons_ms:
            if delta_ms < horizon:
                self.below_horizon[horizon] += 1

    def percentile_ms(self, fraction: float) -> float:
        """Upper bound of the bucket containing the requested percentile."""
        if self.count == 0:
            return float("nan")
        target = fraction * self.count
        cumulative = 0
        for index, n in enumerate(self._buckets):
            cumulative += n
            if cumulative >= target:
                return self.BOUNDS_MS[index] if index < len(self.BOUNDS_MS) else self.max_ms
        return self.max_ms

    def share_below(self, horizon_ms: int) -> float:
        if self.count == 0:
            return float("nan")
        return self.below_horizon.get(horizon_ms, 0) / self.count


@dataclass
class VendorDayReport:
    """Scorecard for one contract-day of vendor data."""

    venue: str
    symbol: str
    date: str
    schema: str
    events: int = 0
    first_ns: int | None = None
    last_ns: int | None = None
    ordering_clock: str = "ts_recv (Databento capture-server hardware clock)"
    reference_clock: str = "ts_event (CME MDP3 matching-engine clock)"
    # Integrity: counted where the feed provides the mechanism, None where it
    # does not. None renders "n/a" and never 0 (Stage 1.6).
    sequence_checks: int | None = None
    sequence_regressions: int | None = None
    checksum_checks: int | None = None
    snapshot_checks: int | None = None
    out_of_order_recv: int = 0
    exchange_clock_regressions: int = 0
    crossed: int = 0
    # Crossings inside a scheduled no-match window (maintenance halt plus the
    # reopen auction) are EXPECTED: order entry continues while matching is
    # suspended, so bid can legitimately exceed ask. Counted and reported,
    # excluded from the failure criterion — never suppressed. Outside those
    # windows a crossed book is a real defect and still fails.
    crossed_explained: int = 0
    locked: int = 0
    covered_open_ns: int = 0
    # Scheduled-open time lost to unexplained silences, excluded from
    # coverage so the metric cannot flatter a feed with holes in it.
    quiet_open_ns: int = 0
    scheduled_open_ns: int = 0
    quiet_windows: list[tuple[int, int]] = field(default_factory=list)
    # Roll exclusions reported separately, never absorbed into coverage: an
    # unexpectedly large exclusion must be visible as its own number.
    roll_windows: int = 0
    roll_excluded_open_ns: int = 0
    failure_reasons: list[str] = field(default_factory=list)
    # Inter-event interval statistics, accumulated in the same single pass:
    # a log-spaced histogram plus one counter per label horizon, never a
    # 15-million-element list.
    intervals: IntervalStats = field(default_factory=IntervalStats)

    @property
    def coverage_pct(self) -> float:
        if self.scheduled_open_ns <= 0:
            return 0.0
        return 100.0 * self.covered_open_ns / self.scheduled_open_ns

    @property
    def passed(self) -> bool:
        return not self.failure_reasons


def _date_to_ns(date: str) -> int:
    from datetime import UTC, datetime

    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()) * NS_PER_S


def _overlap_ns(lo: int, hi: int, windows: list[tuple[int, int]]) -> int:
    return sum(
        max(0, min(hi, w_end) - max(lo, w_start)) for w_start, w_end in windows if w_end > w_start
    )


def validate_vendor_day(
    cfg: AppConfig,
    symbol: str,
    date: str,
    schema: str = "mbp-10",
    rolls: list[RollBoundary] | None = None,
) -> VendorDayReport:
    """Stream one DBN file and score it. Bounded memory, single pass."""
    import databento  # lazy

    path = vendor_path(cfg, date, symbol, schema)
    if not path.is_file():
        raise FileNotFoundError(f"no vendor file at {path}")

    report = VendorDayReport(venue="cme", symbol=symbol, date=date, schema=schema)
    closed = closed_windows_ns(date)
    no_match = no_match_windows_ns(date)
    report.scheduled_open_ns = open_ns(date)

    # Roll exclusion joins the existing invalidity path rather than forming a
    # parallel one. Windows are unioned with the scheduled closures before any
    # time is summed (CLAUDE.md interval rule) so an exclusion overlapping a
    # halt is not counted twice.
    roll_ex = roll_windows_ns(rolls or [], FEATURE_LOOKBACK_NS, MAX_LABEL_HORIZON_NS)
    day_start = _date_to_ns(date)
    day_end = day_start + 86_400 * NS_PER_S
    roll_in_day = [
        (max(lo, day_start), min(hi, day_end))
        for lo, hi in roll_ex
        if min(hi, day_end) > max(lo, day_start)
    ]
    report.roll_windows = len(roll_in_day)
    open_and_rolled = merge_windows(roll_in_day)
    report.roll_excluded_open_ns = sum(
        (hi - lo) - _overlap_ns(lo, hi, closed) for lo, hi in open_and_rolled
    )

    store = databento.DBNStore.from_file(path)
    prev_recv: int | None = None
    prev_event: int | None = None
    last_seq: int | None = None
    seq_seen = 0
    seq_regressions = 0

    for rec in store:
        raw = record_to_dict(rec)
        recv = int(raw["ts_recv"])
        event_ts = int(raw["ts_event"])
        report.events += 1
        if report.first_ns is None:
            report.first_ns = recv
        report.last_ns = recv

        if prev_recv is not None:
            if recv < prev_recv:
                report.out_of_order_recv += 1
            else:
                report.intervals.add((recv - prev_recv) / NS_PER_MS)
                # Time between consecutive events counts toward coverage only
                # for the portion when the exchange was scheduled open.
                span = recv - prev_recv
                closed_part = _overlap_ns(prev_recv, recv, closed)
                open_part = span - closed_part
                if span > QUIET_ANOMALY_MS * NS_PER_MS and closed_part < span:
                    # An unexplained silence is NOT covered time. Counting the
                    # whole first-to-last span minus closures would report
                    # 100% while sitting on a multi-hour hole — coverage has
                    # to mean "fresh data existed", not "the file spans it".
                    report.quiet_windows.append((prev_recv, recv))
                    report.quiet_open_ns += open_part
                else:
                    report.covered_open_ns += open_part
        if prev_event is not None and event_ts < prev_event:
            report.exchange_clock_regressions += 1

        seq = raw.get("sequence")
        if seq is not None:
            seq_seen += 1
            seq_int = int(seq)
            if last_seq is not None and seq_int < last_seq:
                seq_regressions += 1
            last_seq = seq_int

        levels = raw.get("levels") or []
        if levels:
            bid = levels[0].get("bid_px", NULL_PRICE)
            ask = levels[0].get("ask_px", NULL_PRICE)
            if bid != NULL_PRICE and ask != NULL_PRICE:
                if bid > ask:
                    report.crossed += 1
                    if any(lo <= recv < hi for lo, hi in no_match):
                        report.crossed_explained += 1
                elif bid == ask:
                    report.locked += 1

        prev_recv, prev_event = recv, event_ts

    report.sequence_checks = seq_seen or None
    report.sequence_regressions = seq_regressions if seq_seen else None
    # Not provided by this feed — stated, never defaulted to a passing zero.
    report.checksum_checks = None
    report.snapshot_checks = None

    if report.events == 0:
        report.failure_reasons.append("no events in file")
    if report.out_of_order_recv:
        report.failure_reasons.append(
            f"{report.out_of_order_recv} events arrived out of order on the ordering "
            "clock (ts_recv) — the capture clock must be monotone"
        )
    if report.sequence_checks == 0:
        report.failure_reasons.append(
            "declares MDP3 sequence numbers but none were observed — zero "
            "regressions out of zero observations is not evidence of integrity"
        )
    unexplained_crossed = report.crossed - report.crossed_explained
    if unexplained_crossed:
        report.failure_reasons.append(
            f"{unexplained_crossed} crossed book events outside any scheduled "
            f"no-match window ({report.crossed_explained} of {report.crossed} "
            "occurred during a halt or reopen auction and are explained)"
        )
    if report.coverage_pct < 99.0:
        report.failure_reasons.append(
            f"coverage {report.coverage_pct:.2f}% of scheduled-open time < 99%"
        )
    return report
