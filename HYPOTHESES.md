# Hypothesis register

**Read this before proposing any new strategy hypothesis.**

Seven strategy hypotheses have been tested and closed. `report.md` runs past
2,600 lines across seventeen stage sections, each written for the moment it
landed rather than for someone reading months later. The failure mode this file
exists to prevent is **retrying a settled question because the number that
closed it is buried** — nobody remembers six weeks later that BTC/ETH
cointegration failed at p=0.1169 on survivorship-free data, or that MBT quotes
1.93 bps of touch spread against 5.33 bps of maker cost.

Every entry carries the measured figure that decided it, the sample it rests
on, where the working lives, and — the field that matters most — **what would
reopen it**. That last field distinguishes the two kinds of closure this
project has produced, and confusing them is the expensive mistake:

- **Cost-bound**: a real signal exists but is smaller than the cost of
  capturing it. Reopens at a materially lower fee tier, and a better model
  could matter *if* costs fell.
- **Signal-absent**: there is nothing to capture. **Does not reopen on a better
  model, a better feature set, or lower fees.** Model quality was never the
  constraint.

This file contains no analysis. It records what other stages established.

---

## Register

### H1 — Short-horizon directional prediction on crypto spot

> Microstructure features predict short-horizon mid-price direction on crypto
> spot by enough to cover the cost of trading it.

| | |
|---|---|
| **Status** | **Closed — cost-bound** · 2026-08-03 |
| **Deciding number** | **3.31 bps** gross capture at the 900 s horizon against **80.00 bps** round-trip maker cost. Coinbase BTC-USD. AUC **0.596** — the signal is real and the arithmetic still fails, by 23×. Net EV **−76.69 bps**. **Superseded by C.14 (2026-08-05): that 3.31 bps came from a single day. Across four full days the same measurement ranges −2.44 to +3.05 bps** — a draw from a distribution centred near zero, not a small positive edge. |
| **Sample** | Coinbase and Kraken spot, recorded tick data, single-digit days. Event bars every 50 book updates, 42 features, horizons 100 ms – 900 s. |
| **Limitations** | Days, not regimes. C.14 extended the sample to six validated days (2026-07-30 → 2026-08-04); short-horizon AUC reproduces to within **0.0044**, long-horizon capture does not reproduce at all. Under the project's own research-honesty rule this is pipeline validation, not evidence of a durable edge — a signal fitted on a few days is fitted on those days' volatility regime. |
| **Working** | Phase B research runs, `report.md` "Phase B research run" sections (2026-08-01 → 2026-08-03); baseline row in the Stage C.8 comparison table. |
| **What would reopen it** | A round-trip cost below roughly **3 bps**, i.e. under 1.5 bps per side. On Coinbase that is the 0 bps maker tier requiring **$250M trailing 30-day volume**; on Kraken, the 0 bps maker tier at **$10M**. Neither is reachable at this project's capital. **Reopens on cost, not on modelling** — AUC 0.596 says there is signal there, so a better model is worth building *only after* a venue at that fee level exists. It does not reopen on more data at the same venues.<br><br>**C.14 strengthened this closure in three ways.** (1) **The mechanism is named: AUC is magnitude-blind.** Confidence is *anti*-correlated with realised move size — Spearman **rho = −0.32** (Kraken) and **−0.37** (Coinbase) at 100 ms — so the model is surest exactly where there is least to win. (2) **There is no hidden selection filter.** Top-confidence deciles do capture 2–24× the all-sample mean, but through accuracy rather than magnitude, and the best decile in the study captures **5.00 bps against 80 bps** — missing the economic bar by 16×. (3) **Capacity is not the constraint.** An MLP and a GRU both score *worse* than LightGBM on AUC and on capture, at 900 s and at 1 s, with the leakage suite passing and its planted-future canary firing at AUC 0.9714. Reopening now additionally requires the top-confidence decile to clear a round trip somewhere, which it does not. |

---

### H2 — Transfer of that edge to CME micro futures

