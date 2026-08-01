"""Phase B pipeline: validated Parquet → samples → purged-CV evaluation.

Extraction is a single streaming pass per venue/symbol/day: the merged event
stream drives the feature engine, the sampler decides sample times, and the
labelers resolve forward returns as the stream advances. A sample's row is
buffered only until its slowest label resolves (bounded by the longest
horizon), then written in timestamp order — nothing day-sized is ever held.

Point-in-time discipline (the leakage tests pin this):
- features for a sample at ``t`` are computed before the event at ``t`` is
  applied, so they see only ``local_ns < t``;
- labels read only mids after ``t`` (entry mid is the last mid strictly
  before ``t``);
- samples whose lookback or label horizon touches a gap window (feed gap or
  recorder downtime) or an invalid book are marked invalid and excluded from
  training, never interpolated.
"""

from __future__ import annotations

import heapq
import time
from bisect import bisect_right
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from numpy.typing import NDArray

from data.config import AppConfig
from data.store import StreamingPartWriter, sanitize_symbol
from data.store.parquet_writer import PART_NAME
from research.features.cross_venue import CrossVenueTracker
from research.features.engine import FEATURE_COLUMNS, FeatureEngine
from research.labels.costs import CostModel, cost_model_from_config, net_label
from research.labels.fixed_horizon import DEFAULT_HORIZONS_MS, FixedHorizonLabeler
from research.labels.triple_barrier import TripleBarrierLabeler
from research.models.baselines import LastSignBaseline, ZeroBaseline
from research.models.evaluate import auc, calibration_bins, expected_value_bps, hit_rate
from research.models.evaluate import feature_importances as importances_of
from research.models.lgbm import make_classifier, make_regressor
from research.sampling.bars import EventBars, Sampler
from research.stream.events import StreamEvent
from research.stream.reader import gap_windows, iter_book_events, merged_stream
from research.validation.purged_kfold import PurgedKFold

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000
# A sample is invalid if any gap window intersects [t - lookback, t + horizon]:
# its features would span the hole backwards or its label forwards.
FEATURE_LOOKBACK_NS = 60 * NS_PER_S
MAX_LABEL_HORIZON_NS = 30 * NS_PER_S
SAMPLES_DATASET = "research_samples"
PROGRESS_EVERY_EVENTS = 1_000_000

LABEL_COLUMNS = [f"ret_bps_{h}ms" for h in DEFAULT_HORIZONS_MS]
NET_COLUMNS = [f"y_net_{mode}_{h}ms" for mode in ("maker", "taker") for h in DEFAULT_HORIZONS_MS]
TB_COLUMNS = ["tb_label", "tb_ret_bps"]
_MAX_HORIZON_MS = max(DEFAULT_HORIZONS_MS)


def samples_partition_dir(processed_dir: Path, venue: str, symbol: str, date: str) -> Path:
    return (
        processed_dir
        / SAMPLES_DATASET
        / f"venue={venue}"
        / f"symbol={sanitize_symbol(symbol)}"
        / f"date={date}"
    )


def _samples_schema() -> pa.Schema:
    fields = [pa.field("ts_ns", pa.int64()), pa.field("valid", pa.bool_())]
    fields += [
        pa.field(name, pa.float64())
        for name in [*FEATURE_COLUMNS, *LABEL_COLUMNS, *NET_COLUMNS, *TB_COLUMNS]
    ]
    return pa.schema(fields)


def _overlaps_gap(windows: list[tuple[int, int]], starts: list[int], lo: int, hi: int) -> bool:
    """True when any half-open gap window intersects ``[lo, hi)``."""
    index = bisect_right(starts, hi) - 1
    while index >= 0:
        win_start, win_end = windows[index]
        if win_end <= lo:
            return False
        if win_start < hi:
            return True
        index -= 1
    return False


