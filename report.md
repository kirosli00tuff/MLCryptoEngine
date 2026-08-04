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

## Phase B research run — 2026-08-01 17:45 UTC

**Caveat, read first: these results rest on 1 day(s) of data spanning ~1 volatility regime(s). They validate the pipeline; they are NOT evidence of edge. Microstructure relationships shift with regime, session, and venue conditions — a signal fitted on one day is fitted on that day's regime.**

Data range: 2026-07-31 · sampling: event bars, every 50 book updates · features: 42 · labels: fixed-horizon [100, 500, 1000, 5000, 30000] ms + triple-barrier (pt/sl 2.0x rvol_30s, 30 s time limit) · cost assumptions: coinbase: maker 40.0 bps, taker 60.0 bps per leg (tier 0) + spread / kraken: maker 25.0 bps, taker 40.0 bps per leg (tier 0) + spread · trade signing: {'kraken': 'venue_flag', 'coinbase': 'tick_rule'}

Leakage suite: PASS (...                                                                      [100%])

### coinbase BTC-USD

Valid samples: 31,640

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 31640 | 0.886 | maker | -80.00 | 0.060 | -79.99 | -79.99 | n/a |
| 100 ms | 31640 | 0.886 | taker | -120.01 | 0.060 | -120.00 | -120.01 | n/a |
| 500 ms | 31640 | 0.831 | maker | -79.99 | 0.123 | -79.96 | -79.98 | n/a |
| 500 ms | 31640 | 0.831 | taker | -120.01 | 0.123 | -119.97 | -120.00 | n/a |
| 1000 ms | 31640 | 0.788 | maker | -79.98 | 0.169 | -79.93 | -79.97 | n/a |
| 1000 ms | 31640 | 0.788 | taker | -120.00 | 0.169 | -119.95 | -119.99 | n/a |
| 5000 ms | 31638 | 0.684 | maker | -79.90 | 0.359 | -79.84 | -79.95 | n/a |
| 5000 ms | 31638 | 0.684 | taker | -119.92 | 0.359 | -119.86 | -119.97 | n/a |
| 30000 ms | 31629 | 0.552 | maker | -79.80 | 0.510 | -79.82 | -79.91 | n/a |
| 30000 ms | 31629 | 0.552 | taker | -119.82 | 0.510 | -119.84 | -119.93 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.886 · 500 ms: 0.831 · 1000 ms: 0.788 · 5000 ms: 0.684 · 30000 ms: 0.552

Top feature importances (fold-averaged): time_since_trade_ms 0.04 · signed_vol_1s 0.04 · depth_ask_1 0.03 · xv_leadlag_p500 0.03 · xv_leadlag_m500 0.03 · xv_leadlag_p100 0.03 · xv_leadlag_m100 0.03 · ofi_deep_1s 0.03 · depth_bid_2 0.03 · spread_bps 0.03

### coinbase ETH-USD

Valid samples: 29,024

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 29024 | 0.814 | maker | -80.00 | 0.114 | -79.98 | -79.99 | n/a |
| 100 ms | 29024 | 0.814 | taker | -120.12 | 0.114 | -120.10 | -120.12 | n/a |
| 500 ms | 29024 | 0.756 | maker | -79.99 | 0.204 | -79.94 | -79.98 | n/a |
| 500 ms | 29024 | 0.756 | taker | -120.12 | 0.204 | -120.07 | -120.11 | n/a |
| 1000 ms | 29024 | 0.722 | maker | -79.98 | 0.266 | -79.92 | -79.97 | n/a |
| 1000 ms | 29024 | 0.722 | taker | -120.10 | 0.266 | -120.04 | -120.10 | n/a |
| 5000 ms | 29022 | 0.618 | maker | -79.89 | 0.437 | -79.86 | -79.95 | n/a |
| 5000 ms | 29022 | 0.618 | taker | -120.01 | 0.437 | -119.98 | -120.07 | n/a |
| 30000 ms | 29014 | 0.531 | maker | -79.82 | 0.509 | -79.77 | -79.97 | n/a |
| 30000 ms | 29014 | 0.531 | taker | -119.95 | 0.509 | -119.90 | -120.10 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.814 · 500 ms: 0.756 · 1000 ms: 0.722 · 5000 ms: 0.618 · 30000 ms: 0.531

Top feature importances (fold-averaged): time_since_trade_ms 0.04 · depth_ask_1 0.04 · spread_bps 0.03 · ofi_best_1s 0.03 · xv_leadlag_p500 0.03 · signed_vol_1s 0.03 · dwp_minus_mid 0.03 · vwap_minus_mid_5s 0.03 · slope_ask 0.03 · xv_leadlag_0 0.03

### kraken BTC/USD

Valid samples: 153,942

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 153942 | 0.940 | maker | -49.97 | 0.095 | -49.93 | -49.96 | n/a |
| 100 ms | 153942 | 0.940 | taker | -80.03 | 0.095 | -80.00 | -80.03 | n/a |
| 500 ms | 153942 | 0.901 | maker | -49.93 | 0.150 | -49.84 | -49.93 | n/a |
| 500 ms | 153942 | 0.901 | taker | -79.99 | 0.150 | -79.90 | -79.99 | n/a |
| 1000 ms | 153942 | 0.878 | maker | -49.89 | 0.185 | -49.78 | -49.91 | n/a |
| 1000 ms | 153942 | 0.878 | taker | -79.95 | 0.185 | -79.84 | -79.97 | n/a |
| 5000 ms | 153934 | 0.809 | maker | -49.66 | 0.348 | -49.54 | -49.83 | n/a |
| 5000 ms | 153934 | 0.809 | taker | -79.72 | 0.348 | -79.60 | -79.89 | n/a |
| 30000 ms | 153913 | 0.668 | maker | -49.33 | 0.531 | -49.42 | -49.87 | n/a |
| 30000 ms | 153913 | 0.668 | taker | -79.39 | 0.531 | -79.48 | -79.94 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.940 · 500 ms: 0.901 · 1000 ms: 0.878 · 5000 ms: 0.809 · 30000 ms: 0.668

