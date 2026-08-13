"""Adversarial probes against research.microstructure.fill_replay.BoundedQuoteSim.

Every probe is a *behavioural* assertion run against the shipped code, not a
reading of it. Failures are printed, not raised, so the whole battery runs.
Synthetic events only -- no data file is read or written.
"""

from __future__ import annotations

import inspect
import trace as _trace

import research.microstructure.fill_replay as fr
from research.microstructure.fill_replay import BoundedQuoteSim

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


MS = 1_000_000

# --------------------------------------------------------------- 1. sign ---
s = sim(latency_ns=0)
s.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s.on_bbo(1 * MS, 100.0, 10.0, 102.0, 10.0)
s.on_trade(2 * MS, -1, 100.0, 10.0)
check(
    "1a realized edge on a bid fill is POSITIVE half-spread",
    abs(s.edge_usd - (101.0 - 100.0) * 100.0) < 1e-9,
    f"edge_usd={s.edge_usd} expected={(101.0 - 100.0) * 100.0}",
)
check("1b bid fill leaves LONG position", s.position == +100.0, f"position={s.position}")

s2 = sim(latency_ns=0)
s2.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s2.on_bbo(1 * MS, 100.0, 10.0, 102.0, 10.0)
s2.on_trade(2 * MS, +1, 102.0, 10.0)
check(
    "1c realized edge on an ask fill is POSITIVE half-spread",
    abs(s2.edge_usd - (102.0 - 101.0) * 100.0) < 1e-9,
    f"edge_usd={s2.edge_usd}",
)
check("1d ask fill leaves SHORT position", s2.position == -100.0, f"position={s2.position}")

# ---------------------------------------------------------------- 2. fee ---
check(
    "2a fee is charged PER SIDE at 1.5 bps of that leg's notional",
    abs(s.fees_usd - 100.0 * 100.0 * 1.5 / 1e4) < 1e-12,
    f"fees_usd={s.fees_usd} leg_notional={100.0 * 100.0}",
)
check(
    "2b fees_bps in summary is the per-leg rate (NOT the 3.0 round trip)",
    abs(s.summary()["fees_bps"] - 1.5) < 1e-9,
    f"fees_bps={s.summary()['fees_bps']}",
)

# -------------------------------------------------------- 3. decomposition --
s3 = sim(latency_ns=0)
s3.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s3.on_bbo(1 * MS, 100.0, 10.0, 102.0, 10.0)
s3.on_trade(2 * MS, -1, 100.0, 10.0)
s3.on_bbo(3 * MS, 101.0, 10.0, 103.0, 10.0)
s3.on_funding(4 * MS, 0.0001, 102.0)
ident = s3.edge_usd + s3.inventory_usd + s3.funding_usd - s3.fees_usd
check(
    "3a total_net == edge + inv + funding - fees",
    abs(s3.total_net_usd() - ident) < 1e-9,
    f"net={s3.total_net_usd()} sum={ident}",
)
mtm = s3.mark_to_market_usd()
check(
    "3b mark-to-market == edge + inventory",
    abs(mtm - (s3.edge_usd + s3.inventory_usd)) < 1e-9,
    f"mtm={mtm} edge+inv={s3.edge_usd + s3.inventory_usd}",
)

# ------------------------------------------------- 4. latency, both ways ---
L = 100 * MS
s4 = sim(latency_ns=L)
s4.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s4.on_trade(50 * MS, -1, 100.0, 10.0)
check("4a placement latency: no fill before active_ns", s4.fills == 0, f"fills={s4.fills}")
s4.on_trade(150 * MS, -1, 100.0, 10.0)
check("4b placement latency: fills after active_ns", s4.fills == 1, f"fills={s4.fills}")

s5 = sim(latency_ns=L)
s5.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s5.on_bbo(120 * MS, 99.0, 10.0, 101.0, 10.0)
check(
    "4c cancel is issued when the touch leaves our price",
    s5.cancels_started >= 1,
    f"cancels_started={s5.cancels_started}",
)
check(
    "4d cancel is NOT instantaneous",
    s5._orders["bid"] is not None and s5._orders["bid"].cancel_dead_ns == 220 * MS,
    f"cancel_dead_ns={s5._orders['bid'].cancel_dead_ns if s5._orders['bid'] else None}",
)
s5.on_trade(150 * MS, -1, 100.0, 10.0)
check(
    "4e order stays fillable at its stale price during cancel-in-flight",
    s5.fills == 1,
    f"fills={s5.fills}",
)

