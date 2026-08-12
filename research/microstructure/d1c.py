"""D.1c: one streaming pass — tick geometry, inventory, longer horizons.

Replays the census week (the C.27 scored window) once, feeding three
independent accumulator families:

- :class:`~research.microstructure.tick.SpreadTicks` for all 12 recorded
  instruments — is the measured spread quotable inside, or tick-pinned?
- :class:`~research.microstructure.horizons.HorizonNet` for the 10 thin census
  instruments — does the census sign hold at 300 s and 900 s?
- :class:`~research.microstructure.inventory.InventorySim` for the survivors
  (PUMP, MERL) under the policy registered in report.md §D.1c — what does the
  position held between fills cost?

Funding is applied hourly at the boundary: the C.11 ``fundingHistory`` archive
rate where the hour is covered, else the last recorded ``activeAssetCtx``
funding at or before the boundary; overlap hours cross-check the two sources.

Quotes are consumed for a 900 s tail past the window end so trades armed near
the close still resolve; nothing is armed, filled, or time-credited past the
window end itself.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson

from data.recorder.reader import iter_day_records
from research.microstructure.census import AGGRESSOR_SIGN, _quote
from research.microstructure.horizons import HorizonNet
from research.microstructure.inventory import InventorySim
from research.microstructure.registered import SCORED_END_NS, SCORED_START_NS, THIN_COINS
from research.microstructure.tick import SpreadTicks

# szDecimals per recorded instrument, retrieved 2026-08-12 from the info
# endpoint ({"type": "meta"}) — venue metadata, re-verifiable with one call.
SZ_DECIMALS: dict[str, int] = {
    "BTC": 5,
    "ETH": 4,
    "HYPE": 2,
    "SOL": 2,
    "PUMP": 0,
    "DOT": 1,
    "LINK": 1,
    "ARB": 1,
    "GMX": 2,
    "MERL": 0,
    "TNSR": 1,
    "NOT": 0,
}
SURVIVORS: tuple[str, ...] = ("PUMP", "MERL")
QUOTE_NOTIONAL_USD = 500.0
CAP_MULTIPLES: tuple[float, ...] = (2.5, 5.0, 10.0)
D1C_DATES: tuple[str, ...] = (
    "2026-08-04",
    "2026-08-05",
    "2026-08-06",
    "2026-08-07",
    "2026-08-08",
    "2026-08-09",
    "2026-08-10",
    "2026-08-11",
)
FUNDING_ARCHIVE_DIR = Path("data/vendor/archive/hyperliquid/info/fundingHistory")
NS_PER_HOUR = 3_600_000_000_000
MS_PER_HOUR = 3_600_000
RESOLUTION_TAIL_NS = 900_000 * 1_000_000


def load_funding_archive(base: Path, coin: str) -> dict[int, float]:
    """Hour-boundary (epoch ms) → hourly funding rate from the C.11 archive."""
    rates: dict[int, float] = {}
    coin_dir = base / f"coin={coin}"
    if not coin_dir.is_dir():
        return rates
    for path in sorted(coin_dir.glob("start=*.json")):
        for row in json.loads(path.read_text()):
            hour_ms = round(int(row["time"]) / MS_PER_HOUR) * MS_PER_HOUR
            rates[hour_ms] = float(row["fundingRate"])
    return rates


@dataclass
class _FundingState:
    """Rate application bookkeeping for one survivor."""

    archive: dict[int, float]
    last_ctx_rate: float | None = None
    last_ctx_mark: float | None = None
    last_ctx_ns: int | None = None
    hours_from_archive: int = 0
    hours_from_ctx: int = 0
    hours_skipped: int = 0
    hours_stale_ctx: int = 0
    overlap_hours: int = 0
    overlap_abs_diff_sum: float = 0.0


@dataclass
class D1CRun:
    """All accumulators for the single pass."""

    ticks: dict[str, SpreadTicks] = field(default_factory=dict)
    horizons: dict[str, HorizonNet] = field(default_factory=dict)
    sims: dict[str, list[InventorySim]] = field(default_factory=dict)
    funding: dict[str, _FundingState] = field(default_factory=dict)
    last_mid: dict[str, float] = field(default_factory=dict)
    records: int = 0
    next_boundary_ns: int = SCORED_START_NS + NS_PER_HOUR

    def __post_init__(self) -> None:
        half_split = (SCORED_START_NS + SCORED_END_NS) // 2
        for coin, szd in SZ_DECIMALS.items():
            self.ticks[coin] = SpreadTicks(symbol=coin, sz_decimals=szd)
        for coin in sorted(THIN_COINS):
            self.horizons[coin] = HorizonNet(symbol=coin, half_split_ns=half_split)
        for coin in SURVIVORS:
            self.funding[coin] = _FundingState(
                archive=load_funding_archive(FUNDING_ARCHIVE_DIR, coin)
            )

    def _ensure_sims(self, coin: str, mid: float) -> None:
        """Size the fixed quote from the first scored-window mid, as registered."""
        if coin in self.sims or mid <= 0.0:
            return
        quote_size = round(QUOTE_NOTIONAL_USD / mid, SZ_DECIMALS[coin])
        self.sims[coin] = [InventorySim(symbol=coin, quote_size=quote_size)] + [
            InventorySim(symbol=coin, quote_size=quote_size, cap_size=m * quote_size)
            for m in CAP_MULTIPLES
        ]

    def _apply_funding_boundaries(self, up_to_ns: int) -> None:
        while self.next_boundary_ns <= min(up_to_ns, SCORED_END_NS):
            boundary_ns = self.next_boundary_ns
            hour_ms = boundary_ns // 1_000_000
            for coin in SURVIVORS:
                state = self.funding[coin]
                archive_rate = state.archive.get(hour_ms)
                rate = archive_rate if archive_rate is not None else state.last_ctx_rate
                mark = state.last_ctx_mark or self.last_mid.get(coin)
                if rate is None or mark is None:
                    # Only inside the 08-04 recorder hole before any message:
                    # no position can exist there either, so nothing is lost.
                    state.hours_skipped += 1
                    continue
                if archive_rate is not None:
                    state.hours_from_archive += 1
                    if state.last_ctx_rate is not None:
                        state.overlap_hours += 1
                        state.overlap_abs_diff_sum += abs(archive_rate - state.last_ctx_rate)
                else:
                    state.hours_from_ctx += 1
                    if (
                        state.last_ctx_ns is None
                        or boundary_ns - state.last_ctx_ns > 2 * NS_PER_HOUR
                    ):
                        state.hours_stale_ctx += 1
                for sim in self.sims.get(coin, []):
                    sim.on_funding(boundary_ns, rate, mark)
            self.next_boundary_ns += NS_PER_HOUR

    def process(self, recv_ns: int, raw: str) -> None:
        self.records += 1
        in_window = SCORED_START_NS <= recv_ns < SCORED_END_NS
        self._apply_funding_boundaries(recv_ns)
        try:
            message = orjson.loads(raw)
        except orjson.JSONDecodeError:
            return
        channel, data = message.get("channel"), message.get("data")
        if channel == "bbo" and isinstance(data, dict):
            coin = str(data.get("coin"))
            quote = _quote(data.get("bbo") or [])
            if quote is None:
                return
            bid, ask = quote
            horizon = self.horizons.get(coin)
            if horizon is not None:
                horizon.on_quote(recv_ns, bid, ask)
            if not in_window:
                return
            tick = self.ticks.get(coin)
            if tick is not None:
                tick.observe(recv_ns, bid, ask)
            if bid > 0.0 and ask > 0.0:
                self.last_mid[coin] = 0.5 * (bid + ask)
            if coin in SURVIVORS:
                self._ensure_sims(coin, self.last_mid.get(coin, 0.0))
                for sim in self.sims.get(coin, []):
                    sim.on_quote(recv_ns, bid, ask)
        elif channel == "trades" and isinstance(data, list) and in_window:
            for print_ in data:
                if not isinstance(print_, dict):
                    continue
                coin = str(print_.get("coin"))
                sign = AGGRESSOR_SIGN.get(str(print_.get("side")))
                if sign is None:
                    continue
                horizon = self.horizons.get(coin)
                if horizon is not None:
                    horizon.on_trade(recv_ns, sign)
                if coin in SURVIVORS and coin in self.sims:
                    try:
                        size = float(print_["sz"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    for sim in self.sims[coin]:
                        sim.on_trade(recv_ns, sign, size)
        elif channel == "activeAssetCtx" and isinstance(data, dict) and in_window:
            coin = str(data.get("coin"))
            state = self.funding.get(coin)
            ctx = data.get("ctx")
            if state is None or not isinstance(ctx, dict):
                return
            try:
                state.last_ctx_rate = float(ctx["funding"])
                state.last_ctx_mark = float(ctx["markPx"])
                state.last_ctx_ns = recv_ns
            except (KeyError, TypeError, ValueError):
                return

    def close(self) -> None:
        self._apply_funding_boundaries(SCORED_END_NS)
        for tick in self.ticks.values():
            tick.close(SCORED_END_NS)

    def summary(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "tick_geometry": {coin: self.ticks[coin].summary() for coin in sorted(self.ticks)},
            "horizons": {coin: self.horizons[coin].summary() for coin in sorted(self.horizons)},
            "inventory": {
                coin: [sim.summary() for sim in sims] for coin, sims in sorted(self.sims.items())
            },
            "funding_sources": {
                coin: {
                    "hours_from_archive": state.hours_from_archive,
                    "hours_from_ctx": state.hours_from_ctx,
                    "hours_skipped": state.hours_skipped,
                    "hours_stale_ctx": state.hours_stale_ctx,
                    "overlap_hours": state.overlap_hours,
                    "overlap_mean_abs_diff": (
                        state.overlap_abs_diff_sum / state.overlap_hours
                        if state.overlap_hours
                        else None
                    ),
                }
                for coin, state in self.funding.items()
            },
        }


def run_d1c(raw_dir: Path, dates: tuple[str, ...] = D1C_DATES) -> dict[str, Any]:
    """Replay the scored window plus the resolution tail; return the summary."""
    run = D1CRun()
    for date in dates:
        started = time.perf_counter()
        for recv_ns, raw in iter_day_records(raw_dir, "hyperliquid", date):
            if recv_ns >= SCORED_END_NS + RESOLUTION_TAIL_NS:
                break
            run.process(recv_ns, raw)
        print(f"{date}: {run.records:,} records cumulative, {time.perf_counter() - started:.0f}s")
    run.close()
    return run.summary()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("logs/d1c_summary.json"))
    args = parser.parse_args()
    started = time.perf_counter()
    summary = run_d1c(args.raw_dir)
    summary["elapsed_s"] = round(time.perf_counter() - started, 1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=1))
    print(f"wrote {args.out} in {summary['elapsed_s']}s")


if __name__ == "__main__":
    main()
