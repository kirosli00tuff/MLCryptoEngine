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