s6 = sim(latency_ns=L)
s6.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s6.on_bbo(120 * MS, 99.0, 10.0, 101.0, 10.0)
s6.on_bbo(230 * MS, 99.0, 10.0, 101.0, 10.0)
check(
    "4f cancel completes only after one latency, then re-places with one more",
    s6._orders["bid"] is not None and s6._orders["bid"].active_ns == 330 * MS,
    f"replacement active_ns={s6._orders['bid'].active_ns if s6._orders['bid'] else None}",
)

# ---------------------------------------------------------------- 5. ALO ---
s7 = sim(latency_ns=L)
s7.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s7.on_bbo(150 * MS, 97.0, 10.0, 99.0, 10.0)
check(
    "5a ALO rejects an order that would cross on arrival",
    s7.alo_rejections == 1,
    f"alo_rejections={s7.alo_rejections}",
)
s8 = sim(latency_ns=L)
s8.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s8.on_bbo(150 * MS, 100.0, 10.0, 102.0, 10.0)
check(
    "5b ALO does NOT reject a non-crossing order",
    s8.alo_rejections == 0,
    f"alo_rejections={s8.alo_rejections}",
)
s9 = sim(latency_ns=L)
s9.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s9.on_bbo(150 * MS, 99.5, 10.0, 100.5, 10.0)
check(
    "5c ALO does not fire merely because the touch moved",
    s9.alo_rejections == 0,
    f"alo_rejections={s9.alo_rejections}",
)
s10 = sim(latency_ns=0)
s10.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s10.on_bbo(1 * MS, 100.0, 10.0, 102.0, 10.0)
before = s10.alo_rejections
s10.on_bbo(2 * MS, 90.0, 10.0, 91.0, 10.0)
check(
    "5d ALO is one-shot: a later cross is a FILL, not a rejection",
    s10.alo_rejections == before and s10.fills_crossing == 1,
    f"alo={s10.alo_rejections} crossing_fills={s10.fills_crossing}",
)

# ---- 5e: is an ALO rejection also blocking the *following* update's quote? ----
s10b = sim(latency_ns=L)
s10b.on_bbo(0, 100.0, 10.0, 102.0, 10.0)
s10b.on_bbo(150 * MS, 97.0, 10.0, 99.0, 10.0)  # bid ALO-rejected here
placed_same = s10b._orders["bid"] is not None
s10b.on_bbo(160 * MS, 97.0, 10.0, 99.0, 10.0)  # next update: should re-place
check(
    "5e after an ALO rejection the side is re-quoted on the NEXT bbo",
    (not placed_same) and s10b._orders["bid"] is not None,
    f"same_update_placed={placed_same} next_update_placed={s10b._orders['bid'] is not None}",
)

# ---- 5f: an ALO rejection raised during on_trade blocks one EXTRA bbo -------
s10c = sim(latency_ns=L)
s10c.on_bbo(0, 100.0, 10.0, 102.0, 10.0)  # place bid@100, active @100ms
s10c._bid_px, s10c._ask_px = 97.0, 99.0  # book moved; no bbo delivered yet
s10c.on_trade(150 * MS, -1, 98.0, 1.0)  # transitions run here -> ALO reject
rej_on_trade = s10c.alo_rejections
s10c.on_bbo(160 * MS, 97.0, 10.0, 99.0, 10.0)  # first bbo after: places or not?
check(
    "5f a trade-triggered ALO rejection does NOT silently skip an extra quote",
    rej_on_trade == 1 and s10c._orders["bid"] is not None,
    f"rejected_on_trade={rej_on_trade} order_after_next_bbo={s10c._orders['bid']}",
)

