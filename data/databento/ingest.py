"""Ingest a stored DBN file into canonical Parquet, with an integrity report.

The ``databento`` client is imported lazily so the adapter and its tests
never require it; only actual DBN decoding does. Ingest is idempotent
(deterministic part names, same as every processed dataset) and streams
through the same bounded writers as the recorder path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from data.config import AppConfig
from data.databento.adapter import VENUE, SequenceAudit, map_mbp10, map_trade
from data.databento.budget import check_affordable, commit
from data.store import BookDayWriter, TradesDayWriter

VENDOR_SUBDIR = Path("vendor") / "databento"
DATASET = "GLBX.MDP3"
# Continuous front-month symbology: see progress.md Stage C.3 symbology
# discovery. Resolved from the vendor's own symbology API, not assumed.
STYPE_CONTINUOUS = "continuous"


@dataclass
class IngestReport:
    """What the adapter verified, and what is not applicable — stated, not implied."""

    dataset: str
    date: str
    book_rows: dict[str, int] = field(default_factory=dict)
    trade_rows: dict[str, int] = field(default_factory=dict)
    sequence_observations: dict[str, int] = field(default_factory=dict)
    sequence_gaps: dict[str, int] = field(default_factory=dict)
    # Fixed statements of mechanism applicability for report.md.
    verified: str = "per-instrument sequence monotonic continuity; crossed/locked detection"
    not_applicable: str = (
        "book checksums (none in MDP3 MBP-10); snapshot cadence (incremental feed)"
    )
    clocks: str = (
        "ts_ns = Databento capture-server hardware receive clock; "
        "exchange_ns = CME MDP3 exchange clock; neither is the recorder clock "
        "and neither may be ordered against it"
    )


def vendor_dir(cfg: AppConfig) -> Path:
    return cfg.data_root / VENDOR_SUBDIR


def store_dbn(cfg: AppConfig, source_path: Path, dataset: str, date: str) -> Path:
    """Copy a fetched DBN file into the immutable vendor tree; refuses overwrite."""
    target = vendor_dir(cfg) / dataset / f"date={date}" / source_path.name
    if target.exists():
        raise FileExistsError(f"{target} already exists — vendor raw is immutable")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source_path.read_bytes())
    return target


def record_to_dict(record: Any) -> dict[str, Any]:
    """Flatten a databento record object into the adapter's plain-dict shape."""
    out: dict[str, Any] = {
        "ts_event": record.ts_event,
        "ts_recv": getattr(record, "ts_recv", record.ts_event),
        "sequence": getattr(record, "sequence", None),
    }
    levels = getattr(record, "levels", None)
    if levels is not None:
        out["levels"] = [
            {
                "bid_px": lvl.bid_px,
                "ask_px": lvl.ask_px,
                "bid_sz": lvl.bid_sz,
                "ask_sz": lvl.ask_sz,
            }
            for lvl in levels
        ]
    for name in ("price", "size", "side", "action"):
        if hasattr(record, name):
            out[name] = getattr(record, name)
    return out