class _PendingSamples:
    """Rows in flight until every label resolves; flushed in timestamp order.

    Bounded even when label resolution stalls: sample creation and label
    resolution are driven by different event types (any sampler may fire on
    trades while labels resolve only on book mids), so a silent book feed
    must not let the buffer grow toward day size — the exact failure mode
    that OOM-killed Phase A validation. Past ``max_pending`` rows, the oldest
    sample force-flushes with its unresolved labels left ``None``: censored,
    exactly as at end of stream, because no mid ever arrived to resolve it.
    """

    def __init__(
        self,
        writer: StreamingPartWriter,
        resolutions_needed: int,
        max_pending: int = 100_000,
    ) -> None:
        self._writer = writer
        self._needed = resolutions_needed
        self._max_pending = max_pending
        self._rows: dict[int, dict[str, Any]] = {}
        self._remaining: dict[int, int] = {}
        self._order: list[int] = []
        self._next_flush = 0

    def add(self, index: int, row: dict[str, Any], tb_armed: bool) -> None:
        self._rows[index] = row
        self._remaining[index] = self._needed + (1 if tb_armed else 0)
        self._order.append(index)
        if len(self._rows) > self._max_pending:
            oldest = self._order[self._next_flush]
            self._remaining[oldest] = 0
            self._flush_ready()

    def resolve(self, index: int, updates: dict[str, Any]) -> None:
        row = self._rows.get(index)
        if row is None:
            return
        row.update(updates)
        self._remaining[index] -= 1
        self._flush_ready()

    def _flush_ready(self) -> None:
        while self._next_flush < len(self._order):
            index = self._order[self._next_flush]
            if self._remaining.get(index, 0) > 0:
                return
            row = self._rows.pop(index, None)
            if row is not None:
                self._writer.append([row])
            self._remaining.pop(index, None)
            self._next_flush += 1

    def finalize(self) -> None:
        """Censored samples flush with whatever labels resolved (rest None)."""
        for index in self._order[self._next_flush :]:
            row = self._rows.pop(index, None)
            if row is not None:
                self._writer.append([row])
            self._remaining.pop(index, None)
        self._next_flush = len(self._order)


def _find_reference(cfg: AppConfig, venue: str, symbol: str) -> tuple[str, str] | None:
    """The other venue's matching symbol, e.g. kraken BTC/USD ↔ coinbase BTC-USD."""
    for other in sorted(v for v in cfg.venues if v != venue):
        for other_symbol in cfg.venues[other].symbols:
            if sanitize_symbol(other_symbol) == sanitize_symbol(symbol):
                return other, other_symbol
    return None


def _tag(kind: str, events: Iterator[StreamEvent]) -> Iterator[tuple[int, int, str, StreamEvent]]:
    # Sort key: (local_ns, primary-first). Primary sorts first at equal ts so
    # the reference venue can never preempt a primary event's sample decision.
    priority = 0 if kind == "primary" else 1
    for event in events:
        yield (event.local_ns, priority, kind, event)


