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

## Validation run — 2026-07-30 19:45 UTC

### coinbase — 2026-07-30 — **FAIL**

- ✗ BTC-USD: coverage outside gaps 0.03% < 99.9%
- ✗ ETH-USD: coverage outside gaps 0.03% < 99.9%

Messages: **997** · recorded span: 24s · feed gaps in span: 0 (0 ms, unioned)

⚠ 28 gap record(s) totalling 32402 ms fall outside the recorded span (e.g. an earlier failed session the same day) — excluded from coverage, listed here so they are never silently dropped.

Channels: `heartbeats`: 24 · `l2_data`: 872 · `market_trades`: 98 · `subscriptions`: 3

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 432 | 1 | 0 (0) | 0 (0) | 0 (0) | 0 | 0.03% | 0.03% | 0 (0) | 457 |
| ETH-USD | 438 | 1 | 0 (0) | 0 (0) | 0 (0) | 0 | 0.03% | 0.03% | 0 (0) | 463 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 1 |
| 0.01 to 0.05 ms | 33 |
| 0.05 to 0.1 ms | 15 |
| 0.1 to 0.5 ms | 33 |
| 0.5 to 1 ms | 17 |
| 1 to 5 ms | 131 |
| 5 to 10 ms | 78 |
| 10 to 50 ms | 589 |
| 50 to 100 ms | 94 |
| 100 to 500 ms | 5 |
| 500 to 1000 ms | 0 |
| 1000 to 5000 ms | 0 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 237.729 ms

## Validation run — 2026-07-30 19:57 UTC

### coinbase — 2026-07-30 — **FAIL**

- ✗ BTC-USD: coverage outside gaps 19.39% < 99.9%
- ✗ ETH-USD: coverage outside gaps 19.39% < 99.9%

Messages: **5882** · recorded span: 16753s · feed gaps in span: 0 (0 ms, unioned)

⚠ 28 gap record(s) totalling 32402 ms fall outside the recorded span (e.g. an earlier failed session the same day) — excluded from coverage, listed here so they are never silently dropped.

Channels: `heartbeats`: 148 · `l2_data`: 5331 · `market_trades`: 397 · `subscriptions`: 6

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 2809 | 2 | 0 (0) | 0 (0) | 0 (0) | 0 | 19.39% | 19.39% | 1 (1) | 19564 |
| ETH-USD | 2518 | 2 | 0 (0) | 0 (0) | 0 (0) | 0 | 19.39% | 19.39% | 1 (1) | 19273 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 1 |
| 0.01 to 0.05 ms | 119 |
| 0.05 to 0.1 ms | 88 |
| 0.1 to 0.5 ms | 168 |
| 0.5 to 1 ms | 67 |
| 1 to 5 ms | 450 |
| 5 to 10 ms | 929 |
| 10 to 50 ms | 3545 |
| 50 to 100 ms | 488 |
| 100 to 500 ms | 25 |
| 500 to 1000 ms | 0 |
| 1000 to 5000 ms | 0 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 1 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 1.66061e+07 ms

### kraken — 2026-07-30 — **FAIL**

- ✗ BTC/USD: coverage outside gaps 19.39% < 99.9%
- ✗ ETH/USD: coverage outside gaps 19.39% < 99.9%

Messages: **29725** · recorded span: 16753s · feed gaps in span: 0 (0 ms, unioned)

Channels: `book`: 29515 · `heartbeat`: 147 · `status`: 2 · `subscribe`: 8 · `trade`: 53

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 12544 | 2 | 0 (0) | 0 (0) | 0 (0) | 0 | 19.39% | 19.39% | 1 (1) | 29299 |
| ETH/USD | 16967 | 2 | 0 (0) | 0 (0) | 0 (0) | 0 | 19.39% | 19.39% | 1 (1) | 33721 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 347 |
| 0.01 to 0.05 ms | 14528 |
| 0.05 to 0.1 ms | 3194 |
| 0.1 to 0.5 ms | 1762 |
| 0.5 to 1 ms | 948 |
| 1 to 5 ms | 4379 |
| 5 to 10 ms | 1501 |
| 10 to 50 ms | 2335 |
| 50 to 100 ms | 503 |
| 100 to 500 ms | 226 |
| 500 to 1000 ms | 0 |
| 1000 to 5000 ms | 0 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 1 |

p50 ≤ 0.05 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 1.66072e+07 ms

## Validation run — 2026-08-01 06:11 UTC

### coinbase — 2026-08-01 — **FAIL**

- ✗ BTC-USD: coverage outside gaps 0.00% < 99.9%
- ✗ ETH-USD: coverage outside gaps 4.39% < 99.9%

