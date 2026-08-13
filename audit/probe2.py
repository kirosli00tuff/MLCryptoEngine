"""Round 2: corrected expectations, natural repros, exact line-level coverage.

Synthetic events only. No data file is read or written.
"""

from __future__ import annotations

import trace as _trace

from research.microstructure.fill_replay import BoundedQuoteSim

MS = 1_000_000
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(f"{name}: {detail}")
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


def sim(**kw):
    base = {
        "symbol": "X",
        "quote_size": 100.0,
        "cap_size": None,
        "latency_ns": 0,
        "sz_decimals": 0,
        "fill_model": "always_last",
    }
    base.update(kw)
    return BoundedQuoteSim(**base)


print("=== 1. SIGN CONVENTION (corrected: sweep credits min(print, order)) ===")
s = sim()
s.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s.on_bbo(1 * MS, 100.0, 10.0, 102.0, 10.0)
s.on_trade(2 * MS, -1, 100.0, 10.0)
check(
    "1a bid fill: edge = +(mid - bid) * filled  (POSITIVE)",
    abs(s.edge_usd - (101.0 - 100.0) * 10.0) < 1e-9,
    f"edge_usd={s.edge_usd} expect=10.0",
)
check("1b bid fill leaves LONG", s.position == +10.0, f"position={s.position}")
check(
    "1c fee = leg notional * 1.5bps",
    abs(s.fees_usd - (100.0 * 10.0) * 1.5e-4) < 1e-12,
    f"fees_usd={s.fees_usd} expect={(100.0 * 10.0) * 1.5e-4}",
)

s2 = sim()
s2.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s2.on_bbo(1 * MS, 100.0, 10.0, 102.0, 10.0)
s2.on_trade(2 * MS, +1, 102.0, 10.0)
check(
    "1d ask fill: edge = +(ask - mid) * filled (POSITIVE)",
    abs(s2.edge_usd - (102.0 - 101.0) * 10.0) < 1e-9,
    f"edge_usd={s2.edge_usd}",
)
check("1e ask fill leaves SHORT", s2.position == -10.0, f"position={s2.position}")

s3 = sim(latency_ns=100 * MS)
s3.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s3.on_bbo(150 * MS, 100.0, 10.0, 102.0, 10.0)
s3.on_bbo(160 * MS, 103.0, 10.0, 105.0, 10.0)
check(
    "1f crossing fill on the stale side is NEGATIVE edge",
    s3.fills_crossing == 1 and s3.edge_usd < 0,
    f"crossing={s3.fills_crossing} edge={s3.edge_usd}",
)

print("\n=== 5f. NATURAL repro: ALO rejection raised inside on_trade ===")
s5 = sim(latency_ns=100 * MS)
s5.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s5.on_bbo(50 * MS, 97.0, 10.0, 99.0, 10.0)
check(
    "5f-i order not live at 50ms, so no ALO check yet",
    s5.alo_rejections == 0,
    f"alo={s5.alo_rejections}",
)
s5.on_trade(150 * MS, -1, 98.0, 1.0)
check(
    "5f-ii ALO rejection fires on a TRADE event", s5.alo_rejections == 1, f"alo={s5.alo_rejections}"
)
s5.on_bbo(200 * MS, 97.0, 10.0, 99.0, 10.0)
check(
    "5f-iii bid is re-quoted on the next bbo (the docstring's claim)",
    s5._orders["bid"] is not None,
    f"order={s5._orders['bid']}  <-- None means the quote was skipped",
)
s5.on_bbo(210 * MS, 97.0, 10.0, 99.0, 10.0)
check(
    "5f-iv ...it actually takes a SECOND bbo",
    s5._orders["bid"] is not None,
    f"order={s5._orders['bid']}",
)

print("\n=== 6e. 'visible' queue-ahead is read from the CURRENT touch ===")
s6 = sim(latency_ns=100 * MS)
s6.on_bbo(0, 100.0, 50.0, 102.0, 500.0)
s6.on_bbo(150 * MS, 100.0, 50.0, 102.0, 500.0)
s6.on_bbo(160 * MS, 99.0, 1.0, 101.0, 1.0)
stale = s6._orders["ask"]
s6.on_trade(200 * MS, +1, 102.0, 2.0)
check(
    "6e stale ask@102 with 500 lots ahead is swept by a 2-lot print, because "
    "'visible' was read from the new 1-lot touch at 101",
    stale is not None and stale.price == 102.0 and s6.fills_sweep == 1,
    f"order_px={stale.price if stale else None} visible={s6._ask_sz} "
    f"sweep_fills={s6.fills_sweep} print_sz=2.0 queue_ahead_at_our_level=500.0",
)

print("\n=== 7. EXACT lines of fill_replay.py the known-answer gate executes ===")
tracer = _trace.Trace(count=1, trace=0)


def _generous() -> None:
    g = BoundedQuoteSim(
        symbol="X",
        quote_size=100.0,
        cap_size=250.0,
        latency_ns=0,
        sz_decimals=0,
        fill_model="generous",
    )
    g.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
    g.on_trade(1 * MS, -1, 100.0, 10.0)
    g.on_trade(2 * MS, +1, 102.0, 10.0)
    g.on_bbo(3 * MS, 101.0, 10.0, 103.0, 10.0)
    g.on_funding(4 * MS, 1e-4, 102.0)
    g.summary()


tracer.runfunc(_generous)
hit = sorted(ln for (f, ln) in tracer.results().counts if f.endswith("fill_replay.py"))
print("  executed line numbers:", hit)
ORDER_MACHINE = {
    "_process_transitions": range(175, 192),
    "_crossing_fills": range(193, 202),
    "_cancel_stale": range(203, 213),
    "_place_wanted": range(214, 233),
    "_target_price": range(234, 239),
    "_fill": range(246, 281),
}
hitset = set(hit)
for name, rng in ORDER_MACHINE.items():
    print(f"  {name:22s} {min(rng)}-{max(rng)}  executed={sorted(hitset & set(rng))}")
all_machine = set().union(*ORDER_MACHINE.values())
check(
    "7a known-answer gate executes ANY of the order machine",
    bool(hitset & all_machine),
    f"overlap={sorted(hitset & all_machine)}",
)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
