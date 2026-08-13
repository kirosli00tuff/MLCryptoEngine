# Adversarial code audit — MLCryptoEngine

**Audited commit:** `ed786ce` (main, 2026-08-11 23:16:42 -0700)
**Method:** scratch clone at `/tmp/.../scratchpad/audit/MLCryptoEngine`, symlinked
read-only to the live `data/raw` and `data/vendor`. Nothing under
`~/Documents/GitHub/MLCryptoEngine` was written; no systemd unit touched.
**Evidence artefacts:** committed under `audit/` — `audit/probe_fill_replay.py`,
`audit/probe2.py`, `audit/replay_variants.py`, `audit/census_ci.py` and their outputs
`audit/variants_base.json`, `audit/variants_p5.json`, `audit/variants_m5.json`,
`audit/census_ci.json`. Run the probes from the repo root with the project venv;
the two replay scripts need `data/raw` and `data/vendor` present. The
scripts were `ruff format`ted before committing (behaviour unchanged: both
probe suites re-run to the same 10/2 and 18/8 pass/fail counts). Note
`audit/probe_fill_replay.py` probes 1a–2a encode a wrong *expectation* of mine —
a sweep credits `min(print, order)`, not the full order — corrected in
`audit/probe2.py`; the shipped code was right and I was not.

Every finding is labelled **[VERIFIED]** — a defect reproduced by executing
code — or **[STATIC]** — read from source, not executed. §B lists verified
negatives: things the brief asked me to suspect that were tested and came back
correct. A clean result on a targeted check is evidence too, and three of the
brief's specific suspicions were wrong.

---

## A. Findings, ranked by severity

> **Ranking note.** A13 was found last — the feed-ordering replays finished
> after the rest of this report was drafted — but ranks **second** by severity.
> Numbering follows discovery order; read **A1, A13, then A2 onward**.

### A1 — HIGH — The D.1d known-answer gate executes none of the code that produced the D.1d result **[VERIFIED]**

**Where:** `research/microstructure/fill_replay.py:129`
(`if self.fill_model != "generous":`), `:144-145`
(`if self.fill_model == "generous": ... return`); gate wired at
`research/microstructure/d1d.py:78`; miniature at `tests/test_d1d.py:114`.

**What is wrong.** The stage's stated warrant for its arithmetic is: *"Same
events, an independently implemented ledger — the accounting is trusted, so the
tightened numbers below are differences in fill model, not arithmetic"*
(report.md §D.1d.1). The claim is true and load-bearing on nothing. In
`generous` mode `on_bbo` short-circuits at line 129 and `on_trade` returns at
line 145, so the order machine is bypassed entirely. Traced with `trace.Trace`
(`audit/probe2.py` §7):

```
_process_transitions   lines 175-191  executed=[]      <- ALO rejection
_crossing_fills        lines 193-201  executed=[]      <- stale-quote fills
_cancel_stale          lines 203-212  executed=[]      <- cancel latency
_place_wanted          lines 214-232  executed=[]      <- quote placement
_target_price          lines 234-238  executed=[]
_fill                  lines 246-280  executed=[]      <- fill booking + attribution
```

106 consecutive lines — every line that distinguishes D.1d from D.1c — execute
zero times under the gate. What it does cover is `_generous_fill` (282-292) and
`_settle` (294-306): the ledger D.1d *inherited*, not the model it added.

The agreement is also far stronger than reported, which is itself the tell. The
report claims reproduction "to the printed digit (registered tolerance ±0.10)".
Measured from `logs/`, it agrees to 15 significant figures:

| | D.1c `InventorySim` cap 2.5×Q | D.1d `known_answer` |
|---|---|---|
| PUMP net_bps | `+1.232843` | `+1.232843` |
| MERL net_bps | `+6.674559` | `+6.674559` |
| PUMP fills / notional | 286,378 / `41506371.05314963` | identical |

Two independent implementations do not agree bit-for-bit across 286,378
floating-point accumulations. They agree because `BoundedQuoteSim._settle` is a
statement-by-statement transliteration of `InventorySim.on_trade` — same
operations, same order, same rounding. The gate is therefore a valid check that
the transliteration is faithful, and nothing more. It is not tautological (the
code genuinely is duplicated) but it is *orthogonal* to the risk it is offered
against.

Both drivers additionally share `AGGRESSOR_SIGN` (`census.py:29`) and
`SZ_DECIMALS` / `load_funding_archive` (`d1c.py:38`, imported by `d1d.py:38`),
so a defect in aggressor-sign convention or funding-hour keying would pass the
gate silently on both sides.