Top feature importances (fold-averaged): depth_ask_1 0.06 · time_since_trade_ms 0.05 · xv_diff_z 0.05 · spread_bps 0.04 · slope_ask 0.04 · xv_mid_diff_bps 0.04 · rvol_1s 0.03 · ofi_best_1s 0.03 · slope_bid 0.03 · dwp_minus_mid 0.03

### kraken ETH/USD

Valid samples: 191,243

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 191243 | 0.852 | maker | -49.96 | 0.270 | -49.91 | -49.95 | n/a |
| 100 ms | 191243 | 0.852 | taker | -80.30 | 0.270 | -80.25 | -80.29 | n/a |
| 500 ms | 191243 | 0.812 | maker | -49.89 | 0.360 | -49.80 | -49.89 | n/a |
| 500 ms | 191243 | 0.812 | taker | -80.23 | 0.360 | -80.14 | -80.23 | n/a |
| 1000 ms | 191243 | 0.790 | maker | -49.81 | 0.415 | -49.73 | -49.85 | n/a |
| 1000 ms | 191243 | 0.790 | taker | -80.15 | 0.415 | -80.07 | -80.19 | n/a |
| 5000 ms | 191231 | 0.709 | maker | -49.63 | 0.501 | -49.56 | -49.74 | n/a |
| 5000 ms | 191231 | 0.709 | taker | -79.97 | 0.501 | -79.90 | -80.08 | n/a |
| 30000 ms | 191195 | 0.579 | maker | -49.59 | 0.525 | -49.69 | -49.76 | n/a |
| 30000 ms | 191195 | 0.579 | taker | -79.93 | 0.525 | -80.03 | -80.10 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.852 · 500 ms: 0.812 · 1000 ms: 0.790 · 5000 ms: 0.709 · 30000 ms: 0.579

Top feature importances (fold-averaged): depth_ask_1 0.12 · depth_bid_1 0.06 · slope_ask 0.06 · depth_ask_2 0.05 · xv_diff_z 0.04 · slope_bid 0.04 · spread_bps 0.04 · dwp_minus_mid 0.04 · depth_bid_2 0.04 · ofi_best_1s 0.03

## Phase B research run — 2026-08-02 01:05 UTC

**Caveat, read first: these results rest on 1 day(s) of data spanning ~1 volatility regime(s). They validate the pipeline; they are NOT evidence of edge. Microstructure relationships shift with regime, session, and venue conditions — a signal fitted on one day is fitted on that day's regime.**

Data range: 2026-07-31 · sampling: event bars, every 50 book updates · features: 42 · labels: fixed-horizon [100, 500, 1000, 5000, 30000, 60000, 300000, 900000] ms + triple-barrier (pt/sl 2.0x rvol_30s, 30 s time limit) · cost assumptions: coinbase: maker 40.0 bps, taker 60.0 bps per leg (tier 0) + spread / hyperliquid: maker 1.5 bps, taker 4.5 bps per leg (tier 0) + spread / kraken: maker 40.0 bps, taker 80.0 bps per leg (tier 0) + spread · trade signing: {'kraken': 'venue_flag', 'coinbase': 'tick_rule', 'hyperliquid': 'venue_flag', 'cme': 'venue_flag'}

Venues in this run: kraken, coinbase. **hyperliquid was skipped — it has no
recorded data for 2026-07-31** (its recorder was activated 2026-08-01), and an
absent venue is reported as absent rather than as an empty result.

Leakage suite: PASS (...                                                                      [100%])

### coinbase BTC-USD

Valid samples: 30,172

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 30172 | 0.886 | maker | -80.00 | 0.063 | -79.99 | -79.99 | n/a |
| 100 ms | 30172 | 0.886 | taker | -120.01 | 0.063 | -120.00 | -120.01 | n/a |
| 500 ms | 30172 | 0.829 | maker | -79.99 | 0.126 | -79.96 | -79.98 | n/a |
| 500 ms | 30172 | 0.829 | taker | -120.00 | 0.126 | -119.98 | -120.00 | n/a |
| 1000 ms | 30172 | 0.786 | maker | -79.98 | 0.173 | -79.93 | -79.97 | n/a |
| 1000 ms | 30172 | 0.786 | taker | -120.00 | 0.173 | -119.95 | -119.99 | n/a |
| 5000 ms | 30170 | 0.684 | maker | -79.90 | 0.362 | -79.84 | -79.95 | n/a |
| 5000 ms | 30170 | 0.684 | taker | -119.91 | 0.362 | -119.86 | -119.97 | n/a |
| 30000 ms | 30161 | 0.551 | maker | -79.82 | 0.512 | -79.85 | -79.91 | n/a |
| 30000 ms | 30161 | 0.551 | taker | -119.84 | 0.512 | -119.87 | -119.92 | n/a |
| 60000 ms | 30150 | 0.534 | maker | -79.81 | 0.516 | -79.85 | -79.83 | n/a |
| 60000 ms | 30150 | 0.534 | taker | -119.83 | 0.516 | -119.87 | -119.85 | n/a |
| 300000 ms | 30061 | 0.550 | maker | -79.44 | 0.540 | -79.42 | -79.42 | n/a |
| 300000 ms | 30061 | 0.550 | taker | -119.46 | 0.540 | -119.44 | -119.44 | n/a |
| 900000 ms | 29838 | 0.596 | maker | -76.69 | 0.566 | -76.77 | -77.91 | n/a |
| 900000 ms | 29838 | 0.596 | taker | -116.71 | 0.566 | -116.79 | -117.92 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.886 · 500 ms: 0.829 · 1000 ms: 0.786 · 5000 ms: 0.684 · 30000 ms: 0.551 · 60000 ms: 0.534 · 300000 ms: 0.550 · 900000 ms: 0.596

