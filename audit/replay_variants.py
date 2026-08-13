"""Independent D.1d re-runs: reproduction, a TRUE no-crossing counterfactual,
and a feed-interleaving sensitivity probe. Writes only to the scratchpad.
"""

from __future__ import annotations

import argparse
import heapq
import json
import time
from pathlib import Path

import orjson

from data.recorder.reader import iter_day_records
from research.microstructure.census import AGGRESSOR_SIGN
from research.microstructure.d1c import FUNDING_ARCHIVE_DIR, SZ_DECIMALS, load_funding_archive
from research.microstructure.d1d import (
    CAP_MULTIPLE_DECLARED,
    D1D_DATES,
    LATENCY_FLOOR_MS,
    NS_PER_HOUR,
    SURVIVOR_QUOTE_SIZES,
)
from research.microstructure.fill_replay import BoundedQuoteSim
from research.microstructure.registered import SCORED_END_NS, SCORED_START_NS


class NoCrossingSim(BoundedQuoteSim):
    """The §2b counterfactual done properly: the stale quote is never run over.

    §2b subtracts the crossing rows arithmetically and keeps the inventory term
    at its full-notional bps. The ledger is path dependent -- removing fills
    changes the position path, hence inventory, hence net. This re-runs it.
    """

    def _crossing_fills(self, ts_ns: int, bid_px: float, ask_px: float) -> None:
        return


def build(symbol: str, cls: type[BoundedQuoteSim]) -> BoundedQuoteSim:
    q = SURVIVOR_QUOTE_SIZES[symbol]
    return cls(
        symbol=symbol,
        quote_size=q,
        cap_size=CAP_MULTIPLE_DECLARED * q,
        latency_ns=int(LATENCY_FLOOR_MS * 1e6),
        sz_decimals=SZ_DECIMALS[symbol],
        fill_model="always_last",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    ap.add_argument("--trade-shift-ms", type=float, default=0.0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    shift_ns = int(args.trade_shift_ms * 1e6)
    sims: dict[str, dict[str, BoundedQuoteSim]] = {
        s: {"base": build(s, BoundedQuoteSim), "no_crossing": build(s, NoCrossingSim)}
        for s in SURVIVOR_QUOTE_SIZES
    }
    funding = {s: load_funding_archive(FUNDING_ARCHIVE_DIR, s) for s in SURVIVOR_QUOTE_SIZES}
    last_rate: dict[str, float | None] = dict.fromkeys(SURVIVOR_QUOTE_SIZES)
    last_mark: dict[str, float | None] = dict.fromkeys(SURVIVOR_QUOTE_SIZES)
    state = {"next": SCORED_START_NS + NS_PER_HOUR, "applied": 0, "skipped": 0}

    def apply_funding(up_to: int) -> None:
        while state["next"] <= min(up_to, SCORED_END_NS):
            b = state["next"]
            for sym in SURVIVOR_QUOTE_SIZES:
                rate = funding[sym].get(b // 1_000_000)
                if rate is None:
                    rate = last_rate[sym]
                if rate is None or last_mark[sym] is None:
                    state["skipped"] += 1
                    continue
                state["applied"] += 1
                for sim in sims[sym].values():
                    sim.on_funding(b, rate, last_mark[sym])
            state["next"] += NS_PER_HOUR

    def handle(recv_ns: int, message: dict) -> None:
        apply_funding(recv_ns)
        channel, data = message.get("channel"), message.get("data")
        if channel == "bbo" and isinstance(data, dict):
            group = sims.get(str(data.get("coin")))
            if group is None:
                return
            pair = data.get("bbo") or [None, None]
            try:
                bpx, bsz = float(pair[0]["px"]), float(pair[0]["sz"])
                apx, asz = float(pair[1]["px"]), float(pair[1]["sz"])
            except (KeyError, TypeError, ValueError, IndexError):
                return
            for sim in group.values():
                sim.on_bbo(recv_ns, bpx, bsz, apx, asz)
        elif channel == "trades" and isinstance(data, list):
            for p in data:
                if not isinstance(p, dict):
                    continue
                group = sims.get(str(p.get("coin")))
                sign = AGGRESSOR_SIGN.get(str(p.get("side")))
                if group is None or sign is None:
                    continue
                try:
                    px, sz = float(p["px"]), float(p["sz"])
                except (KeyError, TypeError, ValueError):
                    continue
                for sim in group.values():
                    sim.on_trade(recv_ns, sign, px, sz)
        elif channel == "activeAssetCtx" and isinstance(data, dict):
            sym = str(data.get("coin"))
            ctx = data.get("ctx")
            if sym not in last_rate or not isinstance(ctx, dict):
                return
            try:
                last_rate[sym] = float(ctx["funding"])
                last_mark[sym] = float(ctx["markPx"])
            except (KeyError, TypeError, ValueError):
                return

    heap: list[tuple[int, int, dict]] = []
    seq = 0
    records = 0
    started = time.perf_counter()
    for date in D1D_DATES:
        for recv_ns, raw in iter_day_records(args.raw_dir, "hyperliquid", date):
            if recv_ns >= SCORED_END_NS:
                break
            records += 1
            if not SCORED_START_NS <= recv_ns < SCORED_END_NS:
                continue
            try:
                message = orjson.loads(raw)
            except orjson.JSONDecodeError:
                continue
            ch = message.get("channel")
            if ch not in ("bbo", "trades", "activeAssetCtx"):
                continue
            ts = recv_ns + (shift_ns if ch == "trades" else 0)
            if shift_ns == 0:
                handle(ts, message)
                continue
            seq += 1
            heapq.heappush(heap, (ts, seq, message))
            while heap and heap[0][0] <= recv_ns - abs(shift_ns):
                t, _, m = heapq.heappop(heap)
                handle(t, m)
        print(f"  {date}: {records:,} records, {time.perf_counter() - started:.0f}s", flush=True)
    while heap:
        t, _, m = heapq.heappop(heap)
        handle(t, m)
    apply_funding(SCORED_END_NS)

    out = {
        "trade_shift_ms": args.trade_shift_ms,
        "records": records,
        "funding": dict(state),
        "elapsed_s": round(time.perf_counter() - started, 1),
        "variants": {s: {k: v.summary() for k, v in g.items()} for s, g in sims.items()},
    }
    args.out.write_text(json.dumps(out, indent=1))
    print(f"wrote {args.out} in {out['elapsed_s']}s")
    for s, g in sims.items():
        for k, v in g.items():
            d = v.summary()
            print(
                f"  {s:5s} {k:12s} net={d['net_bps']:+8.4f} edge={d['edge_bps']:+8.4f} "
                f"inv={d['inventory_bps']:+8.4f} fills={d['fills']:>7,} "
                f"notional=${d['filled_notional_usd']:,.0f}"
            )


if __name__ == "__main__":
    main()