def ingest_dbn(
    cfg: AppConfig,
    dbn_path: Path,
    date: str,
    schema: str,
    symbol_by_instrument_id: dict[int, str] | None = None,
) -> IngestReport:
    """Map one DBN file (``mbp-10`` or ``trades`` schema) into canonical Parquet.

    ``symbol_by_instrument_id`` comes from Databento symbology metadata; an
    unmapped instrument falls back to its numeric id as the symbol string —
    visible, never silently dropped.
    """
    if schema not in ("mbp-10", "trades"):
        raise ValueError(f"unsupported schema '{schema}' — this adapter maps mbp-10 and trades")
    import databento  # lazy: only real DBN decoding needs the client

    store = databento.DBNStore.from_file(dbn_path)
    symbols = symbol_by_instrument_id or {}
    report = IngestReport(dataset="GLBX.MDP3", date=date)
    audit = SequenceAudit()
    book_writers: dict[str, BookDayWriter] = {}
    trade_writers: dict[str, TradesDayWriter] = {}
    for record in store:
        raw = record_to_dict(record)
        instrument_id = getattr(record, "instrument_id", None)
        symbol = (
            symbols.get(int(instrument_id), str(instrument_id))
            if instrument_id is not None
            else "?"
        )
        if raw.get("sequence") is not None:
            audit.observe(symbol, int(raw["sequence"]))
        if schema == "mbp-10":
            if symbol not in book_writers:
                book_writers[symbol] = BookDayWriter(cfg.processed_dir, VENUE, symbol, date)
            book_writers[symbol].append([map_mbp10(raw, symbol)])
        else:
            if symbol not in trade_writers:
                trade_writers[symbol] = TradesDayWriter(cfg.processed_dir, VENUE, symbol, date)
            trade_writers[symbol].append([map_trade(raw, symbol)])
    for symbol, book_writer in book_writers.items():
        book_writer.close()
        report.book_rows[symbol] = book_writer.rows_written
    for symbol, trade_writer in trade_writers.items():
        trade_writer.close()
        report.trade_rows[symbol] = trade_writer.rows_written
    report.sequence_observations = dict(audit.observations)
    report.sequence_gaps = dict(audit.gaps)
    return report


# The key is loaded through the pydantic-settings config layer
# (AppConfig.require_databento_key), never read from os.environ here: one
# path for credentials means one place that fails clearly when it is missing.


def vendor_path(cfg: AppConfig, date: str, symbol: str, schema: str) -> Path:
    """Immutable vendor location for one contract-day-schema DBN file."""
    safe = symbol.replace(".", "_")
    return vendor_dir(cfg) / "GLBX.MDP3" / f"date={date}" / f"{safe}.{schema}.dbn.zst"


def estimate_cost(cfg: AppConfig, date: str, symbol: str, schema: str) -> tuple[float, int]:
    """(USD cost estimate, billable bytes) for one request — costs nothing.

    Verified against the databento-python client actually installed here:
    ``metadata.get_cost`` and ``metadata.get_billable_size`` both exist and
    take the same request parameters as ``timeseries.get_range``. Always
    called before :func:`fetch_day`; the estimate is what makes a spend
    decision reviewable, and comparing it against the delivered file is what
    catches a request that ballooned.
    """
    import databento  # lazy

    client = databento.Historical(cfg.require_databento_key())
    end = _next_day(date)
    cost = client.metadata.get_cost(
        dataset=DATASET,
        symbols=[symbol],
        stype_in=STYPE_CONTINUOUS,
        schema=schema,
        start=date,
        end=end,
    )
    billable = client.metadata.get_billable_size(
        dataset=DATASET,
        symbols=[symbol],
        stype_in=STYPE_CONTINUOUS,
        schema=schema,
        start=date,
        end=end,
    )
    return float(cost), int(billable)


def _download_to_file(
    client: Any, target: Path, *, symbol: str, schema: str, start: str, end: str
) -> None:
    """Stream one vendor response straight to ``target``.

    ``timeseries.get_range`` without ``path`` builds the entire response in
    memory and only then writes it. That is survivable for a day and fatal
    for a month: Stage C.7's June MBP-10 fetch (76.3 GB billable) grew to
    9.1 GB resident and was OOM-killed on a 14 GiB machine, after its cost
    had already been committed to the ledger. Passing ``path`` streams the
    body to disk, so peak memory is a chunk rather than the whole month.

    The bytes land on a ``.partial`` sibling and are renamed only once the
    vendor call has returned. A process killed mid-download therefore leaves
    an obviously-incomplete ``.partial``, never a truncated file at the real
    path that a later run would take for a finished download.
    """
    partial = target.parent / (target.name + ".partial")
    partial.unlink(missing_ok=True)
    try:
        client.timeseries.get_range(
            dataset=DATASET,
            symbols=[symbol],
            stype_in=STYPE_CONTINUOUS,
            schema=schema,
            start=start,
            end=end,
            path=partial,
        )
    except BaseException:
        # The charge is already committed; leaving a half-file behind would
        # only make the next run harder to reason about.
        partial.unlink(missing_ok=True)
        raise
    partial.replace(target)


