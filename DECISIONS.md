# DECISIONS.md — architecture decision log

Append-only. Newest entries at the bottom. Never rewrite an accepted decision; if a
decision is reversed, add a new entry that supersedes it and links back.

---

## ADR-001: Venue selection — Kraken spot, Coinbase Advanced Trade, CME micro futures

**Date:** 2026-07-30 · **Status:** accepted

**Context.** The operator is a Canadian resident in British Columbia. Binance, Bybit,
OKX and KuCoin do not serve Canadian residents, so the usual high-liquidity offshore
perpetuals venues are unavailable regardless of their technical merits. The strategy
class (short-horizon microstructure) needs deep books, granular public market data, a
placeable co-location story, and a legal path to live capital.

**Decision.** Target three venues: Kraken spot (matching engine at Equinix London,
reached via AWS eu-west-2), Coinbase Advanced Trade (matching engine in AWS us-east-1,
reached in-region), and CME micro futures via Interactive Brokers with Databento
supplying market data. Stage 1 records Kraken and Coinbase only; CME/Databento joins
when research demands it.

**Consequences.** All connectivity, fee modeling, and latency work is scoped to these
venues. Liquidity and edge expectations are calibrated to regulated spot books rather
than offshore perp books: thinner queues, smaller edges, but a real legal path.
Anything that assumes Binance-style feeds must be rejected in review.

---

## ADR-002: Latency tier — design for 5–100 ms round trip

**Date:** 2026-07-30 · **Status:** accepted

**Context.** From a VPS in the venue's own cloud region, realistic round-trip times to
the matching engine are single-digit to low-double-digit milliseconds, plus venue-side
processing variance. True HFT (microseconds, colocation cages, kernel bypass) is not
available to a solo operator on cloud infrastructure, and designing for it would be
wasted complexity. Designing for 500 ms would be equally wrong: at that horizon the
microstructure edge is gone before the order arrives.

**Decision.** Every component assumes a 5–100 ms round-trip latency tier. Backtests
consume *measured* latency distributions collected by `ops/telemetry/` rather than
constants. Nothing in the codebase may be justified by sub-millisecond requirements,
and nothing may quietly tolerate multi-hundred-millisecond staleness in the live path.

**Consequences.** Python asyncio is acceptable for the data plane and (with care) the
Phase D/E execution path; no C++/kernel-bypass work is planned. Queue-position and
fee modeling matter more than shaving single milliseconds. Telemetry runs continuously
from Stage 1 so Phase C has real distributions on day one.

---

## ADR-003: Language split — Python pipeline/research, Rust only in the desktop shell

**Date:** 2026-07-30 · **Status:** accepted

**Context.** The project needs (a) a data pipeline and research stack where iteration
speed dominates, and (b) a desktop control surface where a small native footprint and
robust process supervision matter. A single-language codebase was considered: all-Rust
maximizes runtime safety but cripples research velocity (no polars-notebook ecosystem
parity, slow model iteration); all-TypeScript/Electron makes the shell heavy and adds
nothing to the pipeline.

**Decision.** Python 3.11+ owns the data pipeline (`data/`), research (`research/`),
backtesting (`backtest/`), and Stage-1 telemetry (`ops/`). Rust appears only inside
the Tauri 2 desktop backend (`desktop/src-tauri/`), which supervises the Python
processes, tails logs, and serves the React frontend. The 5–100 ms latency tier
(ADR-002) means Python's overhead is acceptable even for the future live path; if a
hot loop ever needs it, an isolated Rust extension can be introduced with its own ADR.

**Consequences.** One dependency toolchain per side (`uv` for Python, `cargo`/`npm`
for the shell). No shared-memory bridging between Rust and Python — the boundary is
process supervision and files (logs, Parquet, JSON status), which keeps coupling low
and each side independently testable.

---

## ADR-004: The desktop app persists no credentials

**Date:** 2026-07-30 · **Status:** accepted

**Context.** Stage 1 specified that no API key with any permission is used or
requested anywhere. The Stage 1 desktop app nevertheless shipped a Settings
section with five key/secret fields, written as plaintext JSON into the OS
config directory. Even though nothing consumed them, plaintext-on-disk is
exactly the wrong default to inherit into Phase D, when keys become real and
carry account access: config directories get backed up, synced, and copied
into bug reports.

**Decision.** Remove credential storage entirely: the `ApiCredentials` struct,
the `api` settings field, and the five credential inputs are deleted. Loading
an older `settings.json` that still contains an `api` object strips it and
rewrites the file immediately, logging the removal, so no plaintext value
lingers. A non-negotiable rule in CLAUDE.md now forbids the desktop app from
persisting credentials at all; Phase D sources them from the OS keyring
(Secret Service on Linux) or environment variables.

**Consequences.** Phase D must budget for keyring integration (e.g. the
`keyring` crate against Secret Service) before any authenticated connectivity
lands, and its design review must treat "where do secrets rest" as a
first-class question. Until then the desktop app has no secret-shaped state
anywhere, which also keeps its config file safe to attach to bug reports.

---

## ADR-005: Validation streams in bounded memory; data-path code is tested at realistic scale

**Date:** 2026-08-01 · **Status:** accepted

**Context.** The first real full-day validation (2026-07-31: ~17.5M Kraken +
~3.4M Coinbase messages) was killed by the kernel OOM killer at 12.8 GB RSS on
the 14 GiB development machine. `validate_venue_day` materialized every emitted
book-snapshot row per symbol (~2.3 KB per row, measured) and wrote Parquet once
at end of day — ~23 GB extrapolated for the Kraken day alone. The defect
shipped because the validator had only ever been exercised on 25-second
(~7,700-message) and ~30,000-message samples, three orders of magnitude below
one real day. Every future day is this size or larger, and Phase B depends on
this path.

**Decision.** The replay processes a venue-day as a single pass in bounded
memory: only current book state plus running aggregates (histogram counters,
gap accounting, checksum/sequence tallies, coverage arithmetic) are held;
snapshot rows stream to Parquet in 50k-row groups through `BookDayWriter`,
which writes to a temporary name and renames on close so reprocessing stays
idempotent and a crashed run never leaves a partial part file. Unexplained
anomalies are counted with a bounded ledger: a timestamp near no gap window is
definitively unexplained and is discarded immediately; only near-gap
timestamps are retained for span-scoped re-evaluation. Long replays print
progress (messages, day position, elapsed, RSS) so a working process is
distinguishable from a hung one. And the general rule this failure bought:
**data-path components must be tested at the scale they will meet in
production, not on convenience samples.** The pytest suite enforces it with a
memory regression guard that validates a 400k-message synthetic day in a
subprocess and asserts peak RSS under a fixed 600 MB ceiling (the retained-rows
design measured 1,462 MB; streaming measures ~440 MB).

**Consequences.** Full days validate on the laptop at a flat ~450 MB RSS
regardless of day size, and can run alongside a live recorder. The guard test
adds ~30 s to the suite — accepted as the price of never shipping an
unbounded data path again. `rows_written` now comes from the streaming writer,
and any future emitter change that reintroduces per-message retention fails
the guard rather than production.

---

## ADR-006: Day replays warm-start from the previous day's last snapshot

**Date:** 2026-08-01 · **Status:** accepted

**Context.** Continuous recording (the default since Stage 1.6) keeps one
WebSocket session running across days, so a calendar day usually starts
mid-session: its opening book snapshot was recorded on the previous date.
Replayed cold, such a day leaves every book invalid until the first intra-day
reconnect — the real 2026-08-01 partial day scored 0% coverage and zero
verified checksums despite lossless capture, and 2026-07-31 would have capped
at ~93% (Kraken) / ~86% (Coinbase) purely by reconnect luck. The recorder
encloses a target day with margin precisely so the pre-midnight snapshot
exists on disk; the replay simply refused to look at it.

**Decision.** `validate_venue_day` warm-starts: it scans the previous day's
hour files newest-first for each symbol's last snapshot, replays that tail
through midnight building book state only (checksums and sequence numbers
verified during warm-up so a corrupt tail leaves the book invalid, not
trustingly valid), then resets every scoring counter at the boundary. Metrics
therefore describe the target day alone, while sequence continuity still spans
midnight — a cross-boundary sequence break is scored to the day being
validated. Only the immediately preceding date is consulted; a session that
somehow ran longer than a day without any snapshot replays cold and fails
honestly. Every report section states its warm or cold start explicitly.

**Consequences.** Full-day coverage is achievable for any day enclosed by a
running recorder, which is the normal operating condition from now on.
Validation cost includes replaying the previous day's tail (bounded by one
day, typically minutes). Coverage begins at midnight for warmed books, so the
coverage number finally measures the data, not the replay's ignorance of the
prior session.

---

## ADR-007: Recorder downtime is a recorded gap kind, distinct from feed gaps

**Date:** 2026-08-01 · **Status:** accepted