**Which result it changes if true.** None directly — this is a missing control,
not a wrong number. Its significance is that it removes the only stated reason
to trust `−4.75 / −4.23`. The entire closure is covered by `tests/test_d1d.py`:
12 synthetic-event assertions written by the same author in the same 30-minute
session that produced the result (`git`: registration `6a17edf` 22:46:47,
results `ed786ce` 23:16:42).

---

### A2 — MEDIUM — §2b's "delete every crossing fill" counterfactual is arithmetic on a path-dependent ledger, and mixes normalising denominators **[VERIFIED]**

**Where:** `report.md` §D.1d.2b, the paragraph beginning *"The counterfactual
that matters"*; copied verbatim into the permanent `HYPOTHESES.md` H6 record.

**What is wrong.** The report defends the closure against its most pessimistic
rule by subtracting the crossing rows arithmetically:

> PUMP: edge −0.24 bps, less 1.5 fee, plus −2.24 inventory = **−3.98 bps**.
> MERL: −1.09 − 1.5 + 0.02 = **−2.57 bps**.

Two problems. First, `−0.24` is recomputed on the *reduced* notional ($10.74M,
sweep+through only) while `−2.24` inventory and `1.50` fees are carried over
unchanged from the *full* notional ($15.41M) — mixed bases. Second and more
fundamentally, the ledger is path dependent: removing fills changes the
position path, which changes the inventory term, which changes net. Rows cannot
be subtracted from it.

I ran the actual counterfactual — subclassing `BoundedQuoteSim` with
`_crossing_fills` as a no-op, replaying all 8 days (`audit/replay_variants.py`):

| | report §2b (arithmetic) | true re-run | Δ |
|---|---|---|---|
| PUMP no-crossing net_bps | **−3.98** | **−4.3519** | −0.37 |
| MERL no-crossing net_bps | **−2.57** | **−2.1346** | +0.44 |
| PUMP fills | 23,333 implied by subtraction | 24,394 actual | +1,061 |
| MERL fills | 3,293 implied | 3,370 actual | +77 |

The fill counts show why subtraction cannot work: orders that would have been
crossed instead survive and are later filled by the sweep/through rules, so the
counterfactual is not a subset of the base run.

**Which result it changes.** Not the verdict — both instruments remain
negative, which is exactly what §2b set out to show, and my PUMP figure is
*worse* than published. It changes two numbers that appear in both `report.md`
and the permanent H6 register (−3.98 → −4.35, −2.57 → −2.13) and discredits the
method that produced them. The error is not directionally biased toward the
conclusion — anti-conservative on PUMP, conservative on MERL — consistent with
sloppiness rather than motivated reasoning.

---

### A3 — MEDIUM — Census confidence intervals assume independence; no clustering correction exists anywhere in the repository **[VERIFIED]**

**Where:** `research/microstructure/registered.py:149-153`

```python
var = sum((x - mean) ** 2 for x in nets) / (n - 1)
se = math.sqrt(var / n)  # <- IID
crit = float(student_t.ppf(0.5 + CONFIDENCE / 2, n - 1))
lower = mean - crit * se
p_one_sided = float(student_t.sf(mean / se, n - 1)) if se > 0 else 1.0
```

**What is wrong.** `se = sqrt(var/n)` is the textbook IID standard error. The
rows are `spread − adverse − 3.0` per aggressor print, where `spread` is the
prevailing touch spread (persistent across bursts) and `adverse` is a forward
mid move over 1/5/60 s. At 5 s and 60 s, consecutive trades have overlapping
forward windows — textbook overlapping observations.
`grep -rniE "newey|hac|bootstrap|autocorr|cluster|effective_n"` over the whole
tree returns no implementation.

The scaling check the brief asked for is decisive. Under independent sampling,
`halfwidth·√n/sd` equals the critical value for every instrument. Measured
across all ten:

```
ARB 1.9600  DOT 1.9600  GMX 1.9601  HYPE 1.9600  LINK 1.9600
MERL 1.9601 NOT 1.9607  PUMP 1.9600 SOL 1.9600   TNSR 1.9604
```

Identical to four decimals. The scaling is perfectly consistent with
independent sampling — **that is the defect, not a reassurance.** There is no
instrument where anything was adjusted.

I re-ran the census through the project's own `_ReplayFeed` and
`_horizon_stats` (reproducing C.27 exactly: PUMP `+4.300` / lower `+4.268`,
MERL `+6.450`, GMX `+0.404`, HYPE `−2.105`, SOL `−2.605`) and added the three
missing corrections:

