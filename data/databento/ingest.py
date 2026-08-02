"""Ingest a stored DBN file into canonical Parquet, with an integrity report.

The ``databento`` client is imported lazily so the adapter and its tests
never require it; only actual DBN decoding does. Ingest is idempotent
(deterministic part names, same as every processed dataset) and streams
through the same bounded writers as the recorder path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data.config import AppConfig
from data.databento.adapter import VENUE, SequenceAudit, map_mbp10, map_trade
from data.store import BookDayWriter, TradesDayWriter

VENDOR_SUBDIR = Path("vendor") / "databento"
DATASET = "GLBX.MDP3"


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


API_KEY_ENV = "MLCE_DATABENTO_API_KEY"
_LEGACY_API_KEY_ENV = "DATABENTO_API_KEY"


def require_api_key() -> str:
    """The Databento key comes only from the environment, never from source.

    Primary name follows this project's ``MLCE_`` env convention; the bare
    vendor name is accepted as a fallback. ``.env`` is gitignored and read by
    the operator's shell — nothing here writes or logs the value.
    """
    key = os.environ.get(API_KEY_ENV) or os.environ.get(_LEGACY_API_KEY_ENV) or ""
    if not key:
        raise RuntimeError(
            f"{API_KEY_ENV} is not set. Sign up at databento.com (free signup "
            "credit covers adapter validation), put the key in .env (gitignored) "
            "or export it, and re-run. Keys never enter the repo."
        )
    return key


def vendor_path(cfg: AppConfig, date: str, symbol: str, schema: str) -> Path:
    """Immutable vendor location for one contract-day-schema DBN file."""
    safe = symbol.replace(".", "_")
    return vendor_dir(cfg) / "GLBX.MDP3" / f"date={date}" / f"{safe}.{schema}.dbn.zst"


def estimate_cost(date: str, symbol: str, schema: str) -> tuple[float, int]:
    """(USD cost estimate, billable bytes) for one request — costs nothing.

    Always call before :func:`fetch_day`: the estimate is what makes a spend
    decision reviewable, and comparing it against the delivered file is what
    catches a request that ballooned.
    """
    import databento  # lazy

    client = databento.Historical(require_api_key())
    end = _next_day(date)
    cost = client.metadata.get_cost(
        dataset=DATASET,
        symbols=[symbol],
        stype_in="continuous",
        schema=schema,
        start=date,
        end=end,
    )
    billable = client.metadata.get_billable_size(
        dataset=DATASET,
        symbols=[symbol],
        stype_in="continuous",
        schema=schema,
        start=date,
        end=end,
    )
    return float(cost), int(billable)


def fetch_day(cfg: AppConfig, date: str, symbol: str, schema: str) -> Path:
    """Fetch one contract-day-schema of GLBX.MDP3 into the immutable vendor tree.

    One file per (symbol, schema) so cost and event-rate accounting stay
    per-contract. Continuous front-month symbology (``.c.0``). Refuses to
    overwrite: vendor raw is immutable and re-downloading costs money.
    """
    import databento  # lazy

    target = vendor_path(cfg, date, symbol, schema)
    if target.exists():
        raise FileExistsError(f"{target} already exists — vendor raw is immutable")
    target.parent.mkdir(parents=True, exist_ok=True)
    client = databento.Historical(require_api_key())
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[symbol],
        stype_in="continuous",
        schema=schema,
        start=date,
        end=_next_day(date),
    )
    data.to_file(target)
    return target


def _next_day(date: str) -> str:
    from datetime import UTC, datetime, timedelta

    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    return (day + timedelta(days=1)).strftime("%Y-%m-%d")
