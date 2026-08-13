"""Re-run the registered census and price the independence assumption.

registered.py:_horizon_stats builds se = sqrt(var/n) -- the IID standard error.
This reruns the identical rows through the identical accumulators, then adds
three corrections the repo does not implement anywhere: Newey-West (HAC),
a moving-block bootstrap, and a day-clustered SE.
Reads raw read-only through the project's own feed; writes one scratchpad JSON.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from research.microstructure.registered import (
    HORIZONS_MS,
    NS_PER_DAY,
    ROUND_TRIP_BPS,
    SAMPLE_FLOOR_TRADES,
    THIN_COINS,
    RegisteredInstrument,
    _horizon_stats,
    _ReplayFeed,
)

DATES = [
    "2026-08-04",
    "2026-08-05",
    "2026-08-06",
    "2026-08-07",
    "2026-08-08",
    "2026-08-09",
    "2026-08-10",
    "2026-08-11",
]
RAW = Path("data/raw")
random.seed(20260812)


def newey_west_se(x: list[float], lag: int) -> float:
    n = len(x)
    mu = sum(x) / n
    d = [v - mu for v in x]
    s = sum(v * v for v in d) / n
    for k in range(1, min(lag, n - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        gk = sum(d[i] * d[i + k] for i in range(n - k)) / n
        s += 2.0 * w * gk
    return math.sqrt(max(s, 1e-30) / n)


def block_bootstrap_lower(x: list[float], block: int, reps: int = 300) -> float:
    n = len(x)
    nb = max(1, n // block)
    means = []
    for _ in range(reps):
        tot = 0.0
        for _ in range(nb):
            st = random.randrange(0, max(1, n - block))
            tot += sum(x[st : st + block])
        means.append(tot / (nb * block))
    means.sort()
    return means[int(0.05 * len(means))]


def main() -> None:
    inst = {c: RegisteredInstrument(symbol=c) for c in sorted(THIN_COINS)}
    feed = _ReplayFeed(inst)
    for d in DATES:
        feed.run_day(RAW, d)
        print(f"  {d} done", flush=True)

    out: dict = {}
    for coin in sorted(inst):
        i = inst[coin]
        best = None
        for h in HORIZONS_MS:
            rows = i.rows[h]
            if len(rows) < SAMPLE_FLOOR_TRADES:
                continue
            st = _horizon_stats(rows)
            if best is None or st["ci95_lower_bps"] < best[1]["ci95_lower_bps"]:
                best = (h, st, rows)
        if best is None:
            out[coin] = {
                "floor_met": False,
                "n_by_horizon": {h: len(i.rows[h]) for h in HORIZONS_MS},
            }
            print(f"{coin:6s} FLOOR NOT MET {out[coin]['n_by_horizon']}", flush=True)
            continue
        h, st, rows = best
        nets = [s - a - ROUND_TRIP_BPS for _, s, a in rows]
        n = len(nets)
        span_ns = rows[-1][0] - rows[0][0]
        tps = n / (span_ns / 1e9) if span_ns else 0.0
        lag = max(1, min(int(tps * h / 1000.0), n // 20, 3000))
        iid_se = (st["net_mean_bps"] - st["ci95_lower_bps"]) / 1.6449 if n > 2 else float("nan")
        nw = newey_west_se(nets, lag)
        bb = block_bootstrap_lower(nets, block=max(lag, 50))
        by_day: dict[int, list[float]] = {}
        for ts, s, a in rows:
            by_day.setdefault(ts // NS_PER_DAY, []).append(s - a - ROUND_TRIP_BPS)
        dm = [sum(v) / len(v) for v in by_day.values()]
        if len(dm) > 1:
            mu = sum(dm) / len(dm)
            day_se = math.sqrt(sum((v - mu) ** 2 for v in dm) / (len(dm) - 1) / len(dm))
        else:
            day_se = float("nan")
        out[coin] = {
            "worst_horizon_ms": h,
            "n": n,
            "net_mean_bps": st["net_mean_bps"],
            "reported_ci95_lower_bps": st["ci95_lower_bps"],
            "reported_halfwidth_bps": st["net_mean_bps"] - st["ci95_lower_bps"],
            "iid_se": iid_se,
            "sd_of_nets": math.sqrt(sum((v - st["net_mean_bps"]) ** 2 for v in nets) / (n - 1)),
            "overlap_lag_trades": lag,
            "trades_per_sec": tps,
            "newey_west_se": nw,
            "nw_over_iid": nw / iid_se if iid_se else float("nan"),
            "nw_ci95_lower_bps": st["net_mean_bps"] - 1.6449 * nw,
            "block_bootstrap_ci90_lower_bps": bb,
            "day_cluster_se": day_se,
            "day_cluster_ci95_lower_bps": st["net_mean_bps"] - 1.943 * day_se,
            "n_days": len(dm),
            "day_means_bps": sorted(dm),
            "p_one_sided_iid": st["p_one_sided"],
        }
        r = out[coin]
        print(
            f"{coin:6s} h={h:>6} n={n:>7,} mean={r['net_mean_bps']:+7.3f} "
            f"iid_lo={r['reported_ci95_lower_bps']:+7.3f} "
            f"NW_lo={r['nw_ci95_lower_bps']:+7.3f} (SEx{r['nw_over_iid']:.1f}) "
            f"day_lo={r['day_cluster_ci95_lower_bps']:+7.3f} boot_lo={bb:+7.3f}",
            flush=True,
        )

    print("\n--- half-width vs independent-sampling scaling ---")
    for coin, r in out.items():
        if "n" in r:
            print(
                f"  {coin:6s} n={r['n']:>7,} halfwidth={r['reported_halfwidth_bps']:.4f} "
                f"sd={r['sd_of_nets']:.3f} "
                f"halfwidth*sqrt(n)={r['reported_halfwidth_bps'] * math.sqrt(r['n']):.3f}"
            )
    Path("../census_ci.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote ../census_ci.json")


if __name__ == "__main__":
    main()
