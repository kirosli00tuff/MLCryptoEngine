# Findings report

This is the findings document for MLCryptoEngine. The validation harness
(`make validate`) appends a dated section below each time it runs. Human-written
analysis goes at the top of a dated section; machine-written metrics tables are
appended by `data/validate/`.

## Phase A acceptance criteria

Phase A is accepted when **all** of the following hold, measured by the validation
harness over recorded data:

1. A full day of Kraken data and a full day of Coinbase data each reconstruct through
   `data/book/` with **zero unexplained crossed-book events**. Crossed or locked books
   that coincide with a logged reconnect gap are explained; any other occurrence fails.
2. Valid-book coverage is **full-day outside logged reconnect gaps** — every second of
   the day is either covered by a valid book or attributable to a gap recorded in the
   recorder's `gaps.jsonl` sidecar.
3. Sequence validation reports **no unexplained sequence gaps** — every gap corresponds
   to a logged disconnect/reconnect window.
4. Reconstructed top-of-book agrees with venue-provided snapshots wherever the venue
   supplies them within tick-size tolerance.

## Measured results

The sections below are empty until data has been recorded and validated. Each
validation run appends a dated section with the measured values.

### Data volume by venue and symbol

(no data recorded yet)

### Book reconstruction error rates

(no data recorded yet)

### Feed gap statistics

(no data recorded yet)

### Latency percentiles

(no data recorded yet)

---

<!-- validation runs are appended below this line; do not edit past here by hand -->

## Validation run — 2026-07-30 15:30 UTC

### coinbase — 2026-07-30 — **FAIL**

- ✗ BTC-USD: coverage outside gaps 0.03% < 99.9%
- ✗ ETH-USD: coverage outside gaps 0.03% < 99.9%

Messages: **997** · recorded span: 24s · feed gaps: 28 (32402 ms)

Channels: `heartbeats`: 24 · `l2_data`: 872 · `market_trades`: 98 · `subscriptions`: 3

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 432 | 1 | 0 (0) | 0 (0) | 0 (0) | 0 | 0.03% | 0.03% | 0 (0) | 457 |
| ETH-USD | 438 | 1 | 0 (0) | 0 (0) | 0 (0) | 0 | 0.03% | 0.03% | 0 (0) | 463 |

| inter-message arrival | count |
|---|---|
| 0–0.01 ms | 1 |
| 0.01–0.05 ms | 33 |
| 0.05–0.1 ms | 15 |
| 0.1–0.5 ms | 33 |
| 0.5–1 ms | 17 |
| 1–5 ms | 131 |
| 5–10 ms | 78 |
| 10–50 ms | 589 |
| 50–100 ms | 94 |
| 100–500 ms | 5 |
| 500–1000 ms | 0 |
| 1000–5000 ms | 0 |
| 5000–30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 237.729 ms

### kraken — 2026-07-30 — **FAIL**

- ✗ BTC/USD: coverage outside gaps 0.03% < 99.9%
- ✗ ETH/USD: coverage outside gaps 0.03% < 99.9%

Messages: **7747** · recorded span: 24s · feed gaps: 0 (0 ms)

Channels: `book`: 7705 · `heartbeat`: 24 · `status`: 1 · `subscribe`: 4 · `trade`: 13

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 3292 | 1 | 0 (0) | 0 (0) | 0 (0) | 0 | 0.03% | 0.03% | 0 (0) | 3316 |
| ETH/USD | 4411 | 1 | 0 (0) | 0 (0) | 0 (0) | 0 | 0.03% | 0.03% | 0 (0) | 4435 |

| inter-message arrival | count |
|---|---|
| 0–0.01 ms | 6 |
| 0.01–0.05 ms | 2784 |
| 0.05–0.1 ms | 1228 |
| 0.1–0.5 ms | 953 |
| 0.5–1 ms | 308 |
| 1–5 ms | 1504 |
| 5–10 ms | 423 |
| 10–50 ms | 460 |
| 50–100 ms | 61 |
| 100–500 ms | 19 |
| 500–1000 ms | 0 |
| 1000–5000 ms | 0 |
| 5000–30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 0.1 ms · p90 ≤ 10 ms · p99 ≤ 100 ms · max 263.255 ms

## Stage 1 implementation summary — 2026-07-30

Implementation of every Stage 1 deliverable is complete. All quality gates pass:
`make lint`, `make typecheck` (mypy strict, 38 files), `make test` (27 tests),
and the desktop frontend compiles clean (`tsc` + vite build). Phase A itself
remains open until full recorded days clear the validation harness.

### Commands the operator should run first