**Context.** gaps.jsonl records disconnects the recorder observed *while
running*; it is structurally blind to periods where the process was not
running at all — systemd restarts, crashes, OOM kills, reboots, manual stops.
The 2026-08-01 outage (01:06:40Z→07:11:59Z, six hours) left no record on
either venue. Unlogged downtime is more dangerous than logged downtime
precisely because every downstream consumer trusts the gap log as the
complete map of missing data: validation subtracts only logged gaps from
coverage, and Phase B will exclude feature windows only inside logged gap
periods. A logged hole is excluded and explained; an unlogged one silently
poisons whatever is computed across it — a long outage surfaces as an
unexplained coverage failure at best, and a two-second restart rounds away
entirely while leaving a discontinuity a microstructure feature window can
span without any flag. The causes also differ and must not be conflated: a
feed gap is the venue dropping us; a downtime gap is us not being there.

**Decision.** The recorder writes session lifecycle markers per venue
(`sessions.jsonl`): `start` on startup before connecting, `end` on graceful
shutdown; dry-run writes none (same rule Stage 1.5 set for gap records).
Validation derives downtime gaps from the marker sequence — end→next start is
a clean `downtime` gap; a start following a start with no end between it
means the previous process terminated uncleanly, so the gap is measured from
the last observed activity (the final raw message on disk) to the new start
and marked `unclean`, never silently treated as clean. Derived gaps are
ordinary `GapRecord`s (`kind` field: `feed` | `downtime` | `unclean`) and go
through the same span clamping, unioning, and anomaly-explanation machinery
as feed gaps; reports state each cause separately plus the union that
coverage excludes. Coverage's numerator subtracts credited time that overlaps
any gap window, so a book left "valid" across an absence cannot count the
hole as covered — numerator and denominator agree on what a gap is. Known
downtime that predates the feature is backfilled from the recorder's own log
timestamps, as sidecar records only.

**Consequences.** Every future stop, restart, crash, or reboot is either
self-recorded or visibly unclean — there is no third state. Validation
explains downtime instead of failing mysteriously, and Phase B can exclude
downtime windows from feature computation with the same confidence as feed
gaps. The marker protocol adds one file per venue and two writes per process
lifetime; the honest cost is that unclean terminations depend on raw data for
their start bound, which is exactly the evidence that survives a crash.

---

## ADR-008: Event and imbalance bars by default; time bars for comparison only

**Date:** 2026-08-01 · **Status:** accepted

**Context.** Phase B needs a sampling scheme deciding when a feature/label
sample is drawn from the event stream. Fixed time bars are the familiar
default, but tick data is not uniformly informative in time: quiet minutes
carry almost nothing while bursts carry everything. Time bars oversample the
quiet stretches and undersample exactly the moments that matter, degrading
label quality and inflating serial correlation between adjacent samples
(Lopez de Prado 2018, ch. 2). The venues also run wildly different message
rates — Kraken roughly 3-9x Coinbase depending on session — so any
count-based scheme behaves differently per venue over the same wall clock.

**Decision.** Event bars (every N book updates) are the default sampler;
imbalance bars (cumulative signed order flow crossing a threshold) are the
information-driven alternative; fixed time bars are implemented but exist
for comparison only and are never the default. The sampler reports samples
per venue per hour so the cross-venue rate asymmetry is visible in every run
rather than discovered as a surprise. Imbalance-bar sample decisions use the
triggering trade's signed quantity computed from pre-sample state, keeping
the strictly-before-t contract intact.

**Consequences.** Sample density follows information arrival, at the cost of
uneven wall-clock spacing (all downstream code treats sample times as data,
never assumes a grid). Identical settings produce different per-venue sample
counts — reported, not hidden. Threshold/interval tuning is deferred until
the pipeline is trusted, same rationale as hyperparameter search.

---

## ADR-009: Labels are cost-aware; every metric names its cost assumption

**Date:** 2026-08-01 · **Status:** accepted

**Context.** Micro-pattern edges here are single-digit basis points while a
Kraken taker round trip costs ~8 bps in tier-0 fees plus the spread. A model
trained on raw mid moves will look predictive and be worthless: most
correctly-predicted moves are smaller than the cost of trading them. This is
the single most common way microstructure research self-deceives.

**Decision.** Alongside raw forward returns, every sample carries net labels
that must clear a configurable round-trip cost before counting as directional
(`y_net_maker_*`, `y_net_taker_*`): +1/-1 only when the move exceeds the
cost, else 0 — an untradeable move is a non-event, not a small win. Fees come
from config/venues.yaml (tier 0 by default, the honest small-account
assumption); maker and taker are computed separately because the answer
differs enormously — maker pays two fee legs, taker pays two legs plus the
spread. Evaluation reports expected value per prediction net of cost next to
AUC/hit-rate for every horizon and both cost modes, and the experiment log
records the assumption on every run.

**Consequences.** Results tables are twice as wide and far more honest. A
model can (and often will) show AUC > 0.5 with negative net EV — that is the
finding, not a contradiction. Queue position and fill probability for maker
assumptions remain execution-layer questions for Phase C; the label layer
states its assumption and does not pretend to answer them.

---

## ADR-010: Gradient boosted trees before deep learning

**Date:** 2026-08-01 · **Status:** accepted

**Context.** The Phase B feature set is small (~43 engineered tabular
features), the data volume is a handful of days, and the immediate goal is
validating a leakage-free pipeline — not maximizing predictive power. Deep
sequence models (LSTMs/transformers over raw book states) demand orders of
magnitude more data to avoid memorizing one regime, are slower to train and
iterate, and their failure modes are harder to audit for leakage — precisely
the property Phase B cannot afford.

**Decision.** LightGBM classifier and regressor with fixed, conservative
defaults are the Phase B models, preceded by two trivial baselines every
model must beat: predict zero (never trade) and predict the sign of the last
return. No hyperparameter search until the pipeline is trusted — searching
over a leaky pipeline just finds the leak. Deep learning is out of scope for
this stage and earns an ADR of its own if regime-diverse data ever justifies
it.

**Consequences.** Cheap training (seconds per fold on the laptop), directly
inspectable feature importances, and native NaN handling for genuinely-missing
features. The ceiling on model capacity is accepted: if a real edge exists at
these horizons, trees on good features should show a trace of it, and a trace
is all a few days of data could support anyway.

---

## ADR-011: Venue expansion — CME micro futures (Databento) and Hyperliquid, collection only

**Date:** 2026-08-01 · **Status:** accepted

**Context.** Phase B showed negative expectancy at every horizon on Kraken and
Coinbase because retail spot fees (80–120 bps round trip at base tier) dwarf
single-digit-bps microstructure edges. Two venue classes have structurally
lower costs and remain legally available to a Canadian resident: CME micro
futures via a broker (per-contract dollar fees, ADR-001 already names them)
and Hyperliquid perps (1.5/4.5 bps base maker/taker). Neither is recorded
yet; nothing can be concluded without data.

**Decision.** Stage C.1 adds both venues for data collection only — no
trading logic, no order placement, no credentials with trade permission. CME
arrives through a Databento GLBX.MDP3 vendor adapter (MES, MBT; MBP-10 +
trades mapped into the canonical format; raw DBN files immutable under
data/vendor/databento/; source column and vendor clocks recorded explicitly,
never ordered against recorder clocks). Hyperliquid arrives through a fourth
live recorder (l2Book/bbo/trades/activeAssetCtx for BTC and ETH, coin names
discovered from the info endpoint, not assumed) using the existing
reconnect/gap machinery; the resubscribe snapshot is the reconnect recovery.
Validation scores each venue on what its feed actually provides: Databento on
adapter-verified sequence continuity (checksums/cadence n/a), Hyperliquid on
snapshot cadence (sequence/checksums n/a, never 0).

**Consequences.** Research and backtest components for these venues are
deliberately out of scope until collection is validated. The recorder unit
must be restarted to activate Hyperliquid capture — the operator's call,
since it briefly interrupts the running Kraken/Coinbase collection (the gap
self-records per ADR-007). Databento ingestion awaits an operator-provisioned
API key from the environment; free signup credit covers adapter validation.

---

## ADR-012: Fee schedules are perishable — dated sources or they are wrong

**Date:** 2026-08-01 · **Status:** accepted

**Context.** Every fee schedule this project has recorded has now changed or
been found stale at least once: Kraken restructured on 2026-07-09 to
0.40%/0.80% at base tier while venues.yaml still carried 0.25%/0.40% — making
the Phase B Kraken results optimistic by ~30 bps per round trip — and the
Hyperliquid and CME schedules use tier and unit models (14-day weighted
volume; per-contract dollars) that this config's 30-day-bps schema cannot
even express exactly. In a project whose Phase B conclusion is literally
"fees decide everything", a silently stale fee table is the most dangerous
number in the repo.

**Decision.** Every figure in venues.yaml carries a dated comment recording
where it came from and what was NOT verified. Schema-model mismatches are
stated in the comment rather than papered over (Hyperliquid: base tier only;
CME: conservative worst-case bps approximation of dollar fees, with the real
model deferred to Phase C). Any stage that consumes fees re-verifies the base
tier against the venue's published schedule before trusting results, and
corrections land as their own commits with the impact quantified in
progress.md.