> The Phase B microstructure edge survives a move to CME micro futures, where
> per-contract fees are a fraction of crypto spot fees in basis-point terms.

| | |
|---|---|
| **Status** | **Closed — signal-absent** · 2026-08-03 |
| **Deciding number** | **AUC 0.501** at every horizon, and **0.22 bps** gross capture against **5.33 bps** cost. CME MBT (micro bitcoin) via Databento. Best net EV **−5.11 bps**, and EV never crosses zero at any horizon in either cost mode. |
| **Sample** | 224,425,675 events over 989 scheduled-open hours; two validated MBT months (2026-04, 2026-05), mbp-10 depth. Ordering clock `ts_recv`. |
| **Limitations** | Two months of one contract. Excludes roll boundaries, the daily maintenance halt, and observed silences. A single instrument on a single venue. |
| **Working** | `report.md` §"Stage C.8 — does the Phase B edge transfer to CME?" (line 959). |
| **What would reopen it** | **Not a better model and not lower fees.** The cost problem was genuinely solved here — 5.33 bps against crypto spot's 80 — and the signal vanished anyway: 3.31 bps of capture became 0.22, and AUC fell from 0.596 to coin-flip. The one figure clearing rounding noise (+0.215 bps at 900 s) **reversed to −0.785 bps** on a stride-1 control, which also cleared the bar-width confound. Reopens only on evidence of measurable AUC on a *different* instrument or feature class — never on a re-run of the same pipeline against the same contract with a stronger learner.<br><br>**C.14 closed the two obvious escape routes.** (1) **The missing feature class was not the cause.** Cross-venue lead-lag and divergence ranked near the top of Phase B importance and were 100% NaN in C.8; measured where they *can* be computed (Kraken/Coinbase, 67–100% coverage) they are worth **ΔAUC ≤ +0.0044** — immaterial at every horizon. Feature importance measured what the model leaned on, not what it gained. (2) **A stronger learner was tried, once, against a pre-registered bar, and lost.** MLP and GRU both scored below the LightGBM baseline on AUC *and* gross capture at 900 s and 1 s, on the instrument where the pipeline works best. The leakage suite passed with a canary that demonstrably fires (AUC 0.9714 on a planted future column), so the null result is informative rather than merely quiet. |

---

### H3 — Passive spread capture

> Quoting passively and earning the touch spread beats the cost of doing so, on
> at least one reachable instrument.

| | |
|---|---|
| **Status** | **Closed — cost-bound, with a measured tail still open (see H6)** · 2026-08-03 |
| **Deciding number** | **spread − adverse selection − cost**, all in bps: Hyperliquid BTC **−3.05**, Hyperliquid ETH **−2.75**, CME MBT **−4.25**. Not one of **28 surveyed instruments** with a real market has a spread-to-cost ratio above 1.0; the best is **M6A micro AUD at 0.98**, break-even on fees *before* adverse selection is charged. |
| **Sample** | 53.13 quoted hours of Hyperliquid BTC/ETH (2,151,124 bbo updates), plus a 16-contract CME bbo-1s survey on 2026-07-15 costing $0.7763. Adverse selection measured at 100 ms / 1 s / 5 s, aggressor-signed. |
| **Limitations** | Hyperliquid side is two instruments over ~2 days. CME side is a **single day** per contract. Every figure is an **upper bound**, because it credits every quote with a fill that queue position has not earned. |
| **Working** | `report.md` §"Stage C.9 — spread-to-cost survey and adverse selection" (line 1090). ADR-026. |
| **What would reopen it** | A venue paying **maker rebates** (none reachable from British Columbia does), or an instrument whose spread-to-cost ratio exceeds 1.0 *with* adverse selection below the excess. Adverse selection was **positive on every instrument measured** (+0.06 to +0.68 bps), so a favourable ratio alone is not sufficient and must never be reported as if it were. Does not reopen on a better quoting model — nothing here was a modelling question. |

---