Top feature importances (fold-averaged): time_since_trade_ms 0.04 · signed_vol_1s 0.04 · depth_ask_1 0.04 · xv_leadlag_p500 0.03 · xv_leadlag_m500 0.03 · xv_leadlag_p100 0.03 · xv_leadlag_m100 0.03 · slope_ask 0.03 · spread_bps 0.03 · depth_bid_2 0.03

### coinbase ETH-USD

Valid samples: 27,642

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 27642 | 0.816 | maker | -80.00 | 0.115 | -79.98 | -79.99 | n/a |
| 100 ms | 27642 | 0.816 | taker | -120.12 | 0.115 | -120.10 | -120.12 | n/a |
| 500 ms | 27642 | 0.759 | maker | -79.99 | 0.205 | -79.94 | -79.98 | n/a |
| 500 ms | 27642 | 0.759 | taker | -120.12 | 0.205 | -120.07 | -120.11 | n/a |
| 1000 ms | 27642 | 0.724 | maker | -79.97 | 0.265 | -79.92 | -79.97 | n/a |
| 1000 ms | 27642 | 0.724 | taker | -120.10 | 0.265 | -120.05 | -120.10 | n/a |
| 5000 ms | 27640 | 0.623 | maker | -79.88 | 0.436 | -79.84 | -79.95 | n/a |
| 5000 ms | 27640 | 0.623 | taker | -120.01 | 0.436 | -119.97 | -120.07 | n/a |
| 30000 ms | 27632 | 0.523 | maker | -79.87 | 0.505 | -79.83 | -79.97 | n/a |
| 30000 ms | 27632 | 0.523 | taker | -120.00 | 0.505 | -119.96 | -120.10 | n/a |
| 60000 ms | 27623 | 0.532 | maker | -79.74 | 0.519 | -79.77 | -79.96 | n/a |
| 60000 ms | 27623 | 0.532 | taker | -119.87 | 0.519 | -119.90 | -120.09 | n/a |
| 300000 ms | 27546 | 0.545 | maker | -79.23 | 0.539 | -79.23 | -80.28 | n/a |
| 300000 ms | 27546 | 0.545 | taker | -119.35 | 0.539 | -119.36 | -120.40 | n/a |
| 900000 ms | 27351 | 0.558 | maker | -77.36 | 0.559 | -77.48 | -80.86 | n/a |
| 900000 ms | 27351 | 0.558 | taker | -117.48 | 0.559 | -117.61 | -120.99 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.816 · 500 ms: 0.759 · 1000 ms: 0.724 · 5000 ms: 0.623 · 30000 ms: 0.523 · 60000 ms: 0.532 · 300000 ms: 0.545 · 900000 ms: 0.558

Top feature importances (fold-averaged): time_since_trade_ms 0.04 · depth_ask_1 0.04 · spread_bps 0.03 · xv_leadlag_p500 0.03 · xv_mid_diff_bps 0.03 · vwap_minus_mid_5s 0.03 · slope_ask 0.03 · ofi_best_1s 0.03 · xv_leadlag_m100 0.03 · signed_vol_1s 0.03

### kraken BTC/USD

Valid samples: 144,738

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 144738 | 0.941 | maker | -79.97 | 0.096 | -79.93 | -79.96 | n/a |
| 100 ms | 144738 | 0.941 | taker | -160.03 | 0.096 | -160.00 | -160.03 | n/a |
| 500 ms | 144738 | 0.901 | maker | -79.93 | 0.149 | -79.84 | -79.93 | n/a |
| 500 ms | 144738 | 0.901 | taker | -159.99 | 0.149 | -159.90 | -159.99 | n/a |
| 1000 ms | 144738 | 0.879 | maker | -79.89 | 0.184 | -79.78 | -79.90 | n/a |
| 1000 ms | 144738 | 0.879 | taker | -159.96 | 0.184 | -159.84 | -159.97 | n/a |
| 5000 ms | 144730 | 0.813 | maker | -79.67 | 0.345 | -79.53 | -79.82 | n/a |
| 5000 ms | 144730 | 0.813 | taker | -159.73 | 0.345 | -159.60 | -159.89 | n/a |
| 30000 ms | 144709 | 0.666 | maker | -79.35 | 0.522 | -79.46 | -79.86 | n/a |
| 30000 ms | 144709 | 0.666 | taker | -159.41 | 0.522 | -159.52 | -159.93 | n/a |
| 60000 ms | 144699 | 0.603 | maker | -79.20 | 0.545 | -79.57 | -79.97 | n/a |
| 60000 ms | 144699 | 0.603 | taker | -159.26 | 0.545 | -159.63 | -160.04 | n/a |
| 300000 ms | 144470 | 0.499 | maker | -80.50 | 0.504 | -80.97 | -80.89 | n/a |
| 300000 ms | 144470 | 0.499 | taker | -160.56 | 0.504 | -161.03 | -160.95 | n/a |
| 900000 ms | 143713 | 0.539 | maker | -79.09 | 0.554 | -80.55 | -83.03 | n/a |
| 900000 ms | 143713 | 0.539 | taker | -159.16 | 0.554 | -160.62 | -163.09 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.941 · 500 ms: 0.901 · 1000 ms: 0.879 · 5000 ms: 0.813 · 30000 ms: 0.666 · 60000 ms: 0.603 · 300000 ms: 0.499 · 900000 ms: 0.539

