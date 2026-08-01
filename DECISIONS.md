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