### H4 — Cointegration pairs trading

> Cointegrated pairs mean-revert reliably enough that low turnover lets the cost
> per trade amortise into profit.

| | |
|---|---|
| **Status** | **Closed — signal-absent** · 2026-08-04 |
| **Deciding number** | **0 of 180** formation-window pairs surviving Benjamini-Hochberg remain significant out of sample. The holdout window produced **91 raw hits against 77.0 expected by chance** — fewer than noise. **BTC/ETH, the literature's headline pair, scores p = 0.1169**, not cointegrated even before correction, against a published claim of 14.89%/yr at Sharpe 2.23. Deflated Sharpe of the best surviving pair: **0.026**, its per-bar Sharpe of 0.0514 being *less than half* the 0.1058 that screening 1,653 noise pairs would be expected to produce. **Zero executable pairs.** |
| **Sample** | Binance daily bars 2021-08-01 → 2026-07-31, 1,826 bars. Universe **survivorship-free by construction**: 291 symbols listed at 2021-08, top 60 by *that month's* volume, of which **12 (20%) died inside the sample**. 1,653 pairs tested. |
| **Limitations** | Daily bars from a venue this project cannot trade. Contains the 2022 aftermath, the 2024 bull run and the 2025–26 compression. Excludes LUNAUSDT (ticker reuse across a 177,400× splice) and BTTUSDT. |
| **Working** | `report.md` §"Stage C.10 — cointegration pairs trading" (line 1386). ADR-029, ADR-030, ADR-032. |
| **What would reopen it** | **Not lower fees.** Break-even transaction costs were **300–550 bps** against Hyperliquid's 3 bps — a margin of 100–180×, so cost was never remotely the constraint. This is the cleanest demonstration in the project that removing cost does not reveal an edge underneath. Reopens only if (a) a reachable venue offers shorts across a materially broader instrument set — only **5 of 12** subscribed Hyperliquid perps existed at the 2021 sample start, and HYPE and MERL have never listed on Binance at all — **and** (b) relationships persist out of sample, which they did not at any correction level. |

---

### H5 — Funding rate carry

> A delta-neutral long-spot/short-perp position collects funding as mechanical
> income, without needing any prediction to be correct.

| | |
|---|---|
| **Status** | **Closed as currently unattractive — decayed, not disproved** · 2026-08-04 |
| **Deciding number** | Historically real: **8.07% (ETH) and 8.00% (BTC)** net annualised **on deployed capital** after every modelled cost, with 5 of 10 instruments clearing a 4% risk-free rate by 1.6–4.1 points. But **the yield has decayed ~85%**: Binance BTC funding annualised **30.61% in 2021 → 11.92% in 2024 → 5.13% in 2025 → 1.94% in 2026**; ETH 37.54% → 0.97%. **At 2026 funding levels the trade does not clear cash at all.** |
| **Sample** | Hyperliquid hourly funding 2023-05-12 → 2026-08-04 (3.23 years, 27,761 rows for BTC), 12 perps; Binance 8-hourly funding 2020-01 → 2026-07 for the decay curve; Binance spot 1h for the long leg. |
| **Limitations** | **Contains no full bear market.** Hyperliquid launched *after* the 2022 drawdown, so the worst funding environment in recent crypto history is outside its history entirely — every Hyperliquid figure is drawn from a favourable sample. Perp prices reconstructed as `spot × (1 + premium)` because the venue's candle endpoint serves only the most recent ~5,000 bars. |
| **Working** | `report.md` §"Stage C.11 — funding rate carry" (line 1637). ADR-033, ADR-034, ADR-035. |
| **What would reopen it** | **Current funding above roughly 10% annualised sustained for a quarter**, measured live rather than from a trailing average — the three-year average describes a regime that has ended. Two standing qualifiers travel with any reopening: funding correlates **0.5+ with trailing price trend** (BTC pays 5.77 bps/day in uptrends against 1.87 in downtrends), so this is a bull-market income stream wearing a delta-neutral label; and it is **not a general property of perps** — MERL paid **−22.38%/yr** and TNSR **−32.41%/yr**, so shorting TNSR would have cost 75% of notional over 2.3 years. |