Top feature importances (fold-averaged): depth_ask_1 0.06 · time_since_trade_ms 0.05 · xv_diff_z 0.05 · spread_bps 0.04 · slope_ask 0.04 · xv_mid_diff_bps 0.04 · ofi_best_1s 0.03 · rvol_1s 0.03 · slope_bid 0.03 · dwp_minus_mid 0.03

### kraken ETH/USD

Valid samples: 179,719

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 179719 | 0.851 | maker | -79.96 | 0.270 | -79.91 | -79.95 | n/a |
| 100 ms | 179719 | 0.851 | taker | -160.30 | 0.270 | -160.25 | -160.30 | n/a |
| 500 ms | 179719 | 0.810 | maker | -79.89 | 0.360 | -79.80 | -79.89 | n/a |
| 500 ms | 179719 | 0.810 | taker | -160.23 | 0.360 | -160.15 | -160.24 | n/a |
| 1000 ms | 179719 | 0.790 | maker | -79.81 | 0.416 | -79.73 | -79.85 | n/a |
| 1000 ms | 179719 | 0.790 | taker | -160.15 | 0.416 | -160.07 | -160.19 | n/a |
| 5000 ms | 179707 | 0.707 | maker | -79.63 | 0.500 | -79.58 | -79.74 | n/a |
| 5000 ms | 179707 | 0.707 | taker | -159.97 | 0.500 | -159.92 | -160.09 | n/a |
| 30000 ms | 179671 | 0.571 | maker | -79.66 | 0.518 | -79.73 | -79.75 | n/a |
| 30000 ms | 179671 | 0.571 | taker | -160.01 | 0.518 | -160.07 | -160.10 | n/a |
| 60000 ms | 179659 | 0.538 | maker | -79.75 | 0.517 | -79.78 | -79.79 | n/a |
| 60000 ms | 179659 | 0.538 | taker | -160.09 | 0.517 | -160.12 | -160.14 | n/a |
| 300000 ms | 179493 | 0.528 | maker | -78.94 | 0.540 | -79.11 | -80.14 | n/a |
| 300000 ms | 179493 | 0.528 | taker | -159.29 | 0.540 | -159.45 | -160.49 | n/a |
| 900000 ms | 178751 | 0.552 | maker | -76.06 | 0.575 | -75.88 | -81.04 | n/a |
| 900000 ms | 178751 | 0.552 | taker | -156.40 | 0.575 | -156.22 | -161.39 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.851 · 500 ms: 0.810 · 1000 ms: 0.790 · 5000 ms: 0.707 · 30000 ms: 0.571 · 60000 ms: 0.538 · 300000 ms: 0.528 · 900000 ms: 0.552

Top feature importances (fold-averaged): depth_ask_1 0.11 · depth_bid_1 0.06 · slope_ask 0.06 · depth_ask_2 0.05 · slope_bid 0.04 · xv_diff_z 0.04 · spread_bps 0.04 · depth_bid_2 0.04 · dwp_minus_mid 0.04 · ofi_best_1s 0.03

## Phase B research run — 2026-08-03 20:38 UTC

**Caveat, read first: these results rest on 53 day(s) of data spanning ~10 volatility regime(s). They validate the pipeline; they are NOT evidence of edge. Microstructure relationships shift with regime, session, and venue conditions — a signal fitted on one day is fitted on that day's regime.**

Data range: 2026-04-01, 2026-04-02, 2026-04-03, 2026-04-05, 2026-04-06, 2026-04-07, 2026-04-08, 2026-04-09, 2026-04-10, 2026-04-12, 2026-04-13, 2026-04-14, 2026-04-15, 2026-04-16, 2026-04-17, 2026-04-19, 2026-04-20, 2026-04-21, 2026-04-22, 2026-04-23, 2026-04-24, 2026-04-26, 2026-04-27, 2026-04-28, 2026-04-29, 2026-04-30, 2026-05-01, 2026-05-03, 2026-05-04, 2026-05-05, 2026-05-06, 2026-05-07, 2026-05-08, 2026-05-10, 2026-05-11, 2026-05-12, 2026-05-13, 2026-05-14, 2026-05-15, 2026-05-17, 2026-05-18, 2026-05-19, 2026-05-20, 2026-05-21, 2026-05-22, 2026-05-24, 2026-05-25, 2026-05-26, 2026-05-27, 2026-05-28, 2026-05-29, 2026-05-30, 2026-05-31 · sampling: event bars, every 50 book updates, then every 4th retained sample kept for training (effective bar ~200 book updates) — memory-bounded, see ADR-025 · features: 42 · labels: fixed-horizon [100, 500, 1000, 5000, 30000, 60000, 300000, 900000] ms + triple-barrier (pt/sl 2.0x rvol_30s, 30 s time limit) · cost assumptions: cme: $2.02 per contract per side (= $4.04 round turn), converted to bps at each sample's own notional (price x multiplier {'MBT': 0.1, 'MES': 5.0}); taker additionally pays the touch spread · trade signing: {'kraken': 'venue_flag', 'coinbase': 'tick_rule', 'hyperliquid': 'venue_flag', 'cme': 'venue_flag'}

Leakage suite: PASS (...                                                                      [100%])

### cme MBT