def extract_samples(
    cfg: AppConfig,
    venue: str,
    symbol: str,
    date: str,
    sampler: Sampler | None = None,
) -> Path | None:
    """Extract one venue/symbol/day of samples; returns the parquet path."""
    sampler = sampler if sampler is not None else EventBars(every_n=50)
    engine = FeatureEngine(venue, symbol, cross=CrossVenueTracker())
    fixed = FixedHorizonLabeler()
    barrier = TripleBarrierLabeler()
    windows = gap_windows(cfg.raw_dir, venue)
    window_starts = [start for start, _ in windows]
    maker = cost_model_from_config(venue, cfg.venues[venue], "maker")
    taker = cost_model_from_config(venue, cfg.venues[venue], "taker")

    partition = samples_partition_dir(cfg.processed_dir, venue, symbol, date)
    writer = StreamingPartWriter(partition / PART_NAME, _samples_schema())
    pending = _PendingSamples(writer, resolutions_needed=len(DEFAULT_HORIZONS_MS))
    entry_spread: dict[int, float | None] = {}

    tagged = [_tag("primary", merged_stream(cfg.processed_dir, venue, symbol, date))]
    reference = _find_reference(cfg, venue, symbol)
    if reference is not None:
        ref_venue, ref_symbol = reference
        tagged.append(
            _tag("reference", iter_book_events(cfg.processed_dir, ref_venue, ref_symbol, date))
        )

    index = 0
    events_seen = 0
    started = time.monotonic()
    for _, _, kind, event in heapq.merge(*tagged):
        events_seen += 1
        if events_seen % PROGRESS_EVERY_EVENTS == 0:
            elapsed = time.monotonic() - started
            print(
                f"  samples {venue} {symbol} {date}: {events_seen:,} events · "
                f"{index:,} samples · {elapsed:.0f}s elapsed",
                flush=True,
            )
        if kind == "reference":
            if event.book is not None and event.book.valid and event.book.mid is not None:
                engine.on_reference_mid(event.local_ns, event.book.mid)
            continue

        t = event.local_ns
        # Labels first: this event's mid is information after each pending
        # sample's t, and may resolve label deadlines.
        if event.book is not None and event.book.valid and event.book.mid is not None:
            for sample_index, horizon_ms, ret_bps in fixed.on_mid(t, event.book.mid):
                spread_bps = entry_spread.get(sample_index)
                pending.resolve(
                    sample_index,
                    {
                        f"ret_bps_{horizon_ms}ms": ret_bps,
                        f"y_net_maker_{horizon_ms}ms": float(
                            net_label(ret_bps, maker.round_trip_cost_bps(spread_bps))
                        ),
                        f"y_net_taker_{horizon_ms}ms": float(
                            net_label(ret_bps, taker.round_trip_cost_bps(spread_bps))
                        ),
                    },
                )
                if horizon_ms == _MAX_HORIZON_MS:
                    entry_spread.pop(sample_index, None)
            for outcome in barrier.on_mid(t, event.book.mid):
                pending.resolve(
                    outcome.index,
                    {"tb_label": float(outcome.label), "tb_ret_bps": outcome.ret_bps},
                )

        # Sample decision and features both come from state strictly before t:
        # the event at t has not been applied, and a trade's own signed qty is
        # previewed without mutating engine state.
        signed_preview = None
        if event.trade is not None:
            signed_preview = engine.preview_signed_qty(
                event.trade.price, event.trade.qty, event.trade.venue_side
            )
        should_sample = sampler.update(event, signed_preview)
        if should_sample and not event.is_warmup:
            features = engine.compute(t)
            entry_mid = engine.last_mid
            in_gap = _overlaps_gap(
                windows, window_starts, t - FEATURE_LOOKBACK_NS, t + MAX_LABEL_HORIZON_NS
            )
            valid = entry_mid is not None and engine.book_is_valid and not in_gap
            row: dict[str, Any] = {"ts_ns": t, "valid": valid, **features}
            for name in [*LABEL_COLUMNS, *NET_COLUMNS, *TB_COLUMNS]:
                row.setdefault(name, None)
            if valid and entry_mid is not None:
                fixed.on_sample(index, t, entry_mid)
                vol = features.get("rvol_30s")
                tb_armed = bool(vol) and barrier.on_sample(index, t, entry_mid, vol or 0.0)
                entry_spread[index] = features.get("spread_bps")
                pending.add(index, row, tb_armed)
            else:
                # Invalid samples are written immediately with null labels —
                # visible in the dataset, excluded from training by `valid`.
                writer.append([row])
            index += 1

        engine.on_event(event)

    for sample_index, _horizon in fixed.finalize():
        entry_spread.pop(sample_index, None)
        pending.resolve(sample_index, {})
    for sample_index in barrier.finalize():
        pending.resolve(sample_index, {})
    pending.finalize()
    return writer.close()


# --------------------------------------------------------------------------
# Training / evaluation
# --------------------------------------------------------------------------


