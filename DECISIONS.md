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

**Consequences.** MES is the CME contract worth backfilling despite costing
47x more per day; a year of MES history is ~$791, a real but affordable
decision to make deliberately rather than by accident. MBT remains worth
collecting cheaply for cross-asset and longer-horizon work (>=30 s), and its
own capability entry now says exactly that. Any future contract added to
this venue needs its own measurement pass before it can be credited with
anything — price is not evidence of resolution, and here it understated the
gap by a factor of five.