Valid samples: 1,109,072

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 1109068 | 0.664 | maker | -5.32 | 0.250 | -5.26 | -5.30 | n/a |
| 100 ms | 1109068 | 0.664 | taker | -7.25 | 0.250 | -7.19 | -7.24 | n/a |
| 500 ms | 1109065 | 0.620 | maker | -5.32 | 0.341 | -5.25 | -5.31 | n/a |
| 500 ms | 1109065 | 0.620 | taker | -7.25 | 0.341 | -7.18 | -7.24 | n/a |
| 1000 ms | 1109059 | 0.600 | maker | -5.32 | 0.376 | -5.25 | -5.31 | n/a |
| 1000 ms | 1109059 | 0.600 | taker | -7.25 | 0.376 | -7.18 | -7.24 | n/a |
| 5000 ms | 1109022 | 0.551 | maker | -5.31 | 0.445 | -5.24 | -5.32 | n/a |
| 5000 ms | 1109022 | 0.551 | taker | -7.24 | 0.445 | -7.18 | -7.25 | n/a |
| 30000 ms | 1108858 | 0.521 | maker | -5.28 | 0.486 | -5.23 | -5.32 | n/a |
| 30000 ms | 1108858 | 0.521 | taker | -7.21 | 0.486 | -7.16 | -7.26 | n/a |
| 60000 ms | 1108687 | 0.516 | maker | -5.29 | 0.492 | -5.25 | -5.32 | n/a |
| 60000 ms | 1108687 | 0.516 | taker | -7.23 | 0.492 | -7.18 | -7.26 | n/a |
| 300000 ms | 1107056 | 0.508 | maker | -5.24 | 0.501 | -5.39 | -5.35 | n/a |
| 300000 ms | 1107056 | 0.508 | taker | -7.18 | 0.501 | -7.32 | -7.29 | n/a |
| 900000 ms | 1101582 | 0.501 | maker | -5.11 | 0.500 | -5.41 | -5.38 | n/a |
| 900000 ms | 1101582 | 0.501 | taker | -7.04 | 0.500 | -7.34 | -7.31 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.664 · 500 ms: 0.620 · 1000 ms: 0.600 · 5000 ms: 0.551 · 30000 ms: 0.521 · 60000 ms: 0.516 · 300000 ms: 0.508 · 900000 ms: 0.501

Top feature importances (fold-averaged): spread_bps 0.08 · time_since_trade_ms 0.07 · rvol_1s 0.06 · abs_ret_1s 0.05 · ofi_best_1s 0.05 · rvol_30s 0.04 · depth_ask_1 0.04 · micro_minus_mid 0.04 · ofi_deep_1s 0.04 · depth_bid_2 0.03

## Phase B research run — 2026-08-03 20:55 UTC

**Caveat, read first: these results rest on 10 day(s) of data spanning ~2 volatility regime(s). They validate the pipeline; they are NOT evidence of edge. Microstructure relationships shift with regime, session, and venue conditions — a signal fitted on one day is fitted on that day's regime.**

Data range: 2026-04-01, 2026-04-02, 2026-04-03, 2026-04-05, 2026-04-06, 2026-04-07, 2026-04-08, 2026-04-09, 2026-04-10, 2026-04-12 · sampling: event bars, every 50 book updates · features: 42 · labels: fixed-horizon [100, 500, 1000, 5000, 30000, 60000, 300000, 900000] ms + triple-barrier (pt/sl 2.0x rvol_30s, 30 s time limit) · cost assumptions: cme: $2.02 per contract per side (= $4.04 round turn), converted to bps at each sample's own notional (price x multiplier {'MBT': 0.1, 'MES': 5.0}); taker additionally pays the touch spread · trade signing: {'kraken': 'venue_flag', 'coinbase': 'tick_rule', 'hyperliquid': 'venue_flag', 'cme': 'venue_flag'}

Leakage suite: PASS (...                                                                      [100%])

### cme MBT

Valid samples: 896,018

| horizon | n | AUC | cost mode | model EV bps | model hit | regressor EV bps | last-sign EV bps | zero EV bps |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 896016 | 0.659 | maker | -5.79 | 0.259 | -5.72 | -5.77 | n/a |
| 100 ms | 896016 | 0.659 | taker | -7.99 | 0.259 | -7.92 | -7.97 | n/a |
| 500 ms | 896010 | 0.615 | maker | -5.79 | 0.350 | -5.71 | -5.77 | n/a |
| 500 ms | 896010 | 0.615 | taker | -7.99 | 0.350 | -7.92 | -7.97 | n/a |
| 1000 ms | 896005 | 0.591 | maker | -5.79 | 0.384 | -5.71 | -5.76 | n/a |
| 1000 ms | 896005 | 0.591 | taker | -7.99 | 0.384 | -7.92 | -7.96 | n/a |
| 5000 ms | 895966 | 0.544 | maker | -5.78 | 0.454 | -5.72 | -5.77 | n/a |
| 5000 ms | 895966 | 0.544 | taker | -7.99 | 0.454 | -7.92 | -7.98 | n/a |
| 30000 ms | 895826 | 0.515 | maker | -5.73 | 0.490 | -5.69 | -5.81 | n/a |
| 30000 ms | 895826 | 0.515 | taker | -7.93 | 0.490 | -7.89 | -8.01 | n/a |
| 60000 ms | 895677 | 0.508 | maker | -5.79 | 0.490 | -5.83 | -5.77 | n/a |
| 60000 ms | 895677 | 0.508 | taker | -7.99 | 0.490 | -8.03 | -7.97 | n/a |
| 300000 ms | 894171 | 0.489 | maker | -6.28 | 0.484 | -6.38 | -5.89 | n/a |
| 300000 ms | 894171 | 0.489 | taker | -8.48 | 0.484 | -8.58 | -8.09 | n/a |
| 900000 ms | 889624 | 0.490 | maker | -6.58 | 0.489 | -7.37 | -5.88 | n/a |
| 900000 ms | 889624 | 0.490 | taker | -8.77 | 0.489 | -9.57 | -8.08 | n/a |