**Consequences.** Fee corrections are auditable history rather than silent
edits. Phase C must implement per-contract dollar fee modeling for CME before
any backtest touches it, and must re-verify all four schedules — the config
is a dated snapshot, never an authority.

---

## ADR-013: Snapshot streams are not incremental books — and what that rules out

**Date:** 2026-08-01 · **Status:** accepted

**Context.** Hyperliquid's l2Book pushes a complete 20-level book per block
with a minimum interval of roughly 0.5 s (observed 0.37–5.4 s), bbo carries
no depth, and no sequence numbers or checksums exist. Differencing successive
snapshots looks like it yields order-flow events, but it aliases everything
that happened between pushes: order flow imbalance, queue imbalance, depth
deltas, and book slope computed that way are fabrications at these horizons —
plausible-looking numbers with no microstructure meaning.

**Decision.** The distinction is enforced in code, not prose. The venue is
declared ``snapshot_stream: true`` in config; validation scores it on
snapshot cadence (interval distribution, stale intervals >10 s explained
against gap windows, unexplained silence >60 s fails) instead of
sequence/checksum integrity, and skips warm-start replay because every
message is a full book. The feature capability matrix
(research/features/capabilities.py) rules out OFI, queue imbalance, depth
ladders, and book slope for this venue; the feature engine nulls them and
``require_supported`` raises on explicit request. bbo is deliberately never
merged into book state — touch-only updates inside a snapshot stream would
fabricate pseudo-incremental depth.

**Consequences.** Hyperliquid research is limited to spread, microprice,
BBO-derived, trade-derived, and cross-venue features — honestly labeled as
such in every downstream artifact. If depth-resolution work on this venue
ever matters, it needs a different data source (e.g. an order-flow
reconstruction from the chain), not a reinterpretation of this feed.

**Amended 2026-08-01 (Stage C.2), by measurement:** the documented cadence
in this ADR was wrong. Recorded l2Book intervals are p50 5,387 ms, not the
documented ~0.5 s minimum — ten times slower. Every conclusion above holds
a fortiori. See ADR-014 for what measurement changed.

---

## ADR-014: Capability claims are measured against recorded data, not vendor docs

**Date:** 2026-08-01 · **Status:** accepted

**Context.** ADR-013 classified Hyperliquid's features from the venue's
documentation: l2Book "per block, ~0.5 s minimum", bbo "on top-of-book
change". Stage C.2 checked both against 242,907 recorded messages and found
the documentation wrong in both directions. l2Book actually arrives at p50
5,387 ms (p90 5,505; max 6,915) — an order of magnitude slower than
documented, which would have quietly destroyed any sub-5-second label on
this venue. bbo is *better* than documented: it carries `px`, `sz`, and `n`
at both touches (171,195 of 171,195 updates) and fires on size-only changes
(164,821 of them), not merely price changes. The specific question that
prompted the check — does microprice belong in the BBO set, given it needs
resting sizes — resolved in the matrix's favour, but only by looking.

**Decision.** Capability classifications are justified by measurements taken
from recorded data, with the numbers and a sample message shape recorded in
progress.md so any future session can re-check them. Two structural
consequences land in the matrix itself: (1) `SUB_100MS_FEATURES` — a feature
whose bin width is finer than a venue's measured median update interval is
unsupported there, which removes the ±100 ms cross-venue lead-lags from
Hyperliquid (100 ms bins against 123 ms median bbo updates are mostly
empty); and (2) `REQUIRED_CHANNELS` plus `assert_stream_supports()` — when a
venue's credited features depend on a channel the parser does not yet emit
(Hyperliquid's bbo, which `hyperliquid_parse.py` deliberately does not map),
the mismatch raises instead of silently computing 5.4-second-stale values.

**Consequences.** Adding a venue now costs a measurement pass before its
capabilities can be trusted, and re-measurement is warranted whenever a
venue changes its infrastructure. The bbo-to-event-stream plumbing is a
known, guarded gap rather than a silent one: until it lands, Hyperliquid
features cannot be computed at all rather than being computed wrongly.
Documented venue behaviour is treated the same way as documented fee
schedules (ADR-012) — a dated hint, never an authority.

**Amended 2026-08-01 (Stage C.2):** the plumbing landed — the Hyperliquid
parser now emits bbo alongside l2Book as a distinct `kind="bbo"` row, and
`assert_stream_supports` reads the parser's own emitted-channel set, so the
gate passes because the code changed rather than because a docstring did.
The same pass corrected one classification: `qimb_best` consumes exactly
the inputs microprice does (best price and size, both sides), so it moved
from `DEPTH_FEATURES` to `BBO_AND_TRADE_FEATURES` — two features with
identical inputs cannot sit in different categories.

---

## ADR-015: Label horizons extend to 15 minutes; embargo scales with the longest one

**Date:** 2026-08-01 · **Status:** accepted

**Context.** Phase B's first run tested 100 ms to 30 s and found negative
expected value at every horizon on both spot venues: the mid move at those
horizons is single-digit basis points while the round trip costs 80–120 bps
at base-tier retail fees. That result answers "is there a fast edge" but not
the question it raises — cost per round trip is *fixed*, so expected value
per trade grows with holding time as long as the move does. The horizon at
which the move finally exceeds the cost (or the demonstration that it never
does within a plausible range) is the actual decision-relevant finding, and
30 s was too short to see it.

The extension is not free. Labels span time, so a 900 s label computed just
before a fold boundary resolves 900 s into the test block. An embargo sized
for the old 30 s maximum would leave 870 s of overlap — reintroducing
exactly the leak purged cross-validation exists to prevent, and doing it
silently, in the direction that flatters results.

**Decision.** The horizon set extends to 60 s, 300 s, and 900 s while
keeping every existing horizon, so the decay curve lengthens rather than
shifts and remains comparable with earlier runs. Embargo sizing becomes a
function of the run's horizons — `embargo_ns_for(horizons)` returns the
longest horizon's span — never a constant, and the gap-validity window that
decides whether a sample is trainable derives from `MAX_HORIZON_MS` rather
than a hardcoded 30 s. Both are pinned by tests: one asserting the embargo
scales with the longest horizon in the run, one asserting a long-horizon
`PurgedKFold` actually removes more training data than a short one, and one
asserting the triple barrier stays armed for a 15-minute limit instead of
silently truncating.

**Consequences.** Long-horizon folds train on materially less data — the
embargo consumes 15 minutes on each side of every test block — which is the
honest cost of not leaking, and it makes long-horizon results noisier on a
single day. Sample rows now carry eight forward-return labels and sixteen
cost-aware net labels. Samples stay pending in the extraction buffer for up
to 900 s, well inside the hard cap that bounds that buffer. Extending
horizons again means only appending to the set: everything downstream reads
the maximum from one place.

---

## ADR-016: Capability entries are per contract, and resolution outranks price

**Date:** 2026-08-02 · **Status:** accepted

**Context.** Phase B showed retail spot fees exceeding the available edge at
every horizon, which is the case for CME micro futures: per-contract dollar
fees on MES are roughly 0.2 bps of notional against 80-160 bps on spot. The
open question was which micro contract to buy history for. MBT (Micro
Bitcoin) is far cheaper per day than MES (Micro E-mini S&P) and trades the
asset class the rest of this project already records, which makes it the
tempting choice on price and on thematic fit.

One purchased trading day (2026-07-31, $3.2053 total, continuous front
month) settles it against measurement rather than intuition:

- **MES**: 14,989,106 book updates (198.3/s), inter-update p50 0.084 ms,
  p90 7.8 ms; 455,192 trades at a 26.3 ms median interval.
- **MBT**: 380,358 book updates (5.0/s), p50 1.273 ms but p90 307 ms and a
  single 5.69-hour spell with no book update at all; **1,426 trades in the
  whole session**, median 10.3 s apart, p90 98 s.

The two contracts share a venue, a feed, a schema and a clock, and differ by
39x in book rate and 319x in trade count. A single `cme` capability entry
would credit MBT with MES's resolution — the same class of error as
crediting a snapshot stream with incremental depth (ADR-013).

**Decision.** Capability entries are keyed by (venue, contract root), with
`CONTRACT_CAPABILITIES` overriding the venue default and `contract_key()`
normalising continuous, outright and root symbology so a roll cannot change
what a contract is credited with. MES receives the full library. MBT loses
`SHORT_TRADE_WINDOW_FEATURES` (`signed_vol_1s`, `signed_vol_5s`,
`trade_count_5s`, `vwap_minus_mid_5s`), which at a 10.3 s median trade
interval would be constant zeros presented as measurements. Contracts not
yet measured fall back to their venue entry rather than being granted
capabilities by assumption.

And the rule the numbers force: **when choosing what history to buy,
measured resolution outranks price.** Measured cost per day is MES $3.1384
and MBT $0.0670 — about **$791/yr versus $17/yr** over ~252 trading days,
so MBT is roughly 47x cheaper (the ~$105/yr figure this stage started from
assumed an 8x event-rate gap; the measured gap is 39x, so MBT is cheaper
still). It is also unusable for the short-horizon research this project
exists to do: no trade-derived feature below 30 s, a fifth of 100 ms label
windows containing no book update, and a 5.7-hour daily hole that no gap
sidecar records because vendor data carries no reconnect log. Buying five
years of MBT for the price of six weeks of MES would buy five years of data
that cannot answer the question.

**Amended 2026-08-02 (Stage C.3) — this ADR's MBT evidence is contaminated
and its conclusion is withdrawn pending re-measurement.** Validation of the
same file confirmed the mechanism: MBT's book stops updating entirely at
15:18:41Z and stays dead until the Friday close, losing 5.99 h of a 21 h
session (coverage 71.5%). MBTN6 expired that day — CME Bitcoin futures
settle against the CF Bitcoin Reference Rate at 16:00 London — so the
measurement captured a contract ceasing to exist, not a thin market. Details
below.** Resolving
`MBT.c.0` through the vendor symbology API returned instrument_id 42101132 =
raw symbol **MBTN6**, the July 2026 contract, which expired on **2026-07-31
— the very day measured**. CME Micro Bitcoin futures expire the last Friday
of the contract month, so the sparsity figures above were taken on an
expiring contract after open interest had already rolled to August. `MES.c.0`
resolved to MESU6 (September quarterly, expiring 2026-09-18) and is
unaffected. The "MBT is too sparse for short-horizon research" conclusion
must be re-measured on a non-expiry day before it is treated as settled; the
per-contract capability entry stands as the conservative default until then.
The general rule the ADR establishes — measured resolution outranks price —
is unaffected, and this episode strengthens it: the measurement itself has
to be taken on a representative day.

**Consequences.** MES is the CME contract worth backfilling despite costing
47x more per day; a year of MES history is ~$791, a real but affordable
decision to make deliberately rather than by accident. MBT remains worth
collecting cheaply for cross-asset and longer-horizon work (>=30 s), and its
own capability entry now says exactly that. Any future contract added to
this venue needs its own measurement pass before it can be credited with
anything — price is not evidence of resolution, and here it understated the
gap by a factor of five.

---

## ADR-017: Metered vendor data passes a cost gate; vendor keys are not trading keys

**Date:** 2026-08-02 · **Status:** accepted

**Context.** Databento bills per request against a prepaid balance, and the
client will happily issue a request that costs a hundred dollars as readily
as one that costs a cent — a mistyped date range, a schema swapped from
`trades` to `mbo`, or a symbol resolving to a whole parent family is enough.
Nothing in the vendor SDK asks for confirmation. Meanwhile the project's
Stage 1 credential rules were written for exchange keys that can move money,
and read literally they would either ban a read-only data key outright or,
read loosely, wave through anything a vendor issues.

Both problems are about the same thing: an action with real-world cost or
risk needs an explicit, checkable barrier rather than care.

**Decision.** Two barriers.

*Cost gate.* Every metered request is priced before it is issued, via the
vendor's own free metadata endpoints (`metadata.get_cost` and
`metadata.get_billable_size`, verified present on the installed client). The
estimate is checked against `budget.vendor_usd_cap` (config, default 25 USD)
minus cumulative spend read from an **append-only on-disk ledger**
(`data/vendor/spend_ledger.jsonl`), so the ceiling survives restarts and a
hundred individually-trivial requests cannot walk past a cap none of them
breaches. The charge is committed to the ledger *before* the bytes are
requested: recording afterwards would leave a crash window in which money
was spent and the ledger did not know. An unpriceable request is refused,
never assumed cheap. `fetch_day` is the only sanctioned download path and it
performs all of this itself, so a caller cannot bypass the gate by
forgetting.