---

### H8 — Cross-sectional funding carry

> Going long the perps paying the most negative funding and short those paying
> the most positive, dollar-neutral on one venue, harvests the dispersion
> between instruments even after the funding *level* has been competed away.

| | |
|---|---|
| **Status** | **Closed — signal present, cancelled by its own hedge** · 2026-08-05 |
| **Deciding number** | Funding income **+43.68%/yr on deployed capital**, price return **−42.91%**, cost −0.66% — **net +0.11%** against a 4% risk-free rate, a shortfall of 3.89 points. Max drawdown **−75.85%**. The price term's daily volatility is **10.9× the funding term's** (1.81% vs 0.166%). |
| **Sample** | Hyperliquid, **232 perps considered / 231 usable / 55 delisted and retained**, 4,411,046 hourly funding observations, 1,182 days 2023-05-12 → 2026-08-05. Both legs priced from the venue's own daily candles. Survivorship-free by construction. |
| **Limitations** | **Contains no bear market** — the venue launched after the 2022 drawdown, and a dollar-neutral book's price term is exactly what an untested regime moves. Delisted perps are assumed to liquidate at their last printed price; the venue settles them at an oracle price this study cannot see. |
| **Working** | `report.md` §"Stage C.13 — cross-sectional funding carry" (2026-08-05). ADR-036, ADR-037. |
| **What would reopen it** | **Not a better signal and not lower fees.** Two independent things would each have to change. First, **dispersion would have to widen back**: measured on a fixed cohort it fell **77%**, from a 241.50% decile spread in 2023 to **53.45%** in 2026, and the all-instruments series looks flat only because the venue kept listing wilder coins — the cross-section grew 21 → 190, and the two measures differ by 3× purely on composition. Second, and more fundamentally, **the price term would have to stop cancelling the carry**. Negative funding is compensation for holding assets that keep falling; the long and short baskets correlate **−0.718** and diverge in the costly direction. A version of this trade that hedged the cross-sectional price exposure rather than only the dollar exposure would be a different hypothesis, and would need its own test. Note also that break-even cost is **1.76 bps a side against 1.5 modelled** at 51.7× annual turnover — a 17% margin, so unlike H4 cost here is *nearly* binding and any fee change closes it. |

---

### H9 — Time-series momentum on daily bars

> Trends persist: recent winners keep winning over horizons of weeks to months,
> by enough to beat holding BTC on risk-adjusted terms.

| | |
|---|---|
| **Status** | **Closed — insignificant after deflation, and untradeable where it appears** · 2026-08-06 |
| **Deciding number** | Primary spec (L90/H30) net-of-3bps Sharpe **0.302 vs BTC buy-and-hold 0.183** — beats the benchmark, but **deflated Sharpe 0.446** against 12 registered trials, **alpha t = 1.01**, and **7/12** specs positive. The three specs clearing the literal bar (beat BTC, DSR > 0.5) are **all at the 7-day hold** — the registered fitting-artifact pattern. On the **27 executable symbols** the primary collapses to **Sharpe 0.013**. Best single cell (L30/H7, net Sharpe 0.647) deflates to **0.732**. |
| **Sample** | C.10's universe **reused verbatim**: 60 members from 291 listed at 2021-08, 58 in matrix (LUNA splice + BTT excluded identically), **12 died in-sample**, 2021-08 → 2026-07 daily bars, universe 60 → 48 over the window. Contains the 2022 collapse, 2024 bull, 2025–26 compression. |
| **Limitations** | The measured book is **net short (−0.275 mean exposure) with negative beta in every cell** (−0.03 to −0.43), earning **+56.9%/yr in down-trending periods against −14.7%/yr in up** — a short-alt-decline position, not trend discovery. Its income requires an alt bear market to exist. |
| **Working** | `report.md` §"Stage C.16 — time-series momentum" (2026-08-06). ADR-041. Bars pre-registered in commit 88b69d8. |
| **What would reopen it** | **Not lower fees** — break-even costs run **66–265 bps a side** against 1.5 modelled, so cost was never within two orders of magnitude of binding (the H4 pattern). Reopens only if, on data that includes a full bear regime, **at least half the registered grid** beats buy-and-hold BTC risk-adjusted with **deflated Sharpe ≥ 0.95**, **and** the effect survives on the executable subset — the full-universe result is dominated by shorting coins that no reachable venue lists. A single cell clearing any bar reopens nothing; the grid was registered precisely so one cell cannot. |