Predictability decay (AUC by horizon): 100 ms: 0.659 · 500 ms: 0.615 · 1000 ms: 0.591 · 5000 ms: 0.544 · 30000 ms: 0.515 · 60000 ms: 0.508 · 300000 ms: 0.489 · 900000 ms: 0.490

Top feature importances (fold-averaged): spread_bps 0.09 · time_since_trade_ms 0.07 · rvol_1s 0.06 · ofi_best_1s 0.05 · abs_ret_1s 0.04 · rvol_30s 0.04 · depth_ask_1 0.04 · depth_bid_1 0.04 · ofi_deep_1s 0.04 · depth_ask_2 0.03

## Stage C.8 — does the Phase B edge transfer to CME? — 2026-08-03

**Caveat, read first: this is 53 days of ONE instrument on ONE venue, spanning
one directional regime. It is more than the single day Phase B rested on and
it is still not enough to conclude an edge exists — or that one is absent for
any reason more durable than the conditions of April and May 2026.**

**Correction to the auto-generated header above it:** the "~10 volatility
regime(s)" figure is `len(dates) // 5`, a placeholder heuristic in
`research/__main__.py`, not a measurement. What the data actually spans:
BTC ran **65,850 to 83,195 (+26%)** across the two months with no sustained
drawdown — a rising market, sampled once. Daily book events ranged 413,952 to
7,325,851 (17.7x), but the low end is the expiry-session collapse rather than
a quiet regime. **Distinct volatility conditions genuinely covered: one.**

### The answer: the edge did not transfer. It vanished.

| 900 s, maker | round-trip cost | gross capture | AUC | net EV |
|---|---|---|---|---|
| Kraken ETH/USD (Phase B) | 80.00 bps | ~3.9 bps | — | −76.1 |
| Coinbase BTC-USD (Phase B) | 80.00 bps | **3.31 bps** | 0.596 | −76.69 |
| Coinbase ETH-USD (Phase B) | 80.00 bps | 2.64 bps | 0.558 | −77.36 |
| **CME MBT (this run)** | **5.33 bps** | **0.22 bps** | **0.501** | **−5.11** |

Changing venue cut costs **15x**. It cut the gross edge **15x** as well. Net EV
improves from −76.69 to −5.11 bps and **never crosses zero at any horizon in
either cost mode** — best case is maker at 900 s, −5.11 bps; worst is taker at
100 ms, −7.25 bps.

**This is a different negative result from Phase B's, and the difference is the
point.** On crypto spot a real 3–4 bps edge was buried under 80 bps of fees: a
cost problem. On CME MBT the cost problem is genuinely solved — 5.33 bps is
affordable against a 3 bps edge — and there is no edge left to capture. Moving
venue fixed what was wrong and revealed that something else was also wrong.

### Gross capture and net EV, per horizon

Realised costs, computed per sample at its own notional (mean BTC 76,084,
mean notional **$7,608**/contract): maker **5.325 bps** round trip (range
4.862–6.125 as price moved), touch spread **1.930 bps**, taker **7.255 bps**.

| horizon | AUC | gross capture | net EV maker | net EV taker |
|---|---|---|---|---|
| 100 ms | 0.664 | +0.005 | −5.32 | −7.25 |
| 500 ms | 0.620 | +0.005 | −5.32 | −7.25 |
| 1000 ms | 0.600 | +0.005 | −5.32 | −7.25 |
| 5 s | 0.551 | +0.015 | −5.31 | −7.24 |
| 30 s | 0.521 | +0.045 | −5.28 | −7.21 |
| 60 s | 0.516 | +0.035 | −5.29 | −7.23 |
| 300 s | 0.508 | +0.085 | −5.24 | −7.18 |
| 900 s | 0.501 | +0.215 | **−5.11** | −7.04 |

Gross capture is `mean(EV) + mean(cost)`, which is exact because both are means
over the same samples. Everything below 300 s sits at or under the rounding
precision of the EV column (±0.005) — indistinguishable from zero.

**MBT is less predictable than Coinbase spot at every horizon:**

| horizon | Coinbase BTC-USD | CME MBT |
|---|---|---|
| 100 ms | 0.886 | 0.664 |
| 1 s | 0.786 | 0.600 |
| 30 s | 0.551 | 0.521 |
| 900 s | 0.596 | **0.501** |

The last row is a coin flip.

### The one apparent positive does not replicate

The +0.215 bps at 900 s is the only figure in the table that clears rounding
noise, so it was checked rather than reported. A **control run on 10 April days
at stride 1** (896,018 samples, run_id `464f8937`) returns **−0.785 bps** gross
capture at the same horizon, with AUC **0.490** — below chance. Gross capture on
MBT is noise around zero, which is what AUC ≈ 0.50 already implied. **No horizon
carries an edge, and the strongest-looking one reverses sign on a different
subset.** Nothing here is a hypothesis for Phase C to test under fill
simulation, because there is no positive expected value to preserve.

### The control also clears the sampling confound

The main run used an effective ~200-update bar (stride 4, forced by memory —
ADR-025) where Phase B used 50, so bar width was a live alternative explanation
for the weaker AUC. The stride-1 control reproduces the AUC curve within 0.01
at every horizon:

| horizon | 100 ms | 1 s | 30 s | 300 s | 900 s |
|---|---|---|---|---|---|
| main (stride 4, 53 d) | 0.664 | 0.600 | 0.521 | 0.508 | 0.501 |
| control (stride 1, 10 d) | 0.659 | 0.591 | 0.515 | 0.489 | 0.490 |

Bar width explains none of the result.

### Capability matrix, applied honestly