*Credential distinction* (now CLAUDE.md rule 4). A read-only market-data
vendor key is permitted; a key that can place an order or move money is not,
in any stage before D, and never in the desktop app. The test is capability,
not vendor. The key lives in a gitignored `.env`, loads through the
pydantic-settings config layer as a `SecretStr` (so a repr or log line
cannot leak it), and `os.environ` reads were deleted so there is exactly one
credential path that fails clearly when it is missing.

**Consequences.** Buying data is a deliberate, logged act with a receipt.
The ledger doubles as the cost record that makes backfill decisions
arithmetic rather than guesswork (ADR-016). Raising the cap is a config edit
someone has to make on purpose. The honest cost: the gate cannot prevent a
charge the vendor's own estimate understates, so estimate-versus-actual is
compared after every download — on the Stage C.3 purchase they matched to
the cent, since Databento bills exactly the billable size it quotes.

**Recorded failure.** The four Stage C.3 downloads were issued *before* this
gate existed, under an amended task list that omitted it — $3.2054 spent
ungated. The ledger was seeded with those actual charges rather than started
at zero, so the cap reflects real spend. The lesson is the ordering one:
a guardrail that arrives after the action it guards is documentation, not a
guardrail.

---

## ADR-018: MBT carries the full feature library — supersedes ADR-016

**Date:** 2026-08-02 · **Status:** accepted · **Supersedes:** ADR-016

**Context.** ADR-016 restricted MBT's capability entry after measuring
380,358 book updates against MES's 14,989,106 — a 39x gap that made MBT look
unusable for short-horizon work. That measurement was taken on 2026-07-31,
which was MBTN6's **expiry day**: the contract settled against the CF Bitcoin
Reference Rate around 15:00 UTC, its book stopped updating entirely at
15:18:41Z, and 5.99 h of a 21 h session had no data at all. The figure
described a contract in its final hours.

The confound was not obvious from the data alone. What made it look like a
liquidity signal was that it *arrived as a price signal*: MBT's day cost
$0.0652 against MES's $2.5686, and cost is proportional to billable bytes,
so cheapness read as thinness. Both readings fit the numbers; only symbology
resolution — `MBT.c.0` -> instrument_id 42101132 -> raw symbol `MBTN6`,
expiring that Friday — distinguished them.

**Decision.** Re-measured on a mid-life front month: **2026-07-15**, a
Wednesday with **16 days to MBTN6 expiry** and a full 23.00 h scheduled-open
session, same date for MES so the comparison is like-for-like. Corrected:

| | MES (MESU6) | MBT (MBTN6) |
|---|---|---|
| book updates | 10,649,955 (128.6/s) | **4,275,234 (51.6/s)** |
| book interval p50 / p90 | 0.1 ms / 50 ms | **0.5 ms / 50 ms** |
| trades | 360,571 | **15,933** |
| trade interval p50 / p90 | 50 ms / 500 ms | **1,000 ms / 30,000 ms** |
| book intervals < 100 ms | 98.28% | **96.38%** |

**MES/MBT is 2.49x on book events, not 39x.** MBT's book updates fall below
100 ms 96.38% of the time, so every book-derived feature is supported at
every horizon in the set. Its trade stream is genuinely thinner — 22.6x
fewer trades, median 1 s apart against MES's 50 ms — but the windows are
populated, not empty: 55.7% of trade gaps fall under 1 s and 80.2% under
5 s. A zero in a 1 s signed-volume window on MBT is a true observation of a
quiet second, not the fabricated zero of a dead contract. **The
`SHORT_TRADE_WINDOW_FEATURES` restriction on MBT is removed; both contracts
carry the full library.** The category itself is kept — the next genuinely
thin contract will need it — and a test pins that it still exists.

**Consequences.** MBT is a viable research instrument, which materially
changes the backfill economics ADR-016 reasoned about: at $0.7525/day
mid-life (not the $0.067 the expiry day suggested) MBT is ~$190/yr against
MES at ~$573/yr on the same session — **~3x cheaper, not 47x**, and usable.
Choosing between them is now a real decision rather than a foregone one.

**The rule this establishes, beyond MBT:** *a single-day measurement of an
expiring instrument measures the expiry, not the instrument.* Any contract
measurement must record its distance to expiry alongside the numbers, and
any capability decision resting on one session must state which session.
ADR-016's general principle — measured resolution outranks price — survives
and is strengthened: here price was precisely the misleading signal, and
only measurement on a representative day corrected it. ADR-016 is left
unedited as the record of how that misreading happened.

---

## ADR-019: Crossed books during no-match windows are explained; crossed state never reaches features

**Date:** 2026-08-02 · **Status:** accepted

**Context.** MES failed validation on 2026-07-15 with 193 crossed book
events — best bid above best ask — while MBT passed the same session with
zero. A matching engine cannot produce a crossed book, so this looked like
an adapter defect, and the candidates were real: MDP3 action semantics,
implied and calendar-spread instruments appearing inside the outright book,
ordering by the wrong timestamp, or mbp-10 aggregation artifacts.