def fetch_day(cfg: AppConfig, date: str, symbol: str, schema: str) -> Path:
    """Price, gate, commit, then fetch one contract-day-schema of GLBX.MDP3.

    The only sanctioned download path. Every request is priced first, checked
    against the cumulative on-disk budget, and committed to the ledger
    *before* the bytes are requested — so a crash mid-download can never
    leave money spent that the ledger does not know about. Refuses to
    overwrite: vendor raw is immutable and re-downloading costs money again.
    """
    import databento  # lazy

    target = vendor_path(cfg, date, symbol, schema)
    if target.exists():
        raise FileExistsError(f"{target} already exists — vendor raw is immutable")

    estimate, billable = estimate_cost(cfg, date, symbol, schema)
    headroom = check_affordable(cfg, estimate)
    commit(
        cfg,
        dataset=DATASET,
        symbol=symbol,
        schema=schema,
        date=date,
        usd=estimate,
        billable_bytes=billable,
    )
    print(
        f"  priced {symbol} {schema} {date}: ${estimate:.4f} "
        f"({billable:,} billable bytes) · ${headroom:.4f} budget left after",
        flush=True,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    client = databento.Historical(cfg.require_databento_key())
    _download_to_file(
        client,
        target,
        symbol=symbol,
        schema=schema,
        start=date,
        end=_next_day(date),
    )
    return target


def ingest_dbn_range(
    cfg: AppConfig,
    dbn_path: Path,
    schema: str,
    symbol_by_instrument_id: dict[int, str] | None = None,
    contract_symbol: str | None = None,
    progress_every: int = 5_000_000,
) -> dict[str, IngestReport]:
    """Map one multi-day DBN file into per-UTC-day canonical Parquet.

    :func:`ingest_dbn` writes every record into a single date partition,
    which is right for a day file and silently wrong for a month: it would
    label 30 days of events as one. This routes each record to the partition
    of its own ``ts_recv`` date instead.

    Records arrive in capture-clock order, so at most one day is open at a
    time and the writer for a finished day is closed as soon as the date
    advances — memory stays flat across a 44 GB month. A record arriving for
    an already-finalised day would mean the stream was not ordered and the
    partition just closed is short, so that raises rather than reopening and
    overwriting.

    ``contract_symbol`` overrides the per-record symbol so a continuous
    series lands under one stable name (``MBT``) rather than splitting into
    a partition per underlying instrument at each roll — the roll is handled
    as an exclusion window, not as a change of instrument identity.
    """
    if schema not in ("mbp-10", "trades"):
        raise ValueError(f"unsupported schema '{schema}' — this adapter maps mbp-10 and trades")
    import databento  # lazy

    store = databento.DBNStore.from_file(dbn_path)
    symbols = symbol_by_instrument_id or {}
    reports: dict[str, IngestReport] = {}
    audit = SequenceAudit()
    finalised: set[str] = set()
    open_date: str | None = None
    book_writers: dict[str, BookDayWriter] = {}
    trade_writers: dict[str, TradesDayWriter] = {}
    started = time.monotonic()

    def close_open_day() -> None:
        nonlocal book_writers, trade_writers
        if open_date is None:
            return
        report = reports[open_date]
        for sym, writer in book_writers.items():
            writer.close()
            report.book_rows[sym] = writer.rows_written
        for sym, twriter in trade_writers.items():
            twriter.close()
            report.trade_rows[sym] = twriter.rows_written
        report.sequence_observations = dict(audit.observations)
        report.sequence_gaps = dict(audit.gaps)
        book_writers = {}
        trade_writers = {}
        finalised.add(open_date)

    for seen, record in enumerate(store, start=1):
        raw = record_to_dict(record)
        ts_recv = int(raw["ts_recv"])
        date = datetime.fromtimestamp(ts_recv / 1e9, tz=UTC).strftime("%Y-%m-%d")
        if date != open_date:
            if date in finalised:
                raise ValueError(
                    f"{dbn_path.name}: record for already-finalised day {date} after "
                    f"{open_date} — the stream is not capture-clock ordered, so that "
                    "partition was closed short. Ingest cannot proceed safely."
                )
            close_open_day()
            open_date = date
            reports[date] = IngestReport(dataset=DATASET, date=date)
            audit = SequenceAudit()

        symbol = contract_symbol
        if symbol is None:
            instrument_id = getattr(record, "instrument_id", None)
            symbol = (
                symbols.get(int(instrument_id), str(instrument_id))
                if instrument_id is not None
                else "?"
            )
        if raw.get("sequence") is not None:
            audit.observe(symbol, int(raw["sequence"]))
        if schema == "mbp-10":
            if symbol not in book_writers:
                book_writers[symbol] = BookDayWriter(cfg.processed_dir, VENUE, symbol, date)
            book_writers[symbol].append([map_mbp10(raw, symbol)])
        else:
            if symbol not in trade_writers:
                trade_writers[symbol] = TradesDayWriter(cfg.processed_dir, VENUE, symbol, date)
            trade_writers[symbol].append([map_trade(raw, symbol)])

        if seen % progress_every == 0:
            rate = seen / max(time.monotonic() - started, 1e-9)
            print(f"  ingest {dbn_path.name}: {seen:,} records · {rate:,.0f}/s", flush=True)

    close_open_day()
    return reports


def _next_day(date: str) -> str:
    from datetime import UTC, datetime, timedelta

    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    return (day + timedelta(days=1)).strftime("%Y-%m-%d")


def range_path(cfg: AppConfig, start: str, end: str, symbol: str, schema: str) -> Path:
    """Immutable vendor location for one contract-range-schema DBN file."""
    safe = symbol.replace(".", "_")
    return vendor_dir(cfg) / DATASET / f"range={start}_{end}" / f"{safe}.{schema}.dbn.zst"


def fetch_range(cfg: AppConfig, start: str, end: str, symbol: str, schema: str) -> Path:
    """Price, gate, commit, then fetch ``[start, end)`` for one contract-schema.

    Same contract as :func:`fetch_day` — priced first, checked against the
    cumulative on-disk budget, committed before the bytes are requested, and
    refusing to overwrite. Buying a month per request rather than a day means
    a failure costs one month, not the whole range.
    """
    import databento  # lazy

    target = range_path(cfg, start, end, symbol, schema)
    if target.exists():
        raise FileExistsError(f"{target} already exists — vendor raw is immutable")

    client = databento.Historical(cfg.require_databento_key())
    estimate = float(
        client.metadata.get_cost(
            dataset=DATASET,
            symbols=[symbol],
            stype_in=STYPE_CONTINUOUS,
            schema=schema,
            start=start,
            end=end,
        )
    )
    billable = int(
        client.metadata.get_billable_size(
            dataset=DATASET,
            symbols=[symbol],
            stype_in=STYPE_CONTINUOUS,
            schema=schema,
            start=start,
            end=end,
        )
    )
    headroom = check_affordable(cfg, estimate)
    commit(
        cfg,
        dataset=DATASET,
        symbol=symbol,
        schema=schema,
        date=f"{start}..{end}",
        usd=estimate,
        billable_bytes=billable,
        note="C.7 four-month MBT backfill",
    )
    print(
        f"  priced {symbol} {schema} {start}..{end}: ${estimate:.4f} "
        f"({billable:,} B) · ${headroom:.4f} left after",
        flush=True,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    _download_to_file(client, target, symbol=symbol, schema=schema, start=start, end=end)
    return target