---

### H6 — Spread capture on thin perpetuals *(in flight)*

> On instruments too thin for the majors' competition, the spread-to-cost ratio
> is favourable enough to survive adverse selection.

| | |
|---|---|
| **Status** | **In flight — awaiting data** |
| **Deciding number so far** | Suggestive but unusable: CME micro silver shows a spread-to-cost ratio of **3,889 on 69 quote updates in a day** (one quote per 20 minutes); micro copper **65.0 on 1,494**. A spread you cannot be filled against is not an opportunity — and it is not a dismissal either. |
| **What it is waiting for** | The **10 thin Hyperliquid perps subscribed on 2026-08-03** (HYPE, SOL, PUMP, DOT, LINK, ARB, GMX, MERL, TNSR, NOT) to accumulate enough quotes *and* aggressor-signed trades to run the C.9 census on. bbo-1s cannot settle it because it carries no trades. Cost: **zero** — the recorders are already capturing it. |
| **How to close it** | Re-run the C.9 census (`research.microstructure`) once ≥1 week of data exists. If the thin end survives spread − adverse − cost, it is the first positive result this project has produced and earns a Phase C fill simulation. If not, H3 closes completely. |
| **Working** | `report.md` §Stage C.9 "Contracts too inactive to call a market"; `config/venues.yaml` hyperliquid symbol rationale. |

---

### H7 — Cross-venue divergence *(in flight)*

> The same asset diverges between Kraken, Coinbase and Hyperliquid by enough,
> and for long enough, to be worth trading against.

| | |
|---|---|
| **Status** | **In flight — awaiting data** |
| **Deciding number so far** | None measured directly. The nearest evidence is Hyperliquid's perp-to-*own-index* premium: mean **0.65 bps**, p99 **14.59 bps**, worst adverse hourly move **38.2 bps**. This is explicitly **not** the cross-venue number — it understates true divergence by whatever Hyperliquid's index and the actual long venue differ by, which has never been measured here. |
| **What it is waiting for** | Simultaneous multi-venue recorded history. All three recorders have only run together since **2026-08-01**, so the overlap is measured in weeks. Any divergence claim needs enough overlap to span more than one regime. |
| **How to close it** | Measure the realised basis between the three venues on the same clock, then charge it against the round-trip cost of both legs — 80 bps at Kraken/Coinbase, 3 bps at Hyperliquid. The asymmetry means any spot-to-spot arbitrage carries 160 bps of cost, which is the bar to clear. |
| **Working** | `report.md` §Stage C.11 "Basis risk"; ADR-034 on the cross-venue structure. |

---

## Cross-cutting findings

These belong to no single hypothesis and would be lost if filed under one.

### The recurring diagnosis, and the one case that broke the pattern

**H1, H2 and H3 all failed the same way: edge per trade was smaller than cost
per trade.** 3.31 bps against 80. 0.22 against 5.33. A spread minus adverse
selection that never covered the fee. It was tempting to conclude that cost is
*the* constraint and that the whole problem is finding a cheaper venue.

**H4 tested that directly and refuted it.** Holding for days instead of
milliseconds worked exactly as intended — break-even costs of **300–550 bps
against a 3 bps venue**, a margin of 100–180×, and 98 of 175 pairs profitable
both gross and net of venue cost. Cost stopped being the binding constraint
entirely. **There was no edge underneath it.** The relationships did not persist
(0 of 180), the best result was weaker than what screening 1,653 noise pairs
would produce, and nothing was executable.

