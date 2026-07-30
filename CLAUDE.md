# CLAUDE.md — MLCryptoEngine operating manual

Read this file at the start of every coding session. It is the contract for how work
happens in this repository.

## Project purpose

MLCryptoEngine is a personal quantitative research project building a machine learning
engine trained on tick-level historical market data to detect short-horizon
microstructure patterns. Detected patterns are ultimately executed from a VPS placed in
the same cloud region as the exchange matching engine. The operator is a solo developer
in British Columbia, Canada, and every design decision is sized for one person operating
real capital carefully.

## Hard constraints

These shape every design decision. Do not violate them, and do not "temporarily" work
around them.

- Binance, Bybit, OKX and KuCoin are not legally available to Canadian residents. Target
  venues are Kraken spot (engine at Equinix London, reach via AWS eu-west-2), Coinbase
  Advanced Trade (AWS us-east-1), and CME micro futures via Interactive Brokers with
  Databento market data.
- Realistic latency tier is 5 to 100 ms round trip. Do not design for microseconds. Do
  not design for 500 ms.
- Micro-pattern edges are single-digit basis points, so fee modeling and queue position
  are first-class concerns, not afterthoughts.
- No large language model call ever sits in the live decision path.

Stage 1 contains zero trading logic and zero order placement. Public market data only.
No API key with trade or withdraw permission is used or requested anywhere in this
stage.

## Directory map

```
config/          YAML configuration: runtime defaults and per-venue metadata (endpoints, fees, depth)
data/            Python package for the data pipeline; also holds raw/ and processed/ output (gitignored)
data/recorder/   Asyncio WebSocket recorders that write raw exchange-native messages losslessly
data/book/       Order book reconstruction: replay raw feeds into a maintained L2 book
data/store/      Parquet writer and DuckDB-backed query helpers over recorded data
data/validate/   Validation harness that scores recorded data quality and writes report.md
research/        Feature engineering, labeling, model training, and notebooks (Phase B+)
backtest/        Simulation with measured latency distributions and true fee tiers (Phase C)
engine/          Live execution engine (Phase D+); risk code lives here — see review rule below
ops/             Operational tooling: deploy/ for VPS provisioning, telemetry/ for latency probes
desktop/         Tauri 2 desktop app: Rust backend (src-tauri/) and React TypeScript frontend (src/)
tests/           Pytest suite; tests/fixtures/ holds small recorded exchange messages
```

## Tech stack and why

- **Python 3.11+ / asyncio** — the data pipeline is I/O bound; asyncio with `uvloop`
  handles multiple WebSocket feeds in one process with low overhead.
- **uv** — dependency management; fast, lockfile-based, reproducible environments.
- **polars + pyarrow + Parquet** — columnar storage and fast scans over tick data;
  Parquet with zstd is the canonical at-rest format for processed outputs.
- **duckdb** — zero-server SQL over Parquet partitions for research queries and
  coverage reporting.
- **pydantic + pydantic-settings** — typed configuration with environment overlay and
  fail-fast validation at startup.
- **websockets + httpx + orjson** — WebSocket feeds, REST latency probes, and fast JSON.
- **zstandard** — streaming zstd compression for raw NDJSON capture.
- **structlog** — structured JSON logs that the desktop app can tail and filter.
- **lightgbm + scikit-learn** (research group) — gradient boosted trees are the Phase B
  baseline; cheap to train, strong on tabular microstructure features.
- **Tauri 2 (Rust) + React + TypeScript + Tailwind** — small-footprint native desktop
  shell; Rust backend supervises Python processes and tails logs, frontend renders the
  dashboard. No Electron, no Redux, no design framework beyond Tailwind.

## Coding standards

- Python 3.11+ only. Type hints are required on all function signatures.
- `ruff format` and `ruff check` must pass clean. `mypy` must pass clean.
- Anything with logic gets a pytest test. Real tests, not smoke tests.
- Keep files focused and small; prefer many small modules over one large one.
- Errors are handled explicitly; never silently swallow an exception.
- Raw recorded data is immutable. Processed outputs must always be regenerable from raw.

## Non-negotiable rules

1. **`engine/` risk code requires line-by-line human review.** Nothing under `engine/`
   that touches order placement, position sizing, or kill switches may be merged or run
   with real capital without the operator reading every line.
2. **Secrets never enter the repo.** No API keys, tokens, or passwords in source, config
   files, fixtures, or commit history. Secrets come only from environment variables
   (see `.env.example`). The config layer raises at startup if a required secret is
   missing.
3. **Backtests must use measured latency, not guessed constants.** `ops/telemetry/`
   runs continuously alongside the recorder precisely so that Phase C has a real
   per-venue latency distribution to feed into hftbacktest. Backtests using a constant
   latency assumption systematically overstate performance: they miss the tail of slow
   round trips, which is exactly where queue position is lost and fills degrade.

## Git commit conventions

Conventional commits: `<type>: <description>` where type is one of
`feat, fix, refactor, docs, test, chore, perf, ci`. Imperative mood, lower case,
no trailing period. Body optional, used to explain *why* when the change is not
self-evident. One deliverable or coherent change per commit.

## Read these first

- `progress.md` — where the project is right now: phase checklist and dated running log.
- `DECISIONS.md` — append-only architecture decision log; read before revisiting any
  settled question.
