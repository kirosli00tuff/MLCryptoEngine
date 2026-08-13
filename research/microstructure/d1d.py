"""D.1d driver: one pass, every registered variant, and the PerformanceReport.

Variants per the registration (report.md §D.1d): a known-answer run under
D.1c's generous fill model (the C.18 gate), the base bounded replay at the
declared cap and latency floor, cap sensitivity at 5x and 10x, an added-
latency grid {+50, +100, +200, +400, +800} ms, and for MERL the price-
improved end. All variants consume the same event stream in a single pass.

Outputs: ``logs/d1d_summary.json`` (every variant), and the project's first
:class:`~backtest.reporting.schema.PerformanceReport` files under
``data/processed/reports/`` — mode ``backtest``, stated explicitly because
the schema refuses a default.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson

from backtest.reporting import (
    CostAssumption,
    DrawdownPoint,
    EquityPoint,
    LatencyPercentiles,
    Mode,
    PerformanceReport,
    SlippageStats,
    TradeRecord,
)
from data.recorder.reader import iter_day_records
from research.microstructure.census import AGGRESSOR_SIGN
from research.microstructure.d1c import FUNDING_ARCHIVE_DIR, SZ_DECIMALS, load_funding_archive
from research.microstructure.fill_replay import (
    MAKER_FEE_BPS,
    AloSuppression,
    BoundedQuoteSim,
    FillModel,
    QueueModel,
)
from research.microstructure.registered import SCORED_END_NS, SCORED_START_NS

# The declared policy (registered before any replay ran).
SURVIVOR_QUOTE_SIZES: dict[str, float] = {"PUMP": 224_065.0, "MERL": 28_510.0}
CAP_MULTIPLE_DECLARED = 2.5
CAP_MULTIPLES_SENSITIVITY: tuple[float, ...] = (5.0, 10.0)
LATENCY_FLOOR_MS = 162.0
ADDED_LATENCY_GRID_MS: tuple[float, ...] = (50.0, 100.0, 200.0, 400.0, 800.0)
CAPITAL_BASE_USD = 1_250.0  # cap notional at Q sizing: 2.5 x $500

D1D_DATES: tuple[str, ...] = (
    "2026-08-04",
    "2026-08-05",
    "2026-08-06",
    "2026-08-07",
    "2026-08-08",
    "2026-08-09",
    "2026-08-10",
    "2026-08-11",
)
NS_PER_HOUR = 3_600_000_000_000
REPORTS_DIR = Path("data/processed/reports")


def _sim(
    symbol: str,
    model: FillModel,
    cap_mult: float,
    latency_ms: float,
    queue_model: QueueModel = "own_level",
    alo_suppression: AloSuppression = "update_scoped",
) -> BoundedQuoteSim:
    quote = SURVIVOR_QUOTE_SIZES[symbol]
    return BoundedQuoteSim(
        symbol=symbol,
        quote_size=quote,
        cap_size=cap_mult * quote,
        latency_ns=int(latency_ms * 1e6),
        sz_decimals=SZ_DECIMALS[symbol],
        fill_model=model,
        queue_model=queue_model,
        alo_suppression=alo_suppression,
    )


def build_variants(symbol: str) -> dict[str, BoundedQuoteSim]:
    """Every scored variant, plus the audit-correction decomposition.

    ``base`` is the corrected engine (audit A4 + A5). The four ``a*``/``as_*``
    variants exist so the 2026-08-12 published figures stay reproducible and so
    the two corrections can be read apart rather than conflated: ``as_published``
    reproduces -4.75 / -4.23 exactly, and the singles isolate each fix.
    """
    variants: dict[str, BoundedQuoteSim] = {
        "known_answer": _sim(symbol, "generous", CAP_MULTIPLE_DECLARED, 0.0),
        "base": _sim(symbol, "always_last", CAP_MULTIPLE_DECLARED, LATENCY_FLOOR_MS),
        "as_published": _sim(
            symbol, "always_last", CAP_MULTIPLE_DECLARED, LATENCY_FLOOR_MS, "touch", "legacy_leak"
        ),
        "a4_only": _sim(
            symbol,
            "always_last",
            CAP_MULTIPLE_DECLARED,
            LATENCY_FLOOR_MS,
            "own_level",
            "legacy_leak",
        ),
        "a4_only_cancels": _sim(
            symbol,
            "always_last",
            CAP_MULTIPLE_DECLARED,
            LATENCY_FLOOR_MS,
            "own_level_cancels",
            "legacy_leak",
        ),
        "a5_only": _sim(
            symbol, "always_last", CAP_MULTIPLE_DECLARED, LATENCY_FLOOR_MS, "touch", "update_scoped"
        ),
    }
    for mult in CAP_MULTIPLES_SENSITIVITY:
        variants[f"cap_{mult:g}x"] = _sim(symbol, "always_last", mult, LATENCY_FLOOR_MS)
    for added in ADDED_LATENCY_GRID_MS:
        variants[f"lat_+{added:g}ms"] = _sim(
            symbol, "always_last", CAP_MULTIPLE_DECLARED, LATENCY_FLOOR_MS + added
        )
    if symbol == "MERL":
        variants["improved"] = _sim(symbol, "improved", CAP_MULTIPLE_DECLARED, LATENCY_FLOOR_MS)
    return variants


@dataclass
class _Funding:
    archive: dict[int, float]
    last_rate: float | None = None
    last_mark: float | None = None
    applied: int = 0
    skipped: int = 0


@dataclass
class D1DRun:
    sims: dict[str, dict[str, BoundedQuoteSim]] = field(default_factory=dict)
    funding: dict[str, _Funding] = field(default_factory=dict)
    records: int = 0
    next_boundary_ns: int = SCORED_START_NS + NS_PER_HOUR

    def __post_init__(self) -> None:
        for symbol in SURVIVOR_QUOTE_SIZES:
            self.sims[symbol] = build_variants(symbol)
            self.funding[symbol] = _Funding(
                archive=load_funding_archive(FUNDING_ARCHIVE_DIR, symbol)
            )

    def _apply_funding(self, up_to_ns: int) -> None:
        while self.next_boundary_ns <= min(up_to_ns, SCORED_END_NS):
            boundary = self.next_boundary_ns
            hour_ms = boundary // 1_000_000
            for symbol, state in self.funding.items():
                rate = state.archive.get(hour_ms)
                if rate is None:
                    rate = state.last_rate
                if rate is None or state.last_mark is None:
                    state.skipped += 1
                    continue
                state.applied += 1
                for sim in self.sims[symbol].values():
                    sim.on_funding(boundary, rate, state.last_mark)
            self.next_boundary_ns += NS_PER_HOUR

    def process(self, recv_ns: int, raw: str) -> None:
        self.records += 1
        if not SCORED_START_NS <= recv_ns < SCORED_END_NS:
            return
        self._apply_funding(recv_ns)
        try:
            message = orjson.loads(raw)
        except orjson.JSONDecodeError:
            return
        channel, data = message.get("channel"), message.get("data")
        if channel == "bbo" and isinstance(data, dict):
            variants = self.sims.get(str(data.get("coin")))
            if variants is None:
                return
            pair = data.get("bbo") or [None, None]
            try:
                bid_px, bid_sz = float(pair[0]["px"]), float(pair[0]["sz"])
                ask_px, ask_sz = float(pair[1]["px"]), float(pair[1]["sz"])
            except (KeyError, TypeError, ValueError):
                return
            for sim in variants.values():
                sim.on_bbo(recv_ns, bid_px, bid_sz, ask_px, ask_sz)
        elif channel == "trades" and isinstance(data, list):
            for print_ in data:
                if not isinstance(print_, dict):
                    continue
                variants = self.sims.get(str(print_.get("coin")))
                sign = AGGRESSOR_SIGN.get(str(print_.get("side")))
                if variants is None or sign is None:
                    continue
                try:
                    px, sz = float(print_["px"]), float(print_["sz"])
                except (KeyError, TypeError, ValueError):
                    continue
                for sim in variants.values():
                    sim.on_trade(recv_ns, sign, px, sz)
        elif channel == "activeAssetCtx" and isinstance(data, dict):
            state = self.funding.get(str(data.get("coin")))
            ctx = data.get("ctx")
            if state is None or not isinstance(ctx, dict):
                return
            try:
                state.last_rate = float(ctx["funding"])
                state.last_mark = float(ctx["markPx"])
            except (KeyError, TypeError, ValueError):
                return

    def close(self) -> None:
        self._apply_funding(SCORED_END_NS)


def zero_crossing_ms(points: list[tuple[float, float]]) -> float | None:
    """Added latency where net crosses zero, linearly interpolated; None if never."""
    from itertools import pairwise

    for (x0, y0), (x1, y1) in pairwise(sorted(points)):
        if y0 > 0.0 >= y1:
            return x0 + (x1 - x0) * y0 / (y0 - y1)
    return None


def performance_report(sim: BoundedQuoteSim, run_id: str) -> PerformanceReport:
    """Map one variant's ledger onto the Phase B contract (mode: backtest).

    Trade records are per maker leg (entry == exit == the fill instant);
    drawdown is a percentage of the declared capital base (the cap notional).
    """
    hours = sorted(set(sim.net_by_hour) | set(sim.fees_by_hour))
    cum_net = cum_gross = peak = 0.0
    equity: list[EquityPoint] = []
    drawdown: list[DrawdownPoint] = []
    for hour in hours:
        net_delta = sim.net_by_hour.get(hour, 0.0)
        fee_delta = sim.fees_by_hour.get(hour, 0.0)
        cum_net += net_delta
        cum_gross += net_delta + fee_delta
        ts = hour * NS_PER_HOUR
        equity.append(EquityPoint(ts_ns=ts, gross=round(cum_gross, 6), net=round(cum_net, 6)))
        peak = max(peak, cum_net)
        drawdown.append(
            DrawdownPoint(
                ts_ns=ts,
                drawdown_pct=round(min(0.0, (cum_net - peak) / CAPITAL_BASE_USD * 100.0), 6),
            )
        )
    trades = [
        TradeRecord(
            entry_ns=ts,
            exit_ns=ts,
            side=side,  # type: ignore[arg-type]
            size=size,
            gross_pnl=round(edge, 8),
            fees=round(fee, 8),
            net_pnl=round(edge - fee, 8),
        )
        for ts, side, size, _px, edge, fee in sim.trade_records
    ]
    summary = sim.summary()
    # A12: summary() returns None for these when nothing filled. Coercing to 0.0
    # would publish a metric computed on an empty set as though it were a
    # measurement -- the exact failure the dashboard rule forbids. Refuse instead.
    if summary["net_bps"] is None or summary["edge_bps"] is None:
        raise ValueError(
            f"{sim.symbol}/{sim.fill_model}: no fills, so expectancy and realized "
            f"edge are undefined; a PerformanceReport must not report 0.0 for them"
        )
    return PerformanceReport(
        run_id=run_id,
        mode=Mode.BACKTEST,
        venue="hyperliquid",
        symbol=sim.symbol,
        data_start_ns=SCORED_START_NS,
        data_end_ns=SCORED_END_NS,
        cost=CostAssumption(mode="maker", fee_bps_per_leg=MAKER_FEE_BPS, includes_spread=True),
        equity_curve=equity,
        drawdown=drawdown,
        trades=trades,
        expectancy_bps_net=float(summary["net_bps"]),
        hit_rate=None,
        slippage=SlippageStats(
            expected_bps=float(summary["expected_edge_bps"] or 0.0),
            realized_bps=float(summary["edge_bps"]),
        ),
        latency=LatencyPercentiles(
            p50_ms=sim.latency_ns / 1e6, p95_ms=sim.latency_ns / 1e6, p99_ms=sim.latency_ns / 1e6
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("logs/d1d_summary.json"))
    args = parser.parse_args()
    started = time.perf_counter()
    run = D1DRun()
    for date in D1D_DATES:
        day_start = time.perf_counter()
        for recv_ns, raw in iter_day_records(args.raw_dir, "hyperliquid", date):
            if recv_ns >= SCORED_END_NS:
                break
            run.process(recv_ns, raw)
        print(f"{date}: {run.records:,} records, {time.perf_counter() - day_start:.0f}s")
    run.close()

    out: dict[str, Any] = {"records": run.records, "variants": {}, "zero_crossing_ms": {}}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for symbol, variants in run.sims.items():
        out["variants"][symbol] = {key: sim.summary() for key, sim in variants.items()}
        grid = [(0.0, float(variants["base"].summary()["net_bps"] or 0.0))]
        for added in ADDED_LATENCY_GRID_MS:
            grid.append((added, float(variants[f"lat_+{added:g}ms"].summary()["net_bps"] or 0.0)))
        out["zero_crossing_ms"][symbol] = zero_crossing_ms(grid)
        out["variants"][symbol]["latency_grid"] = grid
        for key in ("base", "improved") if symbol == "MERL" else ("base",):
            report = performance_report(variants[key], run_id=f"d1d-{symbol}-{key}-2026-08-12")
            path = REPORTS_DIR / f"d1d_{symbol}_{key}.json"
            path.write_text(report.model_dump_json(indent=1))
            print(f"wrote {path} ({len(report.trades):,} trade records)")
    out["funding"] = {
        symbol: {"applied": st.applied, "skipped": st.skipped} for symbol, st in run.funding.items()
    }
    out["elapsed_s"] = round(time.perf_counter() - started, 1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"wrote {args.out} in {out['elapsed_s']}s")


if __name__ == "__main__":
    main()