The evidence ruled them out one at a time. **Instruments:** the file contains
exactly one instrument_id (42003239, MESU6) across all 10,649,955 records and
all 193 crossings, so no implied or spread instrument is being mixed in.
**Actions:** crossings appear under every action type (add 43, cancel 70,
modify 79, trade 1), so no single unhandled action explains them — and the
adapter never applies actions, because mbp-10 delivers the resolved book in
each record. **Ordering:** crossing is detected within a single record, so
inter-record ordering cannot manufacture it. **Transience:** the inversion is
bid 7655.00 against ask 7615.75, 39.25 points, persisting across minutes —
not a sub-millisecond artifact. **Vendor flags:** 192 of 193 carry only
F_LAST, the same flag 10.29M ordinary records carry; none is marked
F_MAYBE_BAD_BOOK.

What identified the cause was the time distribution: **192 of 193 crossings
fall inside 21:00–22:00 UTC and the last at 22:00:00.009Z.** That hour is the
CME daily maintenance halt (16:00–17:00 US/Central), already in the session
calendar. Order entry and cancellation continue through the halt while
matching is suspended, so the book legitimately crosses; it uncrosses at the
reopen auction, which is why the final event lands 9.9 ms after the reopen.
The crossings are real, correctly delivered, and expected.

**Decision.** Two separate things, deliberately not conflated.

*Classification, not suppression.* A crossing inside a **no-match window** —
the scheduled closure plus a 1 s reopen-auction grace — is counted as
`crossed_explained` and excluded from the failure criterion. It remains
counted in `crossed` and printed in every report, exactly as out-of-span gaps
and scheduled closures are: anything the harness excuses stays visible. A
crossing outside those windows is still a failure, and the test suite pins
that a mid-session crossing is not excused. The grace is bounded by the
measured 9.9 ms by an ample margin and is not tuned to make a check pass.

*A guard that does not depend on the cause.* Independently of why a book
crosses, a crossed book must never reach the feature pipeline: its mid,
spread, microprice, queue imbalance and every depth statistic are
meaningless, and a model would train on them without complaint. `BookState`
now carries `crossed`/`locked` (columns the schema always had but the reader
discarded) and exposes `usable`. The feature engine treats a crossed book as
unusable: touch-derived features are nulled, the crossed mid never enters the
return series or realized-volatility windows, and `book_is_valid` goes false
so the pipeline marks the sample invalid — the same exclusion path as gap
windows and Phase A book-invalid periods. Trade-derived features continue
through a crossed book, since trades are unaffected by book inversion.
Locked books (bid == ask) are counted and reported but not excluded: a touch
where bid meets ask is degenerate, not impossible.

**Consequences.** MES 2026-07-15 passes with 193 explained crossings and
0 unexplained; MBT still passes the same session, so nothing was fixed at
another contract's expense. The guard is cause-agnostic, so if a future venue
crosses for an entirely different reason the features are still protected
while the validation still reports it. The honest limitation: mbp-10 is a
derived aggregation, and only the `mbo` schema could confirm the halt-period
book at order granularity — worth buying if crossings ever appear *outside* a
no-match window, and not worth buying now.

---

## ADR-020: Roll boundaries are an exclusion class, derived from symbology

**Date:** 2026-08-02 · **Status:** accepted

**Context.** A continuous futures series is a splice. `MBT.c.0` maps to one
instrument on one date and a different one the next, so the price series
carries a discontinuity at each roll that is a *contract change*, not a
market move. A feature lookback or label horizon spanning that point mixes
two instruments and yields a return that never happened. MBT rolls monthly,
so a twelve-month backfill contains twelve of them.

Two ways to find rolls. **Detect** them from price jumps, or **derive** them
from the vendor's symbology. Detection is a classifier with two failure
modes: it fires on genuine market moves (a real 2% gap looks like a roll)
and misses quiet rolls (adjacent contracts often trade within a tick of each
other, so the roll produces no jump at all). Derivation has neither: the
symbology API states exactly which instrument the series maps to over each
date interval, so a roll is a bookkeeping fact with an exact timestamp, and
resolving it costs nothing.

**Decision.** Roll boundaries are derived from `symbology.resolve`
(`continuous -> instrument_id`), stored as an append-only record alongside
the data (`data/vendor/databento/rolls/<symbol>.jsonl`, carrying the date,
splice timestamp, and both instrument ids) so they survive into every
downstream run rather than being re-derived inconsistently.

Exclusion joins the **existing** invalidity path — the one already serving
gap windows, book-invalid periods and halt-period crossings — rather than
forming a parallel mechanism, and the windows are unioned with the others
before any time is summed (the CLAUDE.md interval rule; this is its fourth
instance). Roll exclusions are reported as their own count and duration in
validation output, so an unexpectedly large exclusion is visible rather than
absorbed into a coverage percentage.

**The window orientation is the subtle part, and the intuitive answer is
backwards.** A sample at `t` reads `[t - lookback, t + horizon]`, so it is
unsafe exactly when that span contains the roll `R`:

    t - lookback < R <= t + horizon   <=>   R - horizon <= t < R + lookback

The exclusion on *sample time* therefore runs backward by the **label
horizon** and forward by the **feature lookback** — not the reverse. It is
the label reaching forward across the splice that endangers most samples;
the lookback only endangers the few immediately after. Both bounds come from
the configured values, so extending the horizon set widens the exclusion
automatically (same discipline as the embargo, ADR-015).

**Consequences.** Any continuous series added later needs its boundaries
resolved before its first feature run, and the resolution is free. The
exclusion is narrow — 16 minutes per roll at current settings, about 1.6
hours a year for a monthly-rolling contract — so it costs almost no data
while removing an error that would otherwise be invisible and systematic.
The alternative of trading outright contracts instead of a continuous series
removes rolls entirely but fragments history at every expiry; that trade-off
is deferred until there is a reason to make it.

## ADR-021: The backfill is four months, not six — and shipped as two

**Date:** 2026-08-02 · **Status:** accepted

**Context.** Stage C.6 priced a six-month MBT backfill at **$159.66** against
a ~$95 expectation. The overshoot was not a pricing surprise but a modelling
error: C.5 had projected from a measured per-day cost multiplied by 21
trading days a month, an equity convention. CME crypto futures run Sunday
17:00 CT to Friday 16:00 CT, so a month bills across ~30 calendar days, not
21. The per-day rate was roughly right; the days-per-month multiplier was
wrong by 40%.

The cap had just been raised from $25 to $120 for this purchase, and at $120
it **refused the six-month request**. That refusal was the gate working: it
caught a real estimation error before the money moved. Six months was
affordable only by raising the cap a second time, immediately after the cap
had demonstrated its value by stopping something. Raising a limit *because*
it fired converts a control into a formality — the number stops meaning
anything if it yields every time it binds.

**Decision.** Buy **four months (2026-04..07) at $97.08** and leave the cap
at $120. Four months fits with $16.69 to spare and supports two walk-forward
folds at 3-month train / 1-month test instead of three. The trades schema
stays: dropping it saves $4.10 of a $97 purchase and costs every
trade-derived feature, which is not an economy. Months are bought one at a
time so a failure costs one month, not the range.

**What actually happened.** April and May were delivered and validated. June
was priced, committed, and **OOM-killed mid-download** by a defect in our own
fetch path (ADR-022) after its $35.51 had been charged to the ledger. With
that charge recorded, $38.66 remained against $57.48 needed, so the range
could not be finished without raising the cap the decision above exists to
protect. **The stage stopped at two months rather than raise it.** July was
never attempted.

**Consequences.** The research range is April–May 2026: 224 million MBP-10
events over 989 hours of scheduled-open time, two consecutive months of one
season. That is thinner than the two folds this decision was sized for, and
the Phase B honesty rule binds harder, not softer, for it. Resuming June and
July requires first reconciling the June charge against the Databento
invoice — the client exposes no usage endpoint, so only the portal can say
whether the killed stream was billed. If it was not, reversing that entry
makes all four months affordable under the unchanged cap.

**Rejected: raise the cap to ~$170 and buy six months.** The reason the
number existed was to stop exactly this. A cap that is raised whenever it
binds is documentation, not a control — the same failure ADR-017 recorded
when a guardrail arrived after the action it guarded.

## ADR-022: Vendor downloads stream to disk; the ledger records intent, not delivery

**Date:** 2026-08-02 · **Status:** accepted

**Context.** The Databento client's `timeseries.get_range()` returns a
`DBNStore` that, called without `path`, materialises the **entire** response
in memory before any of it is written. A day of MBT is ~140 MB and hides
this. A month is not: Stage C.7's June MBP-10 request (76.3 GB billable)
reached 9.1 GB resident on a 14 GiB machine and was killed by the kernel —
`Out of memory: Killed process 4144248 (python3) anon-rss:9105252kB` — after
its $35.51 had already been committed to the spend ledger. Memory
consumption scaled with the size of the *purchase*, so the most expensive
request was the one guaranteed to fail.

Separately, this exposed an ambiguity in the ledger. ADR-017 commits the
quoted cost **before** the request is issued, deliberately: a gate that
records spending after the fact cannot prevent it, and a crash between
request and record would under-count. The cost of that choice is that a
request which is charged but never delivered leaves the ledger *over*-stating
spend, with nothing on disk to reconcile against, and the client offers no
usage endpoint to settle it — `metadata` has `get_cost` and
`get_billable_size`, both pre-request estimates, and nothing that reports
what was actually billed.

