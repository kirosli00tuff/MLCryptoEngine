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

from dataclasses import dataclass, field

from data.config import AppConfig
from data.databento.adapter import NULL_PRICE
from data.databento.ingest import record_to_dict, vendor_path
from data.databento.session import closed_windows_ns, open_ns

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000
# A quiet stretch longer than this outside a scheduled halt is reported as a
# coverage anomaly worth a human look, not silently absorbed.
QUIET_ANOMALY_MS = 60_000


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
    locked: int = 0
    covered_open_ns: int = 0
    # Scheduled-open time lost to unexplained silences, excluded from
    # coverage so the metric cannot flatter a feed with holes in it.
    quiet_open_ns: int = 0
    scheduled_open_ns: int = 0
    quiet_windows: list[tuple[int, int]] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.scheduled_open_ns <= 0:
            return 0.0
        return 100.0 * self.covered_open_ns / self.scheduled_open_ns

    @property
    def passed(self) -> bool:
        return not self.failure_reasons


def _overlap_ns(lo: int, hi: int, windows: list[tuple[int, int]]) -> int:
    return sum(
        max(0, min(hi, w_end) - max(lo, w_start)) for w_start, w_end in windows if w_end > w_start
    )


def validate_vendor_day(
    cfg: AppConfig, symbol: str, date: str, schema: str = "mbp-10"
) -> VendorDayReport:
    """Stream one DBN file and score it. Bounded memory, single pass."""
    import databento  # lazy

    path = vendor_path(cfg, date, symbol, schema)
    if not path.is_file():
        raise FileNotFoundError(f"no vendor file at {path}")

    report = VendorDayReport(venue="cme", symbol=symbol, date=date, schema=schema)
    closed = closed_windows_ns(date)
    report.scheduled_open_ns = open_ns(date)

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
    if report.crossed:
        report.failure_reasons.append(f"{report.crossed} crossed book events")
    if report.coverage_pct < 99.0:
        report.failure_reasons.append(
            f"coverage {report.coverage_pct:.2f}% of scheduled-open time < 99%"
        )
    return report