The correct reading of the four together is not "costs are too high" but
**"small edges at retail-accessible venues are either absent or already
priced"** — and that the two cases are distinguishable only by measuring, which
is why every entry above records which one it was.

### The measured venue cost landscape

Every future hypothesis is constrained by this table. **Every fee schedule in
this project has been found stale at least once** (ADR-012) — Kraken
restructured its spot schedule on 2026-07-09, and CME announced a change
effective 2026-04-01 that falls *inside* a data range already purchased. Treat
these as dated measurements, not constants.

| venue | maker per side | **round trip** | verified |
|---|---|---|---|
| Kraken spot, base tier | 40 bps | **80 bps** | 2026-08-01 |
| Coinbase Advanced spot, base tier | 40 bps | **80 bps** | 2026-08-01 |
| Hyperliquid perps, base tier | 1.5 bps | **3.0 bps** | 2026-08-01 |

CME micro futures charge **per contract**, so their cost in bps is a function of
the contract's notional — which is why the same $2.02/side lands anywhere from
0.4 to 102 bps (ADR-023). Measured 2026-07-15:

| contract | notional | round turn | **cost bps** |
|---|---|---|---|
| MNQ micro Nasdaq | $59,670 | $2.44 | **0.41** |
| MES micro S&P | $38,027 | $2.44 | **0.64** |
| MGC micro gold | $40,505 | $3.94 | **0.97** |
| M6A micro AUD | $6,985 | $2.22 | **3.18** |
| MBT micro bitcoin | $6,505 | $4.04 | **6.21** |
| MET micro ether | **$191** | $1.94 | **101.76** |

Two structural consequences worth carrying forward. **The cheapest venue
reachable from British Columbia is Hyperliquid at 3 bps**, and it is also the
only one offering a short — so any strategy needing a short leg is a cross-venue
strategy with an asymmetric cost structure (ADR-034). And **notional decides
everything on CME**: MET is 250× more expensive than MNQ for the same $2 ticket.

### Engineering lessons that generalise

Drawn from defects this project actually hit, not from general principle.

**Components tested on samples fail at real scale, and present as data
problems.** Full-day validation was OOM-killed at 12.8 GB the first time it met
a real day. A vendor download buffered 76.3 GB into memory and died at 9.1 GB
**after the charge had already committed**. Training hit 5.48 GB and the
reduction from 6.6 GB was reported as "bounded" when it was not. Each looked
like a data issue and was a scale issue. ADR-005 and ADR-025 exist for this.

**Time-interval arithmetic unions before summing — always.** Three separate
defects, each found only after producing a wrong number in a report: duplicate
reconnect records inflating downtime, gap windows summed at full duration
instead of their intersection with the recorded span, and CME closure windows
double-counting an hour. The shape is always the same and always plausible: a
list of windows, a `sum()`, and no union. It never raises. This is now a
standing rule in CLAUDE.md.

**Append order across processes is unreliable by design, not by accident.**
During every recorder restart two processes append to one `sessions.jsonl`, and
the outgoing process's `end` can land after the incoming process's `start`. Read
in file order that sequence reports a **602 ms unclean termination** — a
graceful restart recorded as a crash. Order by the clock, never by position
(ADR-028).

**A check that cannot fail is not a check.** The guard that silently dropped an
inverted gap window would have hidden exactly the corruption worth knowing
about — and hidden it twice, since `merge_windows` also filters inverted
windows, leaving the coverage union and per-kind totals to disagree with nothing
to show why. The same shape appeared as `_dates_available` returning an empty
set that was reported as "no recorded data" and cost a full overnight cycle.