**Decision.** Two rules.

1. **Every vendor download streams to a path.** `get_range` is always called
   with `path=`, never buffered and written afterward. Peak memory is a chunk,
   independent of the size of the range bought. Both `fetch_day` and
   `fetch_range` route through one helper so the property cannot hold in one
   place and lapse in the other.

2. **Bytes land on a `.partial` sibling and are renamed only on success.** A
   process killed mid-download leaves an obviously-incomplete file, never a
   truncated file at the real path. This matters because the immutability
   guard is `target.exists()`: a truncated file at the real path would be
   read as a finished download by every later run, and silently short data is
   worse than absent data.

**Consequences.** The ledger is explicitly a record of **intent to spend**,
not of delivered bytes, and must be read that way. It is conservative by
construction — it can over-count but never under-count — and the direction of
that error is the safe one for a control whose job is to refuse. Where the
two diverge, the vendor invoice is authoritative, and reconciliation is a
manual step because the vendor gives us no programmatic way to do it. A
charge with no file on disk is therefore a **finding requiring operator
reconciliation before retry**, never something a script may assume it can
re-issue: the gate cannot detect a double-spend it has already recorded.

## ADR-023: Futures costs are per contract, converted at each sample's own notional

**Date:** 2026-08-03 · **Status:** accepted

**Context.** The cost model expressed every venue as basis points per leg,
which is exactly right for crypto spot: an exchange charging 0.4% of notional
charges the same rate whatever the price. Futures do not work that way. CME
charges a fixed sum per contract per side, and its cost *as a rate* depends on
the notional it is divided by — price times the contract multiplier.

Stage C.8 arrived with the premise that "CME micro bitcoin futures cost under
one basis point round trip", reasoning from MES at $2.99 per round turn on
~$34,000 of notional (0.88 bps). That premise does not survive contact with
MBT's own specification. MBT is **0.1 BTC**, so at the April–May 2026 prices in
this range its notional is **$7,608**, not $34,000. Its CME exchange fee is
also **$1.15 per side against MES's $0.35**. A 3.3x larger fee on a 5.2x
smaller notional is roughly 17x the rate: **5.33 bps round turn resting, 7.26
bps crossing**, against the sub-1 bp assumed.

The venue config already carried a bps approximation with a comment saying the
schema could not express per-contract dollars and that Phase C must fix it.
Leaving that in place would have priced MBT with a number that was never
charged, in the one stage whose entire question was whether a 3 bps edge clears
its costs.

**Decision.** `CostModel` carries two fee shapes. Percentage venues keep
`fee_bps_per_leg`. Futures venues declare `fee_usd_per_contract_per_side` plus
a `contract_multiplier` on the instrument, and the model converts to bps **at
each sample's own entry price** — so a range over which price moves 26% is
costed at 4.86 bps at one end and 6.13 bps at the other, rather than at a
single average that is wrong everywhere but the middle. `entry_mid` is stored
on every sample for exactly this purpose.

A per-contract model with no price **raises**. There is no notional to divide
by, and any default would invent a cost that was never charged; a sample whose
entry price is unknown is an invalid sample, not a cheap one.

CME does not split maker and taker fees — the exchange charges the same to add
or remove liquidity — so for these venues the two modes differ only in whether
the touch spread is paid. That is not a technicality: MBT's mean touch spread
is **1.93 bps**, more than a third of the whole resting round turn, so calling
both modes "the fee" would hide the dominant difference between them.

**Consequences.** Every figure is sourced and dated in `config/venues.yaml`,
because every fee schedule in this project has been found stale at least once.
Two caveats travel with it: the exchange component rests on a **broker's
republication** of CME's schedule rather than CME directly, since the fee
finder is interactive and the PDF was not machine-readable at retrieval; and
**CME changed its schedule effective 2026-04-01, inside this data range**. Both
must be resolved before Phase C consumes these numbers with real capital.

**Rejected: keep one bps figure per venue and use the worse contract's.** That
is what the config did, and it is defensible for refusing to understate costs.
It cannot answer a question about whether a specific contract's edge clears its
specific costs, which is the only question that matters here.

## ADR-024: Fold count is reported, never manufactured

**Date:** 2026-08-03 · **Status:** accepted

**Context.** Two contiguous months of MBT span 61 days. At a 42-day train /
14-day test walk-forward window that yields two folds, and the second is
truncated — its test window runs five days past the end of the data, giving
43,340 samples against the first fold's 252,596. The obvious way to reach three
honest-looking folds is to shrink the windows.

That would be a lie told with arithmetic. Three folds cut from 61 days are not
three independent tests; they are three overlapping looks at one regime. As the
test span shrinks it also stops dominating the label horizon — at 14 days the
longest label (900 s) is 1/1344 of the window, which is comfortable, and the
ratio degrades fast as the window shrinks. A fold count is a property of the
data, and reporting it as anything else converts a data limitation into an
apparently-validated result.

**Decision.** `walk_forward_capacity` reports how many folds the data supports
at a **fixed, horizon-appropriate window size**, and returns the count with the
fold sizes so a truncated fold is visible rather than counted as whole. The
window is a constant chosen against the label horizon, never tuned against the
amount of data available. Where the count is small, the report says so in those
words rather than presenting the folds as sufficient.

**Consequences.** Stage C.8 reports **one clean fold**, not two and not three,
and states that six months would give three. This is recorded as a limitation
of the range, which is a purchasing decision (ADR-021), not a modelling one —
the fix is more data, not a smaller window.

## ADR-025: Training is memory-bounded by a declared stride, and the stride is part of the experiment

**Date:** 2026-08-03 · **Status:** accepted

**Context.** The training path holds the whole range in memory at once: a dict
of columns, a stacked feature matrix, and a per-horizon masked copy of that
matrix. At Phase B's scale — three venue-days, ~30,000 samples — this is
invisible. At 53 days of MBT it is 5.4 million samples, and the process was
**OOM-killed at 5.48 GB resident** on a 14 GiB machine already holding a
browser and three live recorders.

A first round of fixes helped and was not enough: reading one file at a time
instead of concatenating every day into one Arrow table and *then* building a
float64 dict (which held two full copies of the range), loading only the
columns training reads rather than all 70, and using float32 for features.
That took the projected peak from ~6.6 GB to the 5.48 GB at which it still
died. **Reducing a number is not the same as fitting under a limit**, and
reporting the reduction as "bounded" was wrong.

**Decision.** `load_samples` accepts a `stride` that keeps every nth retained
sample, applied per file so the full arrays are never built. Because samples
are event bars, striding by n is equivalent to having sampled every
`n x every_n` book updates: it coarsens the bar, it does not bias which moments
are chosen. Stage C.8 used stride 4 — 1.02M samples, ~0.56 GB of arrays.

**The stride is recorded in the report and the experiment log, as part of the
sampling description rather than as a footnote.** A coarser bar is a real
change to the experiment. A run that quietly trains on a quarter of its samples
and reports the sampling rule it did not use is not reproducible, and the
Phase B contract requires every run's configuration to be logged from the first
one precisely so a deflated Sharpe ratio can be computed honestly later.

**Consequences.** Because the stride changes the experiment, its effect must be
measured rather than assumed away. C.8 ran a **stride-1 control on 10 days**
(896,018 samples — the same memory footprint, a shorter range instead of a
coarser bar) and the AUC curve reproduced within 0.01 at every horizon, which
is what licensed the main run's conclusion. Any future stage using a stride
owes the same control, or it owes the caveat that bar width is an unexamined
alternative explanation for its result.

**Rejected: subsample randomly rather than by stride.** A random subsample of
event bars is not an event-bar rule at all, and could not be described as any
sampling scheme a live system would implement. A stride remains a rule the
execution path could actually run.

## ADR-026: Spread capture is judged per instrument, by spread minus adverse selection minus cost

**Date:** 2026-08-03 · **Status:** accepted

**Context.** Stage C.8 closed directional prediction. The natural next question
is whether the passive side pays instead — quote, earn the spread, avoid the
cost of crossing. A claim was made that it does not, anywhere reachable,
because fees exceed the spread. The evidence was two instruments: MBT at 1.93
bps of spread against 5.33 bps of cost, and full-size ES by estimate.

Both are among the tightest instruments available, which makes them the worst
possible basis for a claim about everything. The reason is structural: a fee
quoted per contract converts to a roughly constant number of basis points as
notional scales, because both numerator and denominator scale together. A
spread does not — it is set by competition among quoters, and on a thin
instrument it widens by orders of magnitude while the fee stays put. The
survey bears this out across a single venue: CME micro contracts on one day
range from 0.37 bps (MNQ) to 128 bps (MHG) of spread, a 350x span, against
costs spanning 0.41 to 6.2 bps. **The spread-to-cost ratio is a property of an
instrument, not a venue**, and a venue-level claim about it is a category error.