Messages: **158188** · recorded span: 4000s · feed gaps in span: 0 (0 ms, unioned and clamped to the span)

Channels: `heartbeats`: 4000 · `l2_data`: 138159 · `market_trades`: 16029

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 158,188 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 0 | 0 | 0 (0) | n/a | n/a | 0 (0) | 0 | 0.00% | 0.00% | 0 (0) | 76797 |
| ETH-USD | 61822 | 2 | 0 (0) | n/a | n/a | 0 (0) | 0 | 4.39% | 4.39% | 1 (1) | 69362 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 2457 |
| 0.05 to 0.1 ms | 1741 |
| 0.1 to 0.5 ms | 3401 |
| 0.5 to 1 ms | 814 |
| 1 to 5 ms | 13238 |
| 5 to 10 ms | 10742 |
| 10 to 50 ms | 114021 |
| 50 to 100 ms | 10509 |
| 100 to 500 ms | 1260 |
| 500 to 1000 ms | 4 |
| 1000 to 5000 ms | 0 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 827.436 ms

### kraken — 2026-08-01 — **FAIL**

- ✗ kraken: declares CRC32 book checksums but 0 were verified — a zero checksum-failure count here is evidence of absence, not of integrity
- ✗ BTC/USD: coverage outside gaps 0.00% < 99.9%
- ✗ ETH/USD: coverage outside gaps 0.00% < 99.9%

Messages: **400355** · recorded span: 4000s · feed gaps in span: 0 (0 ms, unioned and clamped to the span)

Channels: `book`: 394925 · `heartbeat`: 3999 · `trade`: 1431

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 0 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 0 | 0 | n/a | 0 (0) | 0 | 0 (0) | 0 | 0.00% | 0.00% | 0 (0) | 183746 |
| ETH/USD | 0 | 0 | n/a | 0 (0) | 0 | 0 (0) | 0 | 0.00% | 0.00% | 0 (0) | 219179 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 230 |
| 0.01 to 0.05 ms | 165326 |
| 0.05 to 0.1 ms | 29809 |
| 0.1 to 0.5 ms | 29310 |
| 0.5 to 1 ms | 13519 |
| 1 to 5 ms | 79423 |
| 5 to 10 ms | 18648 |
| 10 to 50 ms | 40122 |
| 50 to 100 ms | 13968 |
| 100 to 500 ms | 9924 |
| 500 to 1000 ms | 73 |
| 1000 to 5000 ms | 2 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 0.5 ms · p90 ≤ 50 ms · p99 ≤ 500 ms · max 1082.68 ms

## Validation run — 2026-08-01 06:22 UTC

### coinbase — 2026-08-01 — **FAIL**

- ✗ BTC-USD: coverage outside gaps 4.63% < 99.9%
- ✗ ETH-USD: coverage outside gaps 4.63% < 99.9%