```bash
make install                 # sync the uv environment + pre-commit hooks
make record                  # start capturing Kraken + Coinbase public feeds
make telemetry               # in a second terminal: latency probes (leave running)
# ...after at least one full UTC day of recording:
make validate                # reconstruct books, score quality, append to report.md
make desktop                 # desktop app (first run compiles Rust; see desktop/README.md)
```

### Files created

- Root: `CLAUDE.md`, `README.md`, `progress.md`, `report.md`, `DECISIONS.md`,
  `.gitignore`, `.env.example`, `.python-version`, `pyproject.toml`,
  `.pre-commit-config.yaml`, `Makefile`
- `config/`: `default.yaml`, `venues.yaml`
- `data/`: `__init__.py`, `config.py`, `logsetup.py`
- `data/recorder/`: `__init__.py`, `base.py`, `kraken.py`, `coinbase.py`,
  `writer.py`, `reader.py`, `gaps.py`, `service.py`, `__main__.py`
- `data/book/`: `__init__.py`, `types.py`, `builder.py`, `kraken_checksum.py`,
  `kraken_parse.py`, `coinbase_parse.py`, `emit.py`
- `data/store/`: `__init__.py`, `parquet_writer.py`, `query.py`
- `data/validate/`: `__init__.py`, `stats.py`, `replay.py`, `report_writer.py`,
  `__main__.py`
- `ops/`: `__init__.py`; `ops/telemetry/`: `__init__.py`, `probe.py`,
  `store.py`, `service.py`, `__main__.py`; `ops/deploy/.gitkeep`
- `research/{features,labels,models,notebooks}/.gitkeep`, `backtest/.gitkeep`,
  `engine/.gitkeep`
- `desktop/`: `README.md`, `package.json`, `tsconfig.json`, `vite.config.ts`,
  `index.html`
- `desktop/src/`: `main.tsx`, `App.tsx`, `styles.css`,
  `lib/{types,tauri,format,experience}.ts`, `state/AppData.tsx`,
  `components/{icons,Sidebar,Header,EmptyState,Toggle,Toasts,Sparkline,VenueStatusCard,LatencyNowTile,DataFootprintTile,CortexPanel,ExperiencePanel,LatencyChart,CoverageHeatmap,LogStream}.tsx`,
  `pages/{DashboardPage,SettingsPage}.tsx`
- `desktop/src-tauri/`: `Cargo.toml`, `build.rs`, `tauri.conf.json`,
  `capabilities/default.json`, `src/{main,lib,process,settings,inventory,logs}.rs`,
  `icons/{gen_icons.py,32x32.png,128x128.png,icon.png}`
- `tests/`: `conftest.py`, `test_config.py`, `test_book_builder.py`,
  `test_store_roundtrip.py`, `test_recorder_reconnect.py`,
  `fixtures/{README.md,kraken_messages.ndjson,coinbase_messages.ndjson}`

### Dependencies added

- Python core: polars, duckdb, pyarrow, pydantic, pydantic-settings,
  websockets, orjson, uvloop, httpx, structlog, **zstandard** and **pyyaml**
  (the latter two are additions beyond the spec list: required for zstd NDJSON
  capture and YAML config loading)
- Python dev: pytest, pytest-asyncio, ruff, mypy, pre-commit, types-pyyaml
- Python research: lightgbm, scikit-learn, numpy, matplotlib, jupyterlab
- npm: react, react-dom, @tauri-apps/api, recharts; dev: vite,
  @vitejs/plugin-react, typescript, tailwindcss, @tailwindcss/vite,
  @tauri-apps/cli, @types/react, @types/react-dom
- Rust crates: tauri 2, tauri-build, tauri-plugin-window-state, serde,
  serde_json, libc

### Unable to complete in the implementation environment

- **Rust compilation of the desktop backend**: no Rust toolchain or webkit2gtk
  development libraries were available. The Rust code is written and reviewed
  but unverified by a compiler; the first `make desktop` run may need small
  fixups. Ubuntu/Fedora prerequisites are documented in `desktop/README.md`.
- **A full recorded day**: only a ~25-second live sample was captured to prove
  the pipeline end to end (7,747 Kraken + 997 Coinbase messages, zero checksum
  failures, zero sequence gaps). Phase A acceptance requires full-day
  recordings, which only the operator's always-on machine can produce.

### Measured so far (from the live sample)

- Kraken replay: 7,703 book updates across BTC/USD + ETH/USD with **zero CRC32
  checksum failures** and zero crossed/locked books.
- Coinbase replay: sequence-contiguous, valid books on both symbols.
- First latency probes recorded (see `data/processed/latency/`); rolling
  percentiles will stabilize once telemetry runs continuously.