**35 of 42 features computed; 7 skipped.** All seven cross-venue features
(`xv_mid_diff_bps`, `xv_diff_z`, `xv_leadlag_{m500,m100,0,p100,p500}`) are
**100% NaN** — Kraken, Coinbase and Hyperliquid have no April–May data, since
those recorders were activated later. They are absent, not silently zero, and
none appears in the top-10 importances.

MBT's per-contract entry (ADR-018) credits it with the full library, and the
data bears that out: short trade-window features are populated rather than
constant — `signed_vol_1s` 29.0% nonzero, `signed_vol_5s` 56.3%,
`trade_count_5s` 59.7%, `vwap_minus_mid_5s` 56.6% nonzero / 40.3% NaN. A quiet
market, not an absent one.

Top features are microstructure-local, as expected with no cross-venue signal:
`spread_bps` 0.08 · `time_since_trade_ms` 0.07 · `rvol_1s` 0.06 ·
`abs_ret_1s` 0.05 · `ofi_best_1s` 0.05.

### Walk-forward capacity: one clean fold, not three

At 42-day train / 14-day test over a 61-day span the data yields **2 folds, and
the second is truncated** — its test window runs 5 days past the end of the
data (43,340 samples against the first fold's 252,596). **Honestly counted,
this range supports one complete train/test split.** The windows were not
shrunk to manufacture more: a 14-day test is already 1,344x the longest label
horizon, and cutting it further would trade independent evaluation for the
appearance of cross-validation. Six months would give three.

### What would change this answer

Nothing here says CME micro bitcoin has no exploitable structure. It says that
*this feature set*, at *these horizons*, over *this one rising regime*, does
not find any — with costs low enough that a 3 bps edge would have shown. The
open possibilities, in order of cheapness: a regime that is not a two-month
uptrend; cross-venue features against the crypto recorders, which now run and
will make lead-lag against Kraken/Coinbase computable for future months; and
MES, which is 2.49x MBT's event rate on a 5.2x larger notional, so its costs in
bps are ~7x lower and the same gross edge would clear them.

## Stage C.9 — spread-to-cost survey and adverse selection — 2026-08-03

**The correction this stage exists to make.** After C.8 closed directional
prediction, a further claim was made and not verified: that spread capture is
dead everywhere reachable, because fees exceed the spread. That was checked on
**two instruments** — MBT at 1.93 bps against 5.33 bps of cost, and full-size ES
by estimate — and generalised. Those are among the *tightest* instruments
available, which is the worst possible basis for the generalisation. Fees scale
with notional and stay roughly constant in bps; spreads do not, and widen
sharply on thin instruments. **The spread-to-cost ratio is a property of an
instrument, not a venue.** This stage measures it across 28 instruments instead
of arguing about it.

The correction is **partly vindicated and does not change the conclusion**, for
a reason the ratio alone cannot show.

### Task 1 — Hyperliquid census, and what was actually subscribed

**Finding, as anticipated: the recorder was subscribed to BTC and ETH only** —
2 of 177 live perps, and precisely the two where the ratio is worst. The census
below is therefore a census of the least favourable corner of the venue.

Measured over **53.13 quoted hours** (2026-08-01 to 08-03, 2,151,124 bbo
updates, 342,965 trade messages, 0 unparseable), against a maker round trip of
**3.00 bps** (1.5 bps/leg, base tier, `config/venues.yaml`, verified 2026-08-01):

| coin | mean bps | median | p90 | >3 bps | >6 bps | >12 bps | **spread/cost** |
|---|---|---|---|---|---|---|---|
| BTC | 0.164 | 0.2 | 0.2 | 0.01% | 0.00% | 0.00% | **0.055** |
| ETH | 0.545 | 0.75 | 0.75 | 0.03% | 0.00% | 0.00% | **0.182** |

Spread is **time-weighted**, not update-weighted: what matters is what a resting
quote faced, not how often the quote changed. Neither instrument spends
measurable time above the 3 bps it would need merely to break even on fees.

**Subscription extended** from `[BTC, ETH]` to **12 coins**, chosen by the
venue's own liquidity ranking (24h notional volume, `metaAndAssetCtxs`,
retrieved 2026-08-03) sampled across the whole range rather than cherry-picked:

| coin | rank | 24h notional | endpoint impact spread |
|---|---|---|---|
| BTC / ETH | 1 / 2 | $2.03B / $672M | 0.72 / 1.82 bps |
| HYPE / SOL | 3 / 4 | $217M / $154M | 1.87 / 0.81 bps |
| PUMP | 6 | $31M | 4.47 bps |
| DOT / LINK / ARB | 29 / 31 / 33 | $2.4M / $2.0M / $1.9M | 3.96 / 3.00 / 6.01 bps |
| GMX / MERL | 152 / 153 | $97K / $97K | 16.19 / 15.95 bps |
| TNSR / NOT | 175 / 177 | $31K / $15K | 79.18 / 58.31 bps |

Impact spread is the endpoint's own field and only a *ranking* signal — touch
spread is what matters and is what the census will measure. The thin end is
where the ratio could plausibly be favourable, so it is where adverse selection
has to be measured before any of it is believed. Applied via a managed systemd
restart; all 12 coins verified recording bbo **and** trades within 40 s, and the
lifecycle boundary was recorded as a clean end/start pair 574 ms apart.

### Task 2 — CME survey, 16 micro contracts, $0.7763

Priced before buying, bbo-1s only (no mbp-10 for any new contract), one day
(2026-07-15). Cost per side = CME exchange execution + clearing (TradeStation
published non-member schedule, retrieved 2026-08-02) + $0.02 NFA + $0.85 IBKR
commission, the same tier-0 convention as ADR-023.

**Contracts with a real continuous market (>20,000 quote updates/day):**