Messages: **158188** · recorded span: 4000s · feed gaps in span: 0 (0 ms, unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-31 23:37:51Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `heartbeats`: 4000 · `l2_data`: 138159 · `market_trades`: 16029

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 158,188 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 72797 | 0 | 0 (0) | n/a | n/a | 0 (0) | 0 | 4.63% | 4.63% | 0 (0) | 76797 |
| ETH-USD | 65360 | 2 | 0 (0) | n/a | n/a | 0 (0) | 0 | 4.63% | 4.63% | 2 (1) | 69362 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 2457 |
| 0.05 to 0.1 ms | 1741 |
| 0.1 to 0.5 ms | 3401 |
| 0.5 to 1 ms | 814 |
| 1 to 5 ms | 13238 |
| 5 to 10 ms | 10742 |
| 10 to 50 ms | 114021 |
| 50 to 100 ms | 10509 |
| 100 to 500 ms | 1260 |
| 500 to 1000 ms | 4 |
| 1000 to 5000 ms | 0 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 827.436 ms

### kraken — 2026-08-01 — **FAIL**

- ✗ BTC/USD: coverage outside gaps 4.63% < 99.9%
- ✗ ETH/USD: coverage outside gaps 4.63% < 99.9%

Messages: **400355** · recorded span: 4000s · feed gaps in span: 0 (0 ms, unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-31 22:04:41Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `book`: 394925 · `heartbeat`: 3999 · `trade`: 1431

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 394,925 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 179746 | 0 | n/a | 0 (0) | 179746 | 0 (0) | 0 | 4.63% | 4.63% | 0 (0) | 183746 |
| ETH/USD | 215179 | 0 | n/a | 0 (0) | 215179 | 0 (0) | 0 | 4.63% | 4.63% | 0 (0) | 219179 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 230 |
| 0.01 to 0.05 ms | 165326 |
| 0.05 to 0.1 ms | 29809 |
| 0.1 to 0.5 ms | 29310 |
| 0.5 to 1 ms | 13519 |
| 1 to 5 ms | 79423 |
| 5 to 10 ms | 18648 |
| 10 to 50 ms | 40122 |
| 50 to 100 ms | 13968 |
| 100 to 500 ms | 9924 |
| 500 to 1000 ms | 73 |
| 1000 to 5000 ms | 2 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 0.5 ms · p90 ≤ 50 ms · p99 ≤ 500 ms · max 1082.68 ms

## Validation run — 2026-08-01 06:52 UTC

### coinbase — 2026-07-31 — **PASS**

Messages: **3408568** · recorded span: 86400s · feed gaps in span: 5 (6155 ms, unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-30 23:44:41Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `heartbeats`: 86296 · `l2_data`: 3045990 · `market_trades`: 276267 · `subscriptions`: 15

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 3,408,568 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 1588608 | 12 | 0 (0) | n/a | n/a | 0 (0) | 0 | 100.00% | 100.01% | 12 (7) | 1675019 |
| ETH-USD | 1457355 | 15 | 0 (0) | n/a | n/a | 0 (0) | 0 | 100.00% | 100.01% | 15 (9) | 1543769 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 25905 |
| 0.05 to 0.1 ms | 41308 |
| 0.1 to 0.5 ms | 110639 |
| 0.5 to 1 ms | 40381 |
| 1 to 5 ms | 348633 |
| 5 to 10 ms | 379535 |
| 10 to 50 ms | 2169801 |
| 50 to 100 ms | 267663 |
| 100 to 500 ms | 24659 |
| 500 to 1000 ms | 25 |
| 1000 to 5000 ms | 14 |
| 5000 to 30000 ms | 2 |
| >30000 ms | 2 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 38404.1 ms

### kraken — 2026-07-31 — **PASS**

Messages: **17489620** · recorded span: 86400s · feed gaps in span: 6 (12883 ms, unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-30 22:01:05Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `book`: 17361566 · `heartbeat`: 86344 · `status`: 6 · `subscribe`: 24 · `trade`: 41680

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 17,361,554 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 7745333 | 6 | n/a | 0 (0) | 7745333 | 0 (0) | 0 | 100.00% | 100.02% | 6 (0) | 7831738 |
| ETH/USD | 9616221 | 6 | n/a | 0 (0) | 9616221 | 0 (0) | 0 | 100.00% | 100.02% | 6 (2) | 9702626 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 22092 |
| 0.01 to 0.05 ms | 7740487 |
| 0.05 to 0.1 ms | 1824728 |
| 0.1 to 0.5 ms | 1427096 |
| 0.5 to 1 ms | 533409 |
| 1 to 5 ms | 3205844 |
| 5 to 10 ms | 933898 |
| 10 to 50 ms | 1394727 |
| 50 to 100 ms | 276566 |
| 100 to 500 ms | 130237 |
| 500 to 1000 ms | 497 |
| 1000 to 5000 ms | 38 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 0 |

p50 ≤ 0.1 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 3530.27 ms

## Validation run — 2026-08-01 07:28 UTC

### coinbase — 2026-08-01 — **FAIL**

- ✗ BTC-USD: coverage outside gaps 41.60% < 99.9%
- ✗ ETH-USD: coverage outside gaps 41.60% < 99.9%

Messages: **190844** · recorded span: 26825s · feed gaps in span: 0 (0 ms) · recorder downtime: 3 (21919496 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 21919496 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-31 23:37:51Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `heartbeats`: 4901 · `l2_data`: 168626 · `market_trades`: 17308 · `subscriptions`: 9

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 190,844 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 89186 | 3 | 0 (0) | n/a | n/a | 0 (0) | 0 | 31.05% | 41.60% | 3 (1) | 116013 |
| ETH-USD | 79432 | 5 | 0 (0) | n/a | n/a | 0 (0) | 0 | 31.05% | 41.60% | 5 (2) | 106261 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 3126 |
| 0.05 to 0.1 ms | 2263 |
| 0.1 to 0.5 ms | 3959 |
| 0.5 to 1 ms | 996 |
| 1 to 5 ms | 14501 |
| 5 to 10 ms | 12037 |
| 10 to 50 ms | 139132 |
| 50 to 100 ms | 13186 |
| 100 to 500 ms | 1636 |
| 500 to 1000 ms | 4 |
| 1000 to 5000 ms | 2 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 1 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 2.19203e+07 ms

### kraken — 2026-08-01 — **FAIL**

- ✗ BTC/USD: coverage outside gaps 41.72% < 99.9%
- ✗ ETH/USD: coverage outside gaps 41.72% < 99.9%

Messages: **447842** · recorded span: 26900s · feed gaps in span: 0 (0 ms) · recorder downtime: 3 (21919496 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 21919496 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-31 22:04:41Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `book`: 441279 · `heartbeat`: 4974 · `status`: 3 · `subscribe`: 12 · `trade`: 1574

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 441,273 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 201222 | 3 | n/a | 0 (0) | 201222 | 0 (0) | 0 | 31.13% | 41.72% | 3 (1) | 228125 |
| ETH/USD | 240051 | 3 | n/a | 0 (0) | 240051 | 0 (0) | 0 | 31.13% | 41.72% | 3 (2) | 266954 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 365 |
| 0.01 to 0.05 ms | 179311 |
| 0.05 to 0.1 ms | 33909 |
| 0.1 to 0.5 ms | 31710 |
| 0.5 to 1 ms | 15598 |
| 1 to 5 ms | 89401 |
| 5 to 10 ms | 21169 |
| 10 to 50 ms | 46502 |
| 50 to 100 ms | 16940 |
| 100 to 500 ms | 12800 |
| 500 to 1000 ms | 130 |
| 1000 to 5000 ms | 5 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 1 |

p50 ≤ 0.5 ms · p90 ≤ 50 ms · p99 ≤ 500 ms · max 2.19205e+07 ms

## Validation run — 2026-08-01 07:32 UTC

### coinbase — 2026-08-01 — **FAIL**

- ✗ BTC-USD: coverage outside gaps 7.95% < 99.9%
- ✗ ETH-USD: coverage outside gaps 7.95% < 99.9%

Messages: **198642** · recorded span: 27044s · feed gaps in span: 0 (0 ms) · recorder downtime: 3 (21919496 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 21919496 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-31 23:37:51Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `heartbeats`: 5121 · `l2_data`: 175944 · `market_trades`: 17568 · `subscriptions`: 9

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 198,642 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 93044 | 3 | 0 (0) | n/a | n/a | 0 (0) | 0 | 5.93% | 7.95% | 3 (1) | 120091 |
| ETH-USD | 82892 | 5 | 0 (0) | n/a | n/a | 0 (0) | 0 | 5.93% | 7.95% | 5 (2) | 109941 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 3219 |
| 0.05 to 0.1 ms | 2589 |
| 0.1 to 0.5 ms | 4262 |
| 0.5 to 1 ms | 1179 |
| 1 to 5 ms | 16048 |
| 5 to 10 ms | 12721 |
| 10 to 50 ms | 142698 |
| 50 to 100 ms | 14196 |
| 100 to 500 ms | 1722 |
| 500 to 1000 ms | 4 |
| 1000 to 5000 ms | 2 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 1 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 2.19203e+07 ms

### kraken — 2026-08-01 — **FAIL**

- ✗ BTC/USD: coverage outside gaps 8.07% < 99.9%
- ✗ ETH/USD: coverage outside gaps 8.07% < 99.9%

Messages: **458331** · recorded span: 27121s · feed gaps in span: 0 (0 ms) · recorder downtime: 3 (21919496 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 21919496 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-07-31 22:04:41Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `book`: 451499 · `heartbeat`: 5195 · `status`: 3 · `subscribe`: 12 · `trade`: 1622

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 451,493 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 206249 | 3 | n/a | 0 (0) | 206249 | 0 (0) | 0 | 6.02% | 8.07% | 3 (1) | 233373 |
| ETH/USD | 245244 | 3 | n/a | 0 (0) | 245244 | 0 (0) | 0 | 6.02% | 8.07% | 3 (2) | 272368 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 408 |
| 0.01 to 0.05 ms | 181651 |
| 0.05 to 0.1 ms | 34776 |
| 0.1 to 0.5 ms | 32038 |
| 0.5 to 1 ms | 16161 |
| 1 to 5 ms | 92063 |
| 5 to 10 ms | 21710 |
| 10 to 50 ms | 48237 |
| 50 to 100 ms | 17732 |
| 100 to 500 ms | 13411 |
| 500 to 1000 ms | 137 |
| 1000 to 5000 ms | 5 |
| 5000 to 30000 ms | 0 |
| >30000 ms | 1 |

p50 ≤ 0.5 ms · p90 ≤ 50 ms · p99 ≤ 500 ms · max 2.19205e+07 ms