# ------------------------------------------------ 6. always-last fill rules --
s11 = sim(latency_ns=0)
s11.on_bbo(0, 100.0, 50.0, 102.0, 50.0)
s11.on_bbo(1 * MS, 100.0, 50.0, 102.0, 50.0)
s11.on_trade(2 * MS, -1, 100.0, 10.0)
check(
    "6a at-price print smaller than the visible touch does NOT fill",
    s11.fills == 0,
    f"fills={s11.fills}",
)
s11.on_trade(3 * MS, -1, 100.0, 50.0)
check(
    "6b at-price print >= visible touch DOES fill (sweep)",
    s11.fills == 1 and s11.fills_sweep == 1,
    f"fills={s11.fills} sweep={s11.fills_sweep}",
)

s12 = sim(latency_ns=0)
s12.on_bbo(0, 100.0, 50.0, 102.0, 50.0)
s12.on_bbo(1 * MS, 100.0, 50.0, 102.0, 50.0)
s12.on_trade(2 * MS, -1, 99.0, 1.0)
check(
    "6c through-print fills the FULL order size irrespective of print size",
    s12.fills == 1 and s12.trade_records[0][2] == 100.0,
    f"filled={s12.trade_records[0][2] if s12.trade_records else None} print_sz=1.0",
)

s13 = sim(latency_ns=0)
s13.on_bbo(0, 100.0, 50.0, 102.0, 50.0)
s13.on_bbo(1 * MS, 100.0, 50.0, 102.0, 50.0)
s13.on_trade(2 * MS, -1, 100.0, 60.0)
check(
    "6d sweep credits min(print, order), NOT (print - queue_ahead)",
    s13.trade_records[0][2] == 60.0,
    f"credited={s13.trade_records[0][2]} strict_always_last={60.0 - 50.0}",
)

# 6e: 'visible' is read from the CURRENT touch even when our order is stale
s14 = sim(latency_ns=0)
s14.on_bbo(0, 100.0, 50.0, 102.0, 50.0)  # ask order placed at 102
s14.on_bbo(1 * MS, 100.0, 50.0, 102.0, 50.0)  # alo checked
s14.on_bbo(2 * MS, 99.0, 1.0, 101.0, 1.0)  # touch moved; our ask is stale at 102
stale = s14._orders["ask"]
s14.on_trade(3 * MS, +1, 102.0, 2.0)  # 2 lots at our stale price
check(
    "6e sweep queue-ahead is read from the CURRENT touch, not our own level",
    stale is not None and stale.price == 102.0 and s14.fills == 1,
    f"order_px={stale.price if stale else None} visible_used={s14._ask_sz} fills={s14.fills}",
)

# ------------------------------- 7. what does the known-answer gate execute? --
tracer = _trace.Trace(count=1, trace=0)


def _generous_workload() -> None:
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
    g.on_funding(4 * MS, 0.0001, 102.0)
    g.summary()


tracer.runfunc(_generous_workload)
hit = {ln for (fname, ln) in tracer.results().counts if fname.endswith("fill_replay.py")}

targets = [
    ("_process_transitions", fr.BoundedQuoteSim._process_transitions),
    ("_crossing_fills", fr.BoundedQuoteSim._crossing_fills),
    ("_cancel_stale", fr.BoundedQuoteSim._cancel_stale),
    ("_place_wanted", fr.BoundedQuoteSim._place_wanted),
    ("_target_price", fr.BoundedQuoteSim._target_price),
    ("_side_capped", fr.BoundedQuoteSim._side_capped),
    ("_fill", fr.BoundedQuoteSim._fill),
    ("_generous_fill", fr.BoundedQuoteSim._generous_fill),
    ("_settle", fr.BoundedQuoteSim._settle),
]
print("\n--- fill_replay.py lines executed by the GENEROUS (known-answer) path ---")
untouched = []
for name, fn in targets:
    lines, lo = inspect.getsourcelines(fn)
    hi = lo + len(lines) - 1
    n_hit = len([ln for ln in hit if lo <= ln <= hi])
    print(f"  {name:22s} lines {lo:>4}-{hi:<4} executed={n_hit}")
    if n_hit == 0:
        untouched.append(name)
check(
    "7a known-answer (generous) path executes the order machine",
    not untouched,
    f"NEVER EXECUTED by the gate: {untouched}",
)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAILED:", f)