| symbol | updates/day | spread bps | notional | RT $ | cost bps | **ratio** |
|---|---|---|---|---|---|---|
| M6A micro AUD | 22,761 | 3.099 | $6,985 | 2.22 | 3.178 | **0.98** |
| MNQ micro Nasdaq | 82,259 | 0.370 | $59,670 | 2.44 | 0.409 | **0.91** |
| M6E micro EUR | 34,122 | 1.337 | $14,332 | 2.22 | 1.549 | **0.86** |
| MGC micro gold | 73,358 | 0.817 | $40,505 | 3.94 | 0.973 | **0.84** |
| M6B micro GBP | 23,332 | 2.162 | $8,408 | 2.22 | 2.640 | **0.82** |
| MES micro S&P | 79,999 | 0.377 | $38,027 | 2.44 | 0.642 | **0.59** |
| MYM micro Dow | 68,935 | 0.455 | $26,428 | 2.44 | 0.923 | **0.49** |
| M2K micro Russell | 72,968 | 0.703 | $14,931 | 2.44 | 1.634 | **0.43** |
| MBT micro bitcoin | 64,230 | 2.640 | $6,505 | 4.04 | 6.211 | **0.43** |
| MET micro ether | 50,609 | 8.981 | **$191** | 1.94 | 101.762 | **0.09** |

**Not one exceeds 1.0.** The best, micro AUD/USD at 0.98, is break-even on fees
*before* any adverse selection. MET is the extreme case of the notional effect
that started this: 0.1 ETH is a $191 contract, so even a $1.94 round turn is
102 bps.

**Contracts too inactive to call a market:**

| symbol | updates/day | spread bps | cost bps | ratio | note |
|---|---|---|---|---|---|
| SIL micro silver | 69 | 2275.4 | 0.585 | 3889 | one quote per 20 min |
| MHG micro copper | 1,494 | 128.6 | 1.978 | 65.0 | one quote per minute |
| 30Y micro yield | 96 | 410.6 | — | — | yield-quoted |
| 10Y micro yield | 4,577 | 17.9 | — | — | yield-quoted |
| 2YY / 5YY | 10 / 1 | — | — | — | **failed measurement** |

Three honest qualifications. The **yield** contracts quote in yield, not price,
so "bps of notional" is the wrong frame and no ratio is computed. **2YY and
5YY** returned 10 and 1 usable records with mids of 1.4e9 and 4.6e9 — implausible
values from an unresolved continuous symbol, so these are a failed measurement,
not a thin market, and are reported as such rather than as data. And **SIL and
MHG show enormously favourable ratios on books that barely exist**: a spread you
cannot get filled against is not an opportunity, and with 69 quote updates in a
day the measurement may not describe a tradeable market at all.

### Task 3 — adverse selection

Signed post-trade mid drift: for every trade, signed by aggressor direction,
how far the mid moves in the aggressor's favour. That is what a passive fill on
the other side would have suffered. Positive means adverse. Deadlines resolve
against the last mid at or before them, never a later one.

| instrument | trades | 100 ms | 1 s | 5 s |
|---|---|---|---|---|
| Hyperliquid BTC | 491,982 | +0.063 | +0.215 | +0.289 |
| Hyperliquid ETH | 278,835 | +0.106 | +0.298 | +0.384 |
| CME MBT | 148,768 | +0.657 | +0.678 | +0.643 |

Positive at every horizon on every instrument measured. MBT's is ~3x the
Hyperliquid majors' and already flat by 100 ms, which is what one expects where
informed flow is a larger share of a thinner tape.

### The number that decides it: spread − adverse − cost

| instrument | spread | adverse (1 s) | cost | **net bps** |
|---|---|---|---|---|
| Hyperliquid BTC | 0.164 | 0.215 | 3.000 | **−3.05** |
| Hyperliquid ETH | 0.545 | 0.298 | 3.000 | **−2.75** |
| CME MBT | 2.640 | 0.678 | 6.211 | **−4.25** |

**Every instrument measured fails, and none is close.** For the ten liquid CME
contracts where trades were not bought, the conclusion follows without them:
ratio < 1 means spread < cost, so the net is negative before adverse selection
is charged at all, and measured adverse selection is positive everywhere
(+0.06 to +0.68 bps). Adding a positive quantity to a negative result does not
rescue it.

**This assumes a fill, which no part of this pipeline models.** Queue position
determines whether the passive order is filled at all; the arithmetic above
credits every quote with a fill it has not earned. That makes these figures an
*upper bound* on spread-capture economics, and they are already negative. On
any instrument where the ratio does look attractive, the same is visible to
everyone else quoting it, and the queue in front of you is the mechanism by
which that attractiveness is competed away.

### Recommendation: do not build the fill simulation against any of these

The ratio-minus-adverse-selection arithmetic closes spread capture on every
instrument with a measurable market, the way C.8 closed directional prediction —
and for a sharper reason: C.8 needed a model to fail, whereas this needs only
subtraction, and it fails by 2.75 to 4.25 bps rather than marginally. Building
fill simulation against a negative upper bound would be building it to confirm
a sign that is already determined.

**What is genuinely open, and how to close it for free.** The thin tail is not
closed: SIL and MHG show ratios of 65 and 3,889, and the correction that
prompted this stage is right that the ratio is instrument-dependent and does
exceed 1 somewhere. What is unknown is whether those books are tradeable and
what adverse selection does there — and CME bbo-1s cannot answer it, because it
carries no trades. The ten thin Hyperliquid perps subscribed in Task 1 answer
exactly that question, with both quotes and aggressor-signed trades, at **zero
marginal cost**, on instruments spanning a 110x range of impact spread. Re-run
this census in a week. If the thin end survives spread − adverse − cost there,
that is the first positive result this project has produced and it earns a fill
simulation; if it does not, spread capture is closed on the evidence rather than
by assertion.
