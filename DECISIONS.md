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