**Decision.** Spread capture is assessed per instrument, on three measured
quantities and never on the ratio alone:

1. **Time-weighted spread.** Weighted by how long each spread was quoted, not
   by how often the quote changed. A book that sits wide and then flickers
   tight reports a very different number under the two weightings, and only the
   time-weighted one describes what a resting order faced.
2. **Adverse selection** — signed post-trade mid drift. A resting quote is not
   filled by a random counterparty; it is filled by someone who wanted that
   side. Measuring how far the mid then moves in the aggressor's favour costs
   nothing but recorded data and requires no fill model.
3. **Round-trip cost**, per contract at the instrument's own notional
   (ADR-023).

The verdict is **spread − adverse − cost**, and a favourable ratio alone is
explicitly not sufficient: on a wide-spread instrument the adverse term grows
with the spread and can exceed it.

**Consequences.** Two guards travel with the framing.

**Activity is reported alongside the ratio, always.** Stage C.9 found CME micro
silver quoting a ratio of 3,889 on 69 quote updates in a day — one per twenty
minutes. Reporting that as an opportunity would be the same error as measuring
MBT on its expiry day (ADR-018): a number computed over a book that is not
really there. A ratio without an update count is not a finding.

**Every figure is an upper bound, because a fill is assumed.** Nothing in this
project models queue position, so the arithmetic credits every quote with a
fill it has not earned. Where the bound is negative — as it is on every
instrument measured in C.9, by 2.75 to 4.25 bps — the conclusion is safe
without a fill model. Where it is positive, the fill model becomes the next
question rather than an optional refinement, and the very attractiveness that
makes it positive is what puts other quotes ahead of yours in the queue.

**Rejected: settle it by buying depth data across many CME contracts.** Top of
book answers the spread question, and bbo-1s costs a fraction of mbp-10 — the
whole 16-contract survey was $0.78. Depth would be needed for queue modelling,
which is only worth buying once something survives this arithmetic. Buy the
cheap measurement that can rule out, before the expensive one that can refine.

## ADR-027: Validation distinguishes venue kinds, and only one of the three outcomes is an error

**Date:** 2026-08-04 · **Status:** accepted

**Context.** `config/venues.yaml` describes four venues, but they do not all get
their data the same way. Kraken, Coinbase and Hyperliquid are captured live into
`data/raw/venue=<venue>/` by `data/recorder/`. CME is not: it has no recorder,
no live gateway subscription, and never will in Stage 1 — its days are purchased
from Databento and land under `data/vendor/`.

The validator did not model that difference. It treated every configured venue as
replayable and raised `ValueError: No replay support for venue 'cme'` on the
first one it could not parse. Because venues are iterated in sorted order, `cme`
came first, so `python -m data.validate --date 2026-08-03` aborted **before
validating anything** — three healthy venues went unscored because of the one
venue that was never going to have raw capture. The failure was silent in the
worst way available to it: not silent in output, but silent in consequence, since
an operator seeing a traceback learns nothing about the three days that did not
get checked.

The tempting fix — drop `cme` from the venue list — is wrong. Vendor days still
need validating on the dates they cover, and a venue that is invisible to the
validator is a venue nobody notices has stopped being validated.

**Decision.** `VenueConfig` carries an explicit `kind`: `recorder` or `vendor`.
It defaults to `recorder`, so an undeclared venue is one this project believes it
is capturing live — a missing declaration surfaces loudly rather than quietly
removing a venue from validation.

A run then has exactly three outcomes per venue-scope, and they are kept apart:

1. **Replay it** — a recorder venue with recorded data for the date.
2. **Skip it, and say why** — nothing to score. Permanent and normal for a
   vendor venue swept into a default run; ordinary for a recorder venue on a
   date before it was switched on. **Never an error**, and the reason names
   which of the two it is.
3. **Fail loudly** — a venue declared `recorder` with no parser behind it, or an
   unknown venue key. `VenueConfigurationError`, exit code 2, distinct from the
   exit code for "nothing to do" so a scripted caller can tell a
   misconfiguration from an empty archive.

Deciding all of this happens up front, in `data/validate/scope.py`, before any
replay begins. The plan is data, so the three outcomes are unit-testable without
replaying a day, and skips are printed before the first long replay starts rather
than being inferred afterwards from absence.

**Consequences.** Skipped venues are written into `report.md`, not merely printed.
A section listing two venues where three were expected has to say what happened to
the third; otherwise the permanent record of a run cannot be distinguished from
the record of a run where a venue quietly dropped out.

Vendor venues are scored only when named explicitly with `--venue`. A default
sweep skips them. This is not squeamishness about cost — it is that streaming
stored DBN is a different operation from replaying a day of raw capture, and the
stored range files run to 3.7 GB each; doing that on every `make validate` would
be a nasty surprise. Named explicitly, `python -m data.validate --venue cme
--date YYYY-MM-DD` scores the stored day files through
`data.databento.validate`, which until now had no caller anywhere in the
repository. Multi-day `range=` files stay out of the per-day loop and keep their
own entry point, because scoring one day out of a month means streaming the whole
month.

`logs/validation_summary.json` stays recorder-only. The desktop coverage panel
consumes it through generated types, and a vendor day is scored on different
quantities — coverage against scheduled-open time rather than the calendar day,
no checksum, no snapshot cadence. Mixing the two shapes into one array would
either lie about a vendor day or force nullable fields on every recorder day.

**Rejected: infer the kind from whether raw data exists.** It is the same
mistake one level down. "No raw directory" is indistinguishable from "the
recorder has not started yet", "the disk was remounted", and "someone deleted
it" — and each of those should behave differently. The kind is a declaration
about how a venue works, so it is declared.

## ADR-028: Session markers are ordered by their clock, never by their position in the file

**Date:** 2026-08-04 · **Status:** accepted

**Context.** `sessions.jsonl` records one line per recorder lifecycle boundary,
appended by the recorder process itself. During a restart **two processes append
to that one file**: the outgoing process writes its `end` while shutting down,
and the incoming process writes its `start` as soon as it is up. Whichever wins
the race lands first. On disk, from the 2026-08-01T07:26:17 restart:

```
{"venue":"kraken","event":"start","ts_ns":1785569177909450362}
{"venue":"kraken","event":"end",  "ts_ns":1785569177581971000}
```

The `end` is 327 ms *earlier* than the `start` written above it. The timestamps
are correct; only the line order is wrong. This is not a defect to be prevented —
there is no cheap way to make two independent processes agree on write order, and
locking a shutdown path behind a file lock is a worse idea than tolerating
unordered lines.

Read sequentially, that sequence pairs the wrong markers. It reports a 602 ms
**unclean termination** where the reality is a graceful systemd restart, and it
loses the 327 ms clean downtime gap entirely. Kind matters more than duration
here: `unclean` is the signature of a crash, OOM kill or power loss, and one
appearing in a report is a reason to go looking.

**Decision.** Markers are ordered by `ts_ns` before pairing, with `end` breaking
ties ahead of `start` at an identical timestamp — a restart ends before it
begins, and the opposite reading would invent an unclean termination out of a
zero-length stop. **File order carries no information and is never consulted.**
`read_sessions` still returns lines in file order; imposing the clock is the
derivation's job, so any future reader that streams rather than loads inherits
the same requirement rather than a fixed-up input.

Alongside it, an invariant on `GapRecord` itself: a gap window cannot run
backwards. Any gap from any source, feed or derived, raises `NegativeGapError`
if `reconnect_ns < disconnect_ns`. Zero-length stays legal — a reconnect within
the clock's resolution is real.

**Consequences.** The invariant is deliberately unreachable once ordering is by
the clock, which is the point. The code it replaces was `if marker.ts_ns >
pending_end.ts_ns:` — a guard that **silently dropped** an inverted pair. That
guard would have hidden precisely the corruption worth knowing about, and it
would have hidden it twice over, because `merge_windows` also filters inverted
windows: a negative gap disappears from the coverage union while still being
counted in its per-kind total, so the two would disagree with nothing to show
why. This is the same shape as the Stage 1.6 span-clamping invariant and the
CLAUDE.md union-before-summing rule — a list, an arithmetic step, no check, and a
plausible wrong number that never raises.

`NegativeGapError` is a `RuntimeError`, not a `ValueError`, specifically so
pydantic does not fold it into a `ValidationError`. A caller catching
`ValidationError` for ordinary malformed input must not also swallow a
corruption signal.

**This was caught before it produced a wrong number, not after.** Every previous
defect in this family was found downstream of a published figure. Reconciling
the record: the only validation runs published after the mis-ordered pair was
written (2026-08-01 07:28 and 07:32 UTC) report 3 recorder-downtime gaps
totalling 21,919,496 ms and 0 unclean terminations, which is exactly what
clock-ordered pairing yields. File-order pairing would have published 2 downtime
gaps plus 1 unclean of 602 ms, totalling 21,919,770 ms. The sort has been in
`derive_downtime_gaps` since the commit that introduced it (2f94b53,
2026-08-01), predating the first out-of-order pair by six hours. Nothing
downstream consumed a bad pairing. What was missing was not the sort — it was
the statement of *why* the sort is load-bearing, the tie-break, and the assertion
that would fire if either were ever removed.