| coin | n | mean | half-width IID | Newey–West | day-clustered (7) | NW/IID | day/IID |
|---|---|---|---|---|---|---|---|
| PUMP | 499,912 | +4.300 | 0.0327 | 0.0665 | 0.7069 | **2.0×** | **17.3×** |
| MERL | 25,348 | +6.450 | 0.3807 | 0.5301 | 4.7254 | 1.4× | 9.9× |
| GMX | 25,838 | +0.404 | 0.1164 | 0.1769 | 0.4740 | 1.5× | 3.3× |
| SOL | 378,769 | −2.605 | 0.0194 | 0.0698 | 0.1539 | **3.6×** | 6.4× |
| HYPE | 1,150,493 | −2.105 | 0.0072 | 0.0204 | 0.2533 | 2.8× | **28.1×** |

PUMP's reported ±0.03 bps is really ±0.07 under HAC and ±0.71 under day
clustering. The stated precision is overstated by roughly an order of
magnitude.

**Which result it changes.** The stated precision of every C.27 number, and one
membership decision: **GMX flips**, from `ci95_lower = +0.288` (survivor) to
`−0.070` day-clustered (block bootstrap `+0.101`, straddling zero). GMX was one
of C.27's three survivors. PUMP and MERL — the two carried into D.1c/D.1d —
survive every correction (PUMP lower bound `+3.593` day-clustered, `+4.162`
bootstrap; MERL `+1.725` and `+5.123`). The closure chain is therefore not
affected, but the p-values fed to Benjamini–Hochberg at `registered.py:227`
come from the same understated `se` and are correspondingly anti-conservative.

---

### A4 — MEDIUM — The always-last sweep rule reads queue-ahead from the *current touch*, not from the level the order rests on **[VERIFIED]**

**Where:** `research/microstructure/fill_replay.py:162,165`

```python
visible = self._ask_sz if side == "ask" else self._bid_sz
...
elif at_price and sz >= visible > 0.0:
    self._fill(ts_ns, side, order, min(sz, order.size), "sweep")
```

**What is wrong.** `_ask_sz` / `_bid_sz` are the sizes at the *latest* bbo
touch. The order rests at `order.price`, which after any touch move is a
different level. The sweep test — "did this print exhaust the queue ahead of
us?" — therefore compares the print size against the depth at some *other*
price. Reproduced (`audit/probe2.py` §6e): an ask resting at 102 with **500 lots
ahead of it** is swept by a **2-lot** print, because once the touch moved to
99/101 the code read `visible = 1.0` from the new touch.

Two compounding generosities in the same rule, both confirmed:
- `audit/probe2.py` 6d — the sweep credits `min(print, order_size)`, not the strict
  always-last `print − queue_ahead`: a 60-lot print with 50 ahead fills 60, not 10.
- `audit/probe_fill_replay.py` 6c — a `through` print fills the full order regardless
  of print size. **This one is correct**: a print strictly through a price
  implies every resting order at and better than that price cleared.