**The most dangerous defects are success-shaped.** The C.10 look-ahead bug —
pair start indices computed as offsets from each series' own end, so any pair
with a leg that died traded inside the window it had been selected on —
produced **the highest-ranked result in the study**: 223% annualised from four
trades. A bug that makes results worse gets investigated. A bug that makes them
better gets published.

---

## What this project has and has not established

### Established

**Five strategy hypotheses have been tested to a standard that permits closing
them.** Each rests on measured figures with named cost assumptions, not on
impressions. Three closed because a real cost exceeded a real edge; one closed
because removing the cost constraint revealed no edge; one is a genuine but
decayed income stream that no longer clears cash.

**On retail-accessible venues, small edges do not survive.** That is the
substantive finding, and it is narrower than "there is no edge in crypto
microstructure". What has been shown is that at 80 bps round trip on reachable
spot venues, 3 bps on the one reachable perp venue, and 0.4–6 bps on CME micros,
the specific edges tested were either below cost or absent. It has *not* been
shown that no edge exists at fee tiers this project cannot reach, at latency it
does not have, or on instruments it has not surveyed.

### What the infrastructure demonstrably does

This is the durable output regardless of strategy outcomes, and it is real:

- **Continuous multi-venue tick capture** — three recorders under systemd,
  lossless raw storage, gap and session-lifecycle accounting. 2026-08-03
  validates **PASS on all three venues**: Kraken 16.7M messages with 16.5M CRC32
  checksums and zero failures, Coinbase 3.5M messages with zero sequence gaps,
  Hyperliquid 1.5M with 32,200 snapshots — 100.00% coverage outside gaps, zero
  crossed or locked books.
- **Validation that distinguishes not-applicable from clean.** A venue with no
  sequence numbers reports `n/a`, never `0`, so an unavailable check can never
  read as a passed one.
- **Bounded-memory data paths** proven at real scale — full-day replays and
  44 GB month ingests in a few hundred MB of RSS.
- **Vendor purchasing with a cost gate and an append-only ledger**, which caught
  a real error before it spent money.
- **Free-archive acquisition with per-file provenance** — 4,970 files, each with
  source, URL, sha256 and retrieval date.
- **Point-in-time universe construction** that is survivorship-free by
  construction rather than by caveat.

The capture and validation layer has found real defects in its own inputs
(crossed books during CME halts, a 22.6 s host stall invisible to every check
but snapshot cadence) and has never been the reason a strategy failed.

### Genuinely open

**Awaiting data only — no new access or capital required:**

- **H6, thin-perp spread capture.** Closes in roughly a week at zero cost, on
  data already being recorded.
- **H7, cross-venue divergence.** Needs months of simultaneous three-venue
  history; the recorders have run together only since 2026-08-01.
- **Whether any Phase B result generalises across regimes.** Every model metric
  so far rests on days, not regimes. This is a data problem and not a code
  problem, and the research-honesty rule in CLAUDE.md keeps it labelled as such.

**Would require a change in venue access, capital, or latency:**

- Anything depending on maker rebates, which no reachable venue offers.
- H1's reopening condition — sub-3 bps round trip needs $10M–$250M of trailing
  30-day volume.
- Anything requiring co-location or sub-millisecond latency, ruled out by
  ADR-002's 5–100 ms design tier.
- Strategies needing a short on a broad instrument set; only Hyperliquid offers
  a short at all, across 232 perps of which most are too thin to matter.

### An honest reading

Five tests, no deployable strategy. That is a real outcome and not a failure of
method — the tests were designed to be capable of producing a positive result,
and two of them (H1's AUC 0.596, H5's 8% on capital) did produce measurable
effects that were then correctly judged insufficient. The project's pattern has
been to find the number that closes a question rather than the number that keeps
it open, which is the right direction to err, and several stages closed on
findings that contradicted the stage's own starting premise.

What has not been demonstrated is that this approach will eventually find
something tradeable. Five closures is evidence about five hypotheses, not about
the sixth. The infrastructure is genuinely good and the strategy pipeline has
genuinely produced nothing deployable, and both remain true at the same time.