## ADR-029: Universes are built point-in-time, from what was listed at the sample's start

**Date:** 2026-08-04 · **Status:** accepted

**Context.** A pairs study measures whether price relationships between assets
hold. The obvious way to pick assets — take today's liquid symbols and pull
their history — deletes every asset that died inside the sample. Those are not
a random subset. They are precisely the ones whose relationships broke, which
is the quantity being measured. The bias does not merely inflate the result; it
points directly at the conclusion.

Measured on this stage's own sample: of the top 60 symbols by quote volume in
2021-08, **twelve stopped trading before 2026-07** — one in five. A universe
screened on today's liquidity contains none of them, so it would never test a
relationship that ended, while keeping every relationship that survived. The
measured decay of cointegration would then be an artefact of the screen.

**Decision.** The universe is **the symbols that had bars in the sample's first
month, ranked by that month's quote volume.** Every clause matters: not today's
symbols, not symbols with a complete series, not symbols still trading. Members
that die mid-sample stay in and their price series simply ends — that is not a
data-quality problem to patch, it is the event the study most needs to see.

This requires a source that remembers dead assets. `data.binance.vision` does:
`FTTUSDT`, `LUNAUSDT`, `SRMUSDT`, `BUSDUSDT` and `WAVESUSDT` all still resolve
(verified 2026-08-04). Kraken's `AssetPairs` and Coinbase's `products`
enumerate only live products, so **neither may ever be used to select a
universe** — only to cross-check prices. Kraken additionally caps its OHLC
endpoint at 720 candles and cannot carry a multi-year sample at all.

**Consequences.** The caveat travels with the result rather than being assumed
away: this rests on Binance not purging delisted directories. Five known-dead
symbols surviving is evidence, not a guarantee, and a symbol purged before the
check ran would be invisible to the check itself.

**A second bias the survivorship fix does not cover, and must be handled
separately: ticker reuse.** `LUNAUSDT` has an unbroken run of monthly files and
is nonetheless two different assets — Terra collapsed in May 2022 and Terra 2.0
relaunched on the same ticker while the old chain became `LUNCUSDT`. Read
naively the series is continuous; in truth it is a splice across a 177,400x
single-bar jump. No cointegration test interprets that correctly and none
complains, because a splice looks like a structural break and a structural
break looks like a relationship that decayed. Any single-bar move beyond a
factor of five excludes the symbol entirely. The threshold is deliberately
blunt — on a top-sixty asset, 5x in a day is never a market move, and subtle
detectors for this class of defect fail subtly.

**Rejected: truncate a spliced series at the splice.** It keeps whichever side
happened to be longer and silently changes which asset the symbol denotes
partway through the study.

## ADR-030: Screening reports raw hits, expected-by-chance, and corrected hits — always all three

**Date:** 2026-08-04 · **Status:** accepted

**Context.** Testing *N* pairs at α=0.05 produces about `0.05 * N` rejections
when nothing is cointegrated at all. This stage tested 1,653 pairs, so **roughly
83 "discoveries" are the null hypothesis behaving normally.** That is more than
enough to fill a results table, sort it by Sharpe, and publish the top ten. The
pairs-trading literature is full of exactly this artifact, and a raw count is
indistinguishable from a real finding unless the correction is applied *before*
anyone looks at the winners.

**Decision.** Every screen reports three numbers together and never one without
the others:

1. **raw hits** at the threshold,
2. **expected false positives** = α × pairs tested,
3. **hits surviving Benjamini-Hochberg** at q=0.05.

Benjamini-Hochberg over Bonferroni deliberately. Bonferroni controls the
probability of even one false rejection and on 1,653 tests is so conservative
that an ordinary real relationship cannot survive it. What a trading decision
needs is "how much of this table is noise", and that is the false discovery rate
BH bounds.

**Consequences.** The gap between raw and corrected *is* the finding, so the raw
count is never deleted as superseded. This stage's two windows show why: the
formation window gave 432 raw against 82.7 expected (a real 5.2x excess, 180
surviving BH), while the holdout gave **91 raw against 77.0 expected and zero
surviving**. Reporting only corrected counts would have hidden that the second
window is pure noise; reporting only raw counts would have made it look like 91
discoveries.

Test orientation is fixed by symbol order and never chosen by which direction
scores better. Engle-Granger is not symmetric, so silently taking the better of
`coint(y,x)` and `coint(x,y)` doubles the tests actually run while leaving the
count handed to the correction unchanged — a screen quietly doubling its own
false discovery rate. Johansen's lag order and deterministic-trend order are
fixed for the same reason: searching them would be another uncounted dimension.

## ADR-031: A free public archive is a source, not a venue — the third venue kind

**Date:** 2026-08-04 · **Status:** accepted

**Context.** Stage C.9.1 established that data reaching this project has a
*kind*, and that validation must route on it (ADR-027). Two kinds existed:
`recorder` (captured live into `data/raw/`) and `vendor` (purchased into
`data/vendor/`). C.10 introduced a third thing that is neither: free public
historical bars, downloaded once, from a venue that in Binance's case **cannot
legally be traded from British Columbia at all**.

Left undeclared it would default to `recorder`, and `make validate` would abort
on it exactly as it did on `cme`.

**Decision.** A third kind, `archive`, and — more consequentially — archives
live in their own `sources` block rather than under `venues`.

A `VenueConfig` carries a matching-engine endpoint, a book depth, a snapshot
protocol and **a fee schedule**. Every one of those is meaningless for an
archive, and the fee schedule is worse than meaningless: publishing `fee_tiers`
for Binance would invite a future reader to model a strategy on fees no order of
ours could ever pay. The model refuses any `kind` other than `archive` in that
block, so a recorder or vendor stream cannot be smuggled in without its
endpoints and fees being validated.

What an archive shares with a venue is the routing: `plan_run` lists configured
archives among its skipped entries on a default sweep, so an archive that stops
being refreshed is visible rather than merely absent — ADR-027's rule that a
source invisible to the validator is one nobody notices has stopped working.

**Consequences.** Provenance is per file, not per config entry: source, venue,
dataset, symbol, interval, period, URL, byte count, sha256 and retrieval date,
appended to `data/vendor/archive/manifest.jsonl` **after** the bytes land and
the checksum is taken. That ordering is the opposite of the vendor spend
ledger's (ADR-022), and deliberately so — the ledger commits a charge before the
request because the charge happens whether or not the bytes arrive. Nothing is
spent here, so the record can wait for proof.

`venue` and `source` are separate fields because they are separate things.
Binance dumps carry Binance prints, but the dump endpoint is its own artefact
and can be revised, or stop being published, independently of the exchange.

## ADR-032: Strategies are ranked by break-even transaction cost, not by return

**Date:** 2026-08-04 · **Status:** accepted

**Context.** Three stages have now died on the same arithmetic — C.8 on
directional prediction, C.9 on spread capture, and the executable half of C.10 —
and in every case the deciding quantity was cost per trade against edge per
trade, not the size of the edge. A return figure cannot express that. A pair
returning 20% a year that stops being profitable above 5 bps per round trip is
unreachable from every venue this project can use; one returning 8% that
survives to 200 bps is tradeable everywhere, Kraken spot at its punitive 40 bps
maker included.

**Decision.** The primary ranking metric is **break-even transaction cost**: the
round-trip cost in basis points at which a strategy's net return reaches zero,
computed as `2 * gross_return / one_way_turns` in bps. Return, Sharpe and
turnover are reported as context beneath it.

Two conventions make the number comparable across strategies. Gross exposure is
normalised to one unit across both legs, so entering transacts one unit one-way
and exiting another, and a cost figure is always a *round-trip rate on one unit
of capital* — 3.0 bps at Hyperliquid maker, 80.0 bps at Kraken base-tier spot.
And a strategy that loses money before costs reports a break-even of **zero, not
a negative number**: there is no cost at which it becomes profitable, and a
negative value invites being read as a threshold.

**Consequences.** The metric earned itself immediately by separating two
failures that a return column would have merged. C.10's break-even costs of
300–550 bps sit 100–180x above Hyperliquid's 3 bps — the turnover fix worked
exactly as intended and **cost stopped being the binding constraint**. The
strategy still failed, on persistence and on executability. Had the stage been
judged on returns alone, "40% a year gross" would have read as a success and the
real reasons for the failure would have been invisible.

**A break-even is only as meaningful as the trade count under it**, so a power
floor accompanies the ranking — this stage used ≥20 trades and ≥250 scored bars,
which 43 of 175 pairs cleared. Unfiltered, the table was led by a pair returning
128.7% a year on a leg dead since 2025-09. The floor is applied to the headline
and the unfiltered table is kept beside it, because dropping thin results
silently would be its own dishonesty and the gap between the two rankings is
informative.