**Which result it changes.** `fills_sweep` and the `sweep` row of the §2b
attribution table (PUMP 20.1% of notional at +1.23 bps; MERL 9.5% at +1.21).
Both errors admit *more* sweep fills at *favourable* prices, so they bias
D.1d's net **upward** — correcting them makes the closure stronger, not weaker.
It matters because the report leans on that row as the honest-passive
benchmark ("the one rule where we are genuinely the passive party earns its
half-spread"), and that row is measured against a mismatched queue.

---

### A5 — LOW/MEDIUM — An ALO rejection raised during a trade event suppresses two quote updates, not the one the docstring claims **[VERIFIED]**

**Where:** `research/microstructure/fill_replay.py:105-107` (`_rejected_this_update`),
`:191` (set), `:134-135` (cleared at the end of `on_bbo` only), reached from
`on_trade` via `:149`.

**What is wrong.** The module docstring (`:18-19`) states a rejected order is
*"rejected, counted, and retried at the next bbo update"*. `_process_transitions`
is also called from `on_trade` (line 149); a rejection there sets the flag, but
the flag is cleared only in `on_bbo` **after** `_place_wanted` has already been
skipped. Natural repro, no state poking (`audit/probe2.py` §5f):

```
5f-i   order not live at 50 ms, no ALO check yet          PASS  alo=0
5f-ii  ALO rejection fires on a TRADE event               PASS  alo=1
5f-iii bid re-quoted on the next bbo (docstring claim)    FAIL  order=None
5f-iv  ...it actually takes a SECOND bbo                  PASS  order placed
```

**Which result it changes.** Bounded and small: at most `alo_rejections` extra
skipped quotes — 1,454 of 176,568 placements on PUMP (0.82%), 576 of 305,335 on
MERL (0.19%), direction toward fewer fills. It cannot move `−4.75` materially,
but the ALO machinery does not do what the registered policy says it does.

---

### A6 — LOW/MEDIUM — A one-sided registered bar is judged with a two-sided critical value **[STATIC]**

**Where:** `research/microstructure/registered.py:151-153`

The registered bar is *"95% CI lower bound > 0"* and the p-value on the next
line is explicitly `p_one_sided`. But `student_t.ppf(0.5 + 0.95/2, n-1)` = 1.96
— the two-sided 95% value; a one-sided 95% bound needs 1.645. Confirmed
numerically by the `halfwidth·√n/sd = 1.9600` result in §A3.

**Which result it changes.** Nothing, in the safe direction — the bar is ~19%
harder to clear than registered, so nothing passed that should have failed.
Recorded because the interval and the p-value beside it now answer different
questions, and a future stage reusing `_horizon_stats` for a symmetric test
inherits the mismatch. Given A3, this conservatism is swamped many times over
by the anti-conservatism of the IID assumption.

---

### A7 — LOW/MEDIUM — Benjamini–Hochberg corrects 10 instruments out of a 177-perp screen **[STATIC, matches disclosure]**

**Where:** `research/microstructure/registered.py:325` (population is
`THIN_COINS`, 10 symbols), `:223-230` (`multipletests` over `testable ⊆ 10`),
`:264` (`expected_false_positives = BH_Q * len(survivors)`).

The brief asked whether the code does what D.1c said. **It does**: the
correction runs across at most ten p-values, and the screen that chose those
ten was spread-motivated.

**Which result it changes.** Nothing not already disclosed — D.1c §4 and
HYPOTHESES.md H6 both state "BH corrected the 10 tested, not the 177 screened"
and demote the survivors to "screened positives". Recorded because it is a real
multiplicity gap the *code* confirms rather than merely the prose, and because
§A3 shows the p-values entering that correction are themselves understated.

---

### A8 — LOW — Capacity tier divides by 7 calendar days, ignoring the 5.75 h recorder hole **[STATIC]**

**Where:** `research/microstructure/registered.py:201-202`

```python
median_usd = sorted(inst.usd_by_day[d] for d in days)[len(days) // 2] if days else 0.0
trades_per_day = inst.trades / max(1.0, (SCORED_END_NS - SCORED_START_NS) / NS_PER_DAY)
```

The denominator is 7.0 calendar days. Coverage was 96.4% (a ~5.75 h hole on
08-04, per C.27 §1), so the true recorded span is 6.76 days. `median_daily_usd`
has the same problem: the holed day's USD total competes against whole-day
totals.

**Which result it changes.** `trades_per_day` understated ~3.5% for every
instrument; the 08-04 daily-USD figure understated by up to 24%. Both push
*against* clearing `capacity_tier_met` (≥150 trades/day, ≥$100k median daily
USD), so the effect is conservative. It could in principle have demoted a
`survivor_tradeable_capacity` to `positive_but_rare`; it did not, since PUMP and
MERL clear the floor by ~300×. Separately, `sorted(...)[len(days) // 2]` takes
the upper element rather than averaging the middle two on an even day count —
immaterial at this margin.

---

### A9 — LOW — Adverse-selection queues are never drained at the window edge; late trades are silently dropped **[STATIC]**

**Where:** `research/microstructure/registered.py:103-142`, `:293`

`_ReplayFeed.run_day` skips out-of-window records with `continue`, so no quote
after `SCORED_END_NS` is ever fed. `RegisteredInstrument` resolves armed trades
only inside `on_quote`, and nothing drains `_queues` at close, so trades armed
within one horizon of the window end never reach `rows` and vanish from `n`.

`d1c.py` handles exactly this case correctly and says so (`:18-20`, *"Quotes
are consumed for a 900 s tail past the window end so trades armed near the
close still resolve"*, `RESOLUTION_TAIL_NS` at `:73`). The registered census,
which produced the headline, has no such tail.

**Which result it changes.** Bounded by the last 60 s of a 7-day window
(~0.01% of trades) — immaterial to any published number. Listed because the
failure mode is invisible: a silent drop, not a raise. A second instance of the
same class: a deadline falling inside a quote gap resolves against
`self._last_mid` from *before* the gap (`:113-114`), so the adverse move is
measured over a shorter effective horizon than nominal, biasing `adverse`
toward zero and `net` upward. Negligible at the observed 123–330 ms bbo
cadence; not negligible on any feed with real quote gaps.

---

### A10 — LOW — The Hyperliquid maker fee every H6 number rests on is hardcoded in three places with no source and no date **[STATIC]**

**Where:** `research/microstructure/fill_replay.py:38` (`MAKER_FEE_BPS = 1.5`),
`research/microstructure/inventory.py:28` (`MAKER_FEE_BPS = 1.5`),
`research/microstructure/registered.py:57` (`ROUND_TRIP_BPS = 3.0`).

`config/venues.yaml` carries fully sourced, dated fee ladders for Kraken (10
tiers, a retrieval date, three corroborating URLs, and an explicit correction
note about a prior error — ADR-055) and Coinbase (9 tiers). Hyperliquid has a
`fee_tiers` block, but the microstructure code never reads it: the three
constants above are literals — duplicated, unsourced, undated, unconnected to
the config layer. `ROUND_TRIP_BPS = 3.0` and `MAKER_FEE_BPS = 1.5` are
independently maintained restatements of one fact; nothing enforces
`ROUND_TRIP == 2 × MAKER`.

**Which result it changes.** Every net in C.27, D.1c and D.1d scales directly
with it. Against PUMP's `+4.30` round-trip census net, a one-tier error
(Hyperliquid's maker schedule has a 0-bps rung) is larger than the entire
measured edge. The project's own rule is *"measured beats documented"*, and its
own precedent is a Kraken schedule that was wrong for a week. Same exposure,
unreconciled.

---

### A11 — LOW — The reported "fall" mixes per-round-trip and per-leg units in adjacent sentences **[STATIC]**

**Where:** `report.md` §D.1d.5 — *"the census and D.1a measured per-fill
accounting … (+2.15 / +5.42 at the pessimistic end)"*, placed beside *"The
truth lies between D.1c's generous +1.23 and this bounded −4.75"*.

`HYPOTHESES.md` H6 states plainly that the D.1a figure is **"+2.15 bps per
round trip"**. D.1d's `−4.75` and `+1.23` are per filled notional **per leg**
(`fill_replay.py:339-340`: `bps(usd) = usd / filled_notional_usd * 1e4`, with
notional accumulated one leg at a time and `fees_bps = 1.50`, half of
`ROUND_TRIP_BPS`). Per round trip the bounded result is **−9.50**, not −4.75.

**Which result it changes.** No sign, no verdict. It halves the apparent size of
the fall in the one paragraph a reader is most likely to quote. To the
project's credit, units are handled correctly everywhere else I checked,
including the H6 register itself.

---

### A12 — LOW — `None` metrics are coerced to `0.0` on the way into the schema **[STATIC]**

**Where:** `research/microstructure/d1d.py:240,243-244`

```python
expectancy_bps_net = (float(summary["net_bps"] or 0.0),)
expected_bps = (float(summary["expected_edge_bps"] or 0.0),)
realized_bps = (float(summary["edge_bps"] or 0.0),)
```

`summary()` returns `None` for these when `filled_notional_usd == 0`
(`fill_replay.py:340`). A variant producing no fills would emit a
`PerformanceReport` reading `expectancy 0.0` — a metric computed on an empty
set and published as a value, exactly the failure mode the brief names. Not
triggered by the shipped run (every variant filled), and it sits against the
project's own dashboard rule that empty states are the default, not a fallback.

---

### A13 — MEDIUM/HIGH — The net closure is robust to feed ordering, but the *published mechanism* is not: PUMP's realized edge flips sign under a 5 ms shift **[VERIFIED]**

**Where:** `research/microstructure/fill_replay.py:121-127` vs `:154`
(the marking instant: `_last_mid` is advanced to the new mid *before*
`_crossing_fills` runs on a bbo, but is the *pre-print* mid inside `on_trade`);
consumed by `report.md` §D.1d.2 and published as
`SlippageStats(expected_bps=2.74, realized_bps=−1.01)` in
`data/processed/reports/d1d_PUMP_base.json` via `d1d.py:242-245`.

**What is wrong.** `trades` and `bbo` arrive on two independent Hyperliquid
subscriptions and are ordered by the recorder's local `recv_ns`. Which one lands
first decides whether a given market event books as `through` (marked at the
*pre-move* mid → favourable edge) or `crossing` (marked at the *post-move* mid →
adverse edge). Together those two rules are **79.7%** of PUMP's filled notional
and **91.5%** of MERL's. I re-ran the base variant with every `trades` record's
`recv_ns` shifted ±5 ms relative to `bbo` — a perturbation ~25–65× smaller than
the feed's own 123–330 ms bbo cadence:

| PUMP | net_bps | edge_bps | inventory_bps | fills | filled notional | crossing % |
|---|---|---|---|---|---|---|
| trades −5 ms | **−5.1295** | **+0.4464** | −4.0758 | 36,659 | $11.79M | 32.3% |
| **base (published)** | **−4.7503** | **−1.0115** | −2.2387 | 32,018 | $15.41M | 30.3% |
| trades +5 ms | −4.7578 | −1.0077 | −2.2500 | 31,973 | $15.39M | 30.9% |

| MERL | net_bps | edge_bps | inventory_bps | fills |
|---|---|---|---|---|
| trades −5 ms | **−5.0418** | −1.4294 | −2.1119 | 3,807 |
| **base (published)** | **−4.2314** | **−2.7450** | +0.0159 | 4,270 |
| trades +5 ms | −4.2880 | −2.7721 | −0.0138 | 4,264 |

Two distinct conclusions, and they point opposite ways:

1. **The closure is robust.** Net is negative in all three orderings on both
   instruments (PUMP −4.75 / −4.76 / −5.13; MERL −4.23 / −4.29 / −5.04), and the
   **published base is the *least* negative of the three**. No plausible
   re-ordering of the feed makes H6 survive. This is the strongest single piece
   of evidence *for* the D.1d result found in this audit, and it did not
   previously exist.

2. **The stated mechanism is an artefact of the marking instant.** PUMP's
   realized edge swings from **−1.01 to +0.45 — a sign flip** — while inventory
   moves from −2.24 to −4.08 to absorb it. That is not a coincidence: the
   invariant is `MTM = edge + inventory` (`fill_replay.py:332-336`), so moving
   the instant at which a fill is marked merely relocates P&L between the two
   buckets. Shifting trades earlier marks fills at the pre-move mid (edge looks
   good) and leaves the position to ride the move (inventory eats it).

**Which result it changes.** Not the verdict — see (1). It changes the sentence
the stage is actually *about*. `report.md` §D.1d.2 states: *"The mechanism,
visible in the slippage line: a last-in-queue maker's fills are adversely
selected at the fill instant … the fills that actually reach it deliver −1.0 to
−2.7 bps of realized edge"*, and §4 calls `+2.74 vs −1.01` *"the stage's finding
in one pair of numbers"*. Under a 5 ms shift that pair becomes **+2.74 vs
+0.45**, and the loss is inventory drift, not fill-instant adverse selection.
The same figure is frozen into `HYPOTHESES.md` H6 (*"expected half-spread at
placement +2.7 bps vs realized edge −1.0 to −2.7 bps"*) and into a shipped
`PerformanceReport` consumed by the desktop dashboard.

The honest statement the evidence supports is: *the capture does not survive an
order-lifecycle fill model* — which is the closure, and it holds. The
attribution of that loss specifically to adverse selection **at the fill
instant**, rather than to inventory drift, is not separable at this feed's
resolution and should not have been asserted as measured.

---

## B. Verified negatives — targeted checks that came back clean

| Suspicion under test | Result | Evidence |
|---|---|---|
| **Sign of realized edge inverted** | **Correct.** Bid fill → `edge = +(mid − bid)·size`, long; ask fill → `+(ask − mid)·size`, short. Crossing fill on the stale side is negative, as intended. | `audit/probe2.py` 1a–1f |
| **Fee per side vs per round trip** | **Correct and consistent.** 1.5 bps on each leg's own notional; `fees_bps` normalises to exactly 1.50 per leg; `ROUND_TRIP_BPS = 3.0` used only in the census's round-trip framing. | probes 1c, 2b |
| **Latency applied as a single offset** | **No — both directions.** Placement inactive until `t+L`; cancel effective at `t+L`; order stays fillable at its stale price through the cancel-in-flight window; replacement takes a further `L`. | probes 4a–4f |
| **Cancel path accidentally instantaneous** | **No.** `cancel_dead_ns == issue + latency_ns`, verified at 220 ms for `L = 100 ms`; replacement `active_ns = 330 ms`. | probes 4d, 4f |
| **ALO fires on a broader condition than claimed** | **No.** Fires only on a genuine cross at arrival; not on a touch move; not on a non-crossing order; one-shot, so a later cross becomes a fill rather than a rejection. Measured rates 0.19–1.75% are not starving the strategy. | probes 5a–5d |
| **Decomposition identity does not sum** | **It sums.** In code (`net == edge + inv + funding − fees`; `MTM == edge + inv`) and by hand for PUMP: −$1,558.94 edge − $3,450.00 inventory − $2,311.71 fees − $0.02 funding = **−$7,320.67** vs reported −$7,321; and −1.0115 − 2.2387 − 0.0001 − 1.5000 = **−4.7503** vs reported −4.75. Per-reason USD sums to total edge to 13 decimals. | probes 3a–3b; `logs/d1d_summary.json` |
| **Results depend on state left by an earlier run** | **No.** Independent replay from raw reproduced the committed summary bit-exactly: 28,658,883 records; PUMP net −4.7503 / edge −1.0115 / inv −2.2387 / 32,018 fills / $15,411,429; MERL −4.2314 / 4,270 fills. Census likewise reproduced C.27. | `audit/variants_base.json`, `audit/census_ci.json` |
| **Fill classification is an artefact of WebSocket delivery order** | **Split verdict — the only suspicion that partly landed.** The *net* closure is robust across ±5 ms; the *published edge/inventory split* is not. Promoted to **A13**. | `audit/variants_p5.json`, `audit/variants_m5.json` |
| **Pre-registration bars moved after the fact** | **No.** Every `docs: pre-register` commit precedes its `feat:` results commit. `git diff 6a17edf ed786ce -- report.md` shows only additions; no registered threshold edited. `git diff 287fc10 HEAD -- registered.py` filtered to constants is **empty** — no bar ever changed after the code landed. | git |
| **Census ran before its window closed** | **No.** `SCORED_END_NS` = 2026-08-11T00:00Z; results commit `deb041b` is 2026-08-10 23:56 **−0700** = 2026-08-11 06:56 UTC, ~7 h after close. `assert_scored_window_closed` would otherwise have raised. | git; `registered.py:275` |
| **Union-before-summing violated a fifth time** | **No.** `data/databento/session.py:70` calls `merge_windows(clipped)` with an explicit comment about the Friday/Sunday overlap; `open_ns` (`:76`) sums the *merged* output. `research/stream/reader.py:183` also unions. | grep + read |
| **Local receive and venue clocks mixed in one ordering** | **No.** `exchange_ns` is persisted but explicitly never ordered on (`parquet_writer.py:40,176`; `census.py:8-11`). The single use of a venue `time` field is `d1c.py:84`, keying the REST funding archive to hour boundaries — a different clock for a different purpose, correctly. `SCORED_START_NS` is exactly hour-aligned, so that keying cannot silently miss. | grep + read |
| **Adverse-selection primitive leaks the future** | **No.** `adverse.py:69-72` resolves a deadline against the last mid at or before it, never a later one; `trades_without_mid` is counted, not silently lost (`:88`); `on_trade` raises on a sign outside ±1 (`:84`). | read |

### B.1 — The feed-interleaving test, run

This was the check I intended to *nominate* as decisive, so I ran it instead.
It came back split, and the half that failed is written up as **A13**; the half
that passed is the strongest evidence for the closure in this audit:

**Net is negative under every ordering tested, and the published base is the
least negative of the three** — PUMP −5.13 / **−4.75** / −4.76 and MERL −5.04 /
**−4.23** / −4.29 at trades −5 ms / base / +5 ms. No plausible re-ordering of
the two subscriptions rescues H6. See **A13** for the full tables and for the
edge/inventory decomposition, which is *not* stable.

---

## C. Priority-three sweep: the nine other closures

I found no closure whose *cause* was a defect. The specific failure modes the
brief named were searched for; where present they appear above:

- **metric on an empty/near-empty set reported as a value** — one latent
  instance (A12), not triggered by any shipped run. `_horizon_stats` guards
  `n > 2`, and `instrument_report` returns `too_thin_by_prior_declaration`
  below the 300-trade floor rather than computing.
- **inverted operator on a threshold** — none found. The comparison chain in
  `assemble` (`:238-249`) is correct against the registered outcome map; the
  one-sided/two-sided mismatch (A6) is conservative.
- **join silently dropping rows** — A9 is the nearest instance, ~0.01%.
- **all-NaN feature passing through as zero** — none found in the
  microstructure path; every `float()` conversion is wrapped in an explicit
  `except (KeyError, TypeError, ValueError)`.
- **swallowed failure** — parse-level `continue`/`return` handlers in
  `census.py`, `d1c.py`, `d1d.py`, `registered.py` discard malformed messages
  without counting them, except `CensusResult.unparseable` (`census.py:107`)
  which does count. `d1d.py:137-139` and `:149-150` discard silently. Given
  28.7M records reproduce bit-exactly, discarded volume is evidently stable,
  but it is unmeasured.

**Scope limit, stated rather than glossed:** the Phase-B and detection-track
hypotheses (H1, H2, H4, H5, H8–H11) could not be independently re-derived
within this audit — their inputs are not all present in the clone. I read their
register entries; each cites a measured number and a reopening condition. They
are **unaudited**, not clean.

---

## D. Priority-four: what the gates actually cover

The leakage suites carrying the planted-future canary and prefix invariance are
`tests/test_leakage.py`, `test_deep.py`, `test_labels.py`, `test_medium.py`,
`test_research_stream.py`, `test_detection_*.py`. Their imports reach
`research.deep`, `research.labels`, `research.features`, `research.medium`,
`research.detection`, `research.validation.purged_kfold`, `research.pipeline`,
`research.stream` — the Phase B research pipeline and the detection pipeline,
exactly as the brief suspected.

Of the microstructure modules that produced the headline numbers:

| module | covered by |
|---|---|
| `registered.py` (the census) | `test_registered_census.py` only |
| `census.py` | `test_registered_census.py` only |
| `d1c.py`, `inventory.py`, `tick.py`, `horizons.py` | `test_d1c.py` only |
| `d1d.py`, `fill_replay.py` | `test_d1d.py` only |
| `spread.py`, `adverse.py` | **no test file imports them** |

**No leakage suite, canary, or prefix-invariance test reaches any of them.** The
census / D.1c / D.1d path is covered solely by its own three stage-specific
files, and `spread.py` / `adverse.py` — the primitives underneath C.9 and C.27
— are reached only transitively through `run_census`, with no direct test.

The real known-answer gates are `registered.known_answer` (reproduces C.9's
BTC/ETH nets — genuine and useful, and it does exercise the same accumulators
the scored run uses) and D.1d's generous-mode gate (A1 — covers nothing that
matters).

---

## E. Verdict

**Is any closure in this repository more likely a defect than a market fact?**

**No.** And I tried hard to make one be.

Every mechanism the brief flagged as a plausible inversion was tested against
running code and came back correct: the sign convention, the per-leg fee, the
bidirectional latency, the non-instantaneous cancel, the ALO condition and its
rate, and the decomposition identity — which sums both in code and by hand. The
whole 28.7M-record replay reproduces **bit-exactly** from immutable raw data,
as does the census. Pre-registration is genuinely clean: every bar predates its
result and no threshold was ever edited. The union-before-summing rule and the
clock-discipline rule are both honored, including in the places most likely to
break them.

The two real coding defects in the fill path (**A4**, **A5**) both bias the
result **upward** — correcting them makes PUMP and MERL more negative, not less.
The census CIs are constructed wrongly (**A3**, 2–17× too narrow), but the two
instruments that fed D.1d survive every clustering correction; only GMX, which
the report had already discounted to ~zero on independent grounds, flips. And
the one structural fragility I could construct a mechanism for — that the
crossing/through split is an artefact of which WebSocket subscription arrived
first, covering ~80–92% of filled notional — **I tested, and the net survives
it**: negative under every ordering, with the published figure the *least*
negative of the three (**A13**).

Two things are *not* earned. First, the epistemic claim the stage makes for
itself: it ran once, and the control it offers — the known-answer gate —
provably executes none of the 106 lines that produced the number (**A1**), while
its defence against its own most pessimistic rule (**A2**) is arithmetic
performed on a path-dependent ledger and gets both published figures wrong. The
result is right; the reasons given for believing it are not the reasons it is
right.

Second, and more substantively: the stage's *explanation*. `−4.75` is a fact.
"Fills are adversely selected **at the fill instant**" is not — that attribution
moves entirely into the inventory term under a 5 ms shift, flipping PUMP's
published realized edge from −1.01 to **+0.45** (**A13**). H6 closes on the
right number for a reason the data cannot separate at this feed's resolution.
That distinction matters for what happens next, because the register's stated
reopening condition (*"order-level book data … that would let fill-instant
adverse selection be measured rather than bounded"*) is scoped to a mechanism
the evidence does not actually pin down.

**The single check that would settle it fastest.**

Correct A4 — track the visible depth at the order's *own* resting price rather
than at the current touch — and re-run the base variant. ~100 seconds, no new
data, no new harness (`audit/replay_variants.py` already subclasses `BoundedQuoteSim`
for exactly this kind of swap).

That check is decisive because, after this audit, A4 is the **only confirmed
defect left inside the code path that produced −4.75**. The other two candidate
explanations for the number have already been tested and cleared here: feed
ordering (A13 — net negative under every ordering) and the census statistics
that selected the instruments (A3 — PUMP and MERL survive HAC, day-clustered
and block-bootstrap intervals). A4 is the one remaining place where the model is
measurably *more generous* than the always-last bound it claims to implement.

If the closure survives its correction — and the direction of the bias predicts
it will become *more* negative — the last unaudited surface on the D.1d number
is closed, and H6 rests on something better than a gate that never ran over it.
If instead net moves toward zero by more than ~1 bp, then the sweep row §2b
leans on is not measuring what it claims, and the attribution table defending
the closure needs rebuilding before H6 stays shut.

**One scope caveat, restated so it is not lost:** this verdict covers H6 and the
census/D.1c/D.1d chain, which I re-derived from raw. The Phase-B and
detection-track closures (H1, H2, H4, H5, H8–H11) are **unaudited** — their
inputs are not all present in the clone. I read their register entries and found
nothing alarming, but I did not run them, and per this report's own labelling
convention that is worth far less.