def load_samples(paths: list[Path]) -> dict[str, NDArray[np.float64]]:
    """Concatenate sample parquet files into named float arrays (valid rows only)."""
    tables = [pq.read_table(p) for p in paths if p.is_file()]
    if not tables:
        return {}
    table = pa.concat_tables(tables)
    mask = table.column("valid").to_numpy(zero_copy_only=False).astype(bool)
    out: dict[str, NDArray[np.float64]] = {}
    for name in table.schema.names:
        if name == "valid":
            continue
        column = table.column(name).to_numpy(zero_copy_only=False)
        out[name] = np.asarray(column, dtype=np.float64)[mask]
    return out


def train_and_evaluate(
    data: dict[str, NDArray[np.float64]],
    cost_models: dict[str, CostModel],
    n_splits: int = 5,
    horizons_ms: tuple[int, ...] = DEFAULT_HORIZONS_MS,
) -> dict[str, Any]:
    """Purged-CV out-of-fold evaluation of baselines and LightGBM per horizon.

    The classifier trades every prediction (long above 0.5, short below);
    no threshold search happens here — searching a pipeline that is not yet
    trusted just finds its leaks.
    """
    if not data:
        return {"error": "no valid samples"}
    ts = data["ts_ns"].astype(np.int64)
    features = np.column_stack([data[name] for name in FEATURE_COLUMNS])
    ret_index = FEATURE_COLUMNS.index("ret_1s")
    results: dict[str, Any] = {"n_samples": len(ts), "horizons": {}}

    for horizon_ms in horizons_ms:
        y_ret = data[f"ret_bps_{horizon_ms}ms"]
        usable = ~np.isnan(y_ret)
        if int(usable.sum()) < max(200, n_splits * 20):
            results["horizons"][str(horizon_ms)] = {"skipped": "too few resolved labels"}
            continue
        x = features[usable]
        y = y_ret[usable]
        t_use = ts[usable]
        y01 = (y > 0).astype(np.int64)

        prob = np.full(len(y), np.nan)
        reg_pred = np.full(len(y), np.nan)
        importance_acc: dict[str, float] = {}
        for train_idx, test_idx in PurgedKFold(n_splits, horizon_ms * NS_PER_MS).split(
            t_use.tolist()
        ):
            if len(set(y01[train_idx].tolist())) < 2:
                continue
            clf = make_classifier()
            clf.fit(x[train_idx], y01[train_idx])
            prob[test_idx] = np.asarray(clf.predict_proba(x[test_idx]))[:, 1]
            reg = make_regressor()
            reg.fit(x[train_idx], y[train_idx])
            reg_pred[test_idx] = reg.predict(x[test_idx])
            for name, value in importances_of(clf, FEATURE_COLUMNS).items():
                importance_acc[name] = importance_acc.get(name, 0.0) + value / n_splits

        covered = ~np.isnan(prob)
        if not bool(covered.any()):
            results["horizons"][str(horizon_ms)] = {"skipped": "no out-of-fold coverage"}
            continue
        y_c, y01_c, prob_c = y[covered], y01[covered], prob[covered]
        reg_c = reg_pred[covered]
        x_c = x[covered]
        spread = data["spread_bps"][usable][covered]

        top10 = dict(sorted(importance_acc.items(), key=lambda kv: -kv[1])[:10])
        horizon_result: dict[str, Any] = {
            "n": int(covered.sum()),
            "auc": auc(y01_c, prob_c),
            "calibration": calibration_bins(y01_c, prob_c),
            "feature_importances_top10": top10,
            "cost_modes": {},
        }
        for mode, model in cost_models.items():
            costs = np.array(
                [model.round_trip_cost_bps(s if not np.isnan(s) else None) for s in spread]
            )
            predictions = {
                "model_classifier": np.where(prob_c > 0.5, 1.0, -1.0),
                "model_regressor": np.sign(reg_c),
                "baseline_zero": ZeroBaseline().predict(x_c),
                "baseline_last_sign": LastSignBaseline(ret_index).predict(x_c),
            }
            horizon_result["cost_modes"][mode] = {
                name: {
                    "hit_rate": hit_rate(pred, y_c),
                    "ev_bps_net": expected_value_bps(pred, y_c, costs),
                }
                for name, pred in predictions.items()
            }
        results["horizons"][str(horizon_ms)] = horizon_result
    return results
