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

## Validation run — 2026-08-04 08:29 UTC

### coinbase — 2026-08-03 — **PASS**

Messages: **3460641** · recorded span: 86400s · feed gaps in span: 0 (0 ms) · recorder downtime: 0 (0 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 0 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-08-02 18:12:08Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `heartbeats`: 86400 · `l2_data`: 3106470 · `market_trades`: 267771

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 3,460,641 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 1631707 | 7 | 0 (0) | n/a | n/a | 0 (0) | 0 | 100.00% | 100.00% | 7 (2) | 1718113 |
| ETH-USD | 1474751 | 5 | 0 (0) | n/a | n/a | 0 (0) | 0 | 100.00% | 100.00% | 5 (0) | 1561155 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 26659 |
| 0.05 to 0.1 ms | 47664 |
| 0.1 to 0.5 ms | 68771 |
| 0.5 to 1 ms | 43205 |
| 1 to 5 ms | 279904 |
| 5 to 10 ms | 483418 |
| 10 to 50 ms | 2250595 |
| 50 to 100 ms | 242925 |
| 100 to 500 ms | 17434 |
| 500 to 1000 ms | 51 |
| 1000 to 5000 ms | 13 |
| 5000 to 30000 ms | 1 |
| >30000 ms | 0 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 22553.5 ms

### hyperliquid — 2026-08-03 — **PASS**

Messages: **1489552** · recorded span: 86400s · feed gaps in span: 1 (1142 ms) · recorder downtime: 0 (0 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 1142 ms (all kinds unioned and clamped to the span)

Snapshot stream: every l2Book message is a full book, so warm start is structurally unnecessary; this venue is scored on snapshot cadence.

Channels: `activeAssetCtx`: 169503 · `bbo`: 1112687 · `l2Book`: 32200 · `subscriptionResponse`: 64 · `trades`: 175098

Integrity mechanism: **snapshot cadence** · sequence numbers: n/a (this feed provides none) · book checksums: n/a (this feed provides none) · book snapshots: 32,200 applied

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 0 | 16100 | n/a | n/a | n/a | 0 (0) | 0 | 100.00% | 100.00% | 16099 (6616) | 696580 |
| ETH | 0 | 16100 | n/a | n/a | n/a | 0 (0) | 0 | 100.00% | 100.00% | 16099 (6884) | 621101 |

Snapshot cadence BTC: 16,099 intervals · p50 5384 ms · p95 5554 ms · max 28100 ms · stale >10s: 1 (1 unexplained)
Snapshot cadence ETH: 16,099 intervals · p50 5384 ms · p95 5554 ms · max 28100 ms · stale >10s: 1 (1 unexplained)

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 20 |
| 0.01 to 0.05 ms | 289613 |
| 0.05 to 0.1 ms | 269151 |
| 0.1 to 0.5 ms | 205005 |
| 0.5 to 1 ms | 1557 |
| 1 to 5 ms | 2124 |
| 5 to 10 ms | 3643 |
| 10 to 50 ms | 125841 |
| 50 to 100 ms | 253030 |
| 100 to 500 ms | 333357 |
| 500 to 1000 ms | 6083 |
| 1000 to 5000 ms | 126 |
| 5000 to 30000 ms | 1 |
| >30000 ms | 0 |

p50 ≤ 0.5 ms · p90 ≤ 500 ms · p99 ≤ 500 ms · max 22767 ms

### kraken — 2026-08-03 — **PASS**

Messages: **16653584** · recorded span: 86400s · feed gaps in span: 7 (14593 ms) · recorder downtime: 0 (0 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 14593 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-08-02 03:14:18Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `book`: 16531206 · `heartbeat`: 86347 · `status`: 7 · `subscribe`: 28 · `trade`: 35996

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 16,531,192 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 7373330 | 7 | n/a | 0 (0) | 7373330 | 0 (0) | 0 | 99.98% | 100.00% | 7 (0) | 7459736 |
| ETH/USD | 9157862 | 7 | n/a | 0 (0) | 9157862 | 0 (0) | 0 | 99.98% | 100.00% | 7 (3) | 9244268 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 19433 |
| 0.01 to 0.05 ms | 7734419 |
| 0.05 to 0.1 ms | 1513951 |
| 0.1 to 0.5 ms | 888928 |
| 0.5 to 1 ms | 725358 |
| 1 to 5 ms | 3220032 |
| 5 to 10 ms | 829814 |
| 10 to 50 ms | 1297586 |
| 50 to 100 ms | 283405 |
| 100 to 500 ms | 140033 |
| 500 to 1000 ms | 600 |
| 1000 to 5000 ms | 23 |
| 5000 to 30000 ms | 1 |
| >30000 ms | 0 |

p50 ≤ 0.1 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 22678.1 ms
### Venues skipped

- **cme** (kind `vendor`) — vendor-backfill venue, not captured live — it has no raw data on any date by design. Stored vendor days are scored on request: `python -m data.validate --venue cme --date YYYY-MM-DD`

## Validation run — 2026-08-04 08:34 UTC
### cme MBT.c.0 — 2026-07-31 — **FAIL** (vendor, `mbp-10`)

- ✗ coverage 71.49% of scheduled-open time < 99%

Events: **380,358** · scheduled open: 21.00 h · covered: 15.01 h (71.49%) · unexplained quiet: 5.99 h (4 window(s)) · roll exclusions: 1 (0.00 h of open time)

Ordering clock: ts_recv (Databento capture-server hardware clock) · reference only: ts_event (CME MDP3 matching-engine clock)

Integrity: MDP3 sequence numbers: 380,358 checked (0 regressions) · book checksums: n/a (this feed provides none) · book snapshots: n/a (this feed provides none)

Crossed: 0 (0 inside a scheduled no-match window, so expected) · locked: 0 · out of order on ts_recv: 0 · exchange-clock regressions: 0 (reference clock, not a defect)

### cme MES.c.0 — 2026-07-31 — **PASS** (vendor, `mbp-10`)

Events: **14,989,106** · scheduled open: 21.00 h · covered: 21.00 h (100.00%) · unexplained quiet: 0.00 h (0 window(s)) · roll exclusions: 0 (0.00 h of open time)

Ordering clock: ts_recv (Databento capture-server hardware clock) · reference only: ts_event (CME MDP3 matching-engine clock)

Integrity: MDP3 sequence numbers: 14,989,106 checked (0 regressions) · book checksums: n/a (this feed provides none) · book snapshots: n/a (this feed provides none)

Crossed: 0 (0 inside a scheduled no-match window, so expected) · locked: 0 · out of order on ts_recv: 0 · exchange-clock regressions: 0 (reference clock, not a defect)

## Stage C.10 — cointegration pairs trading — 2026-08-04

**Standing caveat, first.** Everything below rests on free daily bars from a
venue this project cannot trade (Binance), used because it is the only free
source that remembers delisted assets. It is not the recorded tick archive,
which remains under three weeks old and cannot carry a multi-year statistical
relationship. Conclusions about *cointegration* are drawn from that history;
conclusions about *executability* are constrained by the venues actually
reachable from British Columbia.

### 1. Universe construction — survivorship-free, and here is the evidence

Sample **2021-08-01 to 2026-07-31**, 1,826 daily bars.

Selection rule: **symbols with a Binance monthly daily-bar file in the sample's
first month, ranked by that month's quote volume.** Not today's liquid symbols,
not symbols with a complete series, not symbols still trading — each of those is
a way of letting the sample's end leak into its beginning.

| step | count |
|---|---|
| USDT-quoted symbol directories in the archive | 710 |
| listed at 2021-08 (had bars that month) | **291** |
| selected (top 60 by 2021-08 quote volume) | 60 |
| **stopped trading inside the sample** | **12 (20%)** |
| excluded for a spliced price series | 1 |
| excluded for too few observations | 1 |
| carried into the study | **58** |

The twelve that died: `MATICUSDT` (2024-09), `EOSUSDT` (2025-05), `FTMUSDT`
(2025-01), `BAKEUSDT` (2025-09), `ATAUSDT`, `DENTUSDT`, `TRUUSDT`, `SXPUSDT`
(2026-04/05), `MBOXUSDT` (2026-06), `SRMUSDT` (2022-11), `BTTUSDT` (2022-01),
`EPSUSDT` (2022-05). Several are rebrands or redenominations rather than
failures — MATIC became POL, FTM became S, EOS became A — but the ticker ended,
which is what matters for a tradeable series. **A universe screened on today's
liquidity silently drops one in five of this sample.**

This is possible only because `data.binance.vision` retains delisted
directories; `FTTUSDT`, `LUNAUSDT`, `SRMUSDT`, `BUSDUSDT` and `WAVESUSDT` all
still resolve (verified 2026-08-04). Kraken's `AssetPairs` and Coinbase's
`products` enumerate only live products, so **neither is ever used to select a
universe here** — Kraken additionally hard-caps its OHLC endpoint at 720
candles, roughly two years of daily bars, and cannot carry this sample at all.

**Caveat, not assumed away:** this rests on Binance not purging delisted
directories. Five known-dead symbols surviving is evidence, not a guarantee, and
a symbol purged before 2026-08-04 would be invisible to the check itself.

#### A second bias the survivorship fix does not cover: ticker reuse

`LUNAUSDT` has an unbroken run of monthly files. It is also two different
assets. Terra collapsed in May 2022 and Terra 2.0 relaunched on the same ticker;
the old chain became `LUNCUSDT`. The detector caught it exactly:

```
LUNAUSDT 2022-05-11: 17.46    -> 1.0769   (0.0617x in one bar)
LUNAUSDT 2022-05-12: 1.0769   -> 0.00032  (0.000297x in one bar)
LUNAUSDT 2022-05-31: 0.00005  -> 8.87     (177,400x in one bar)
```

Read naively the series is continuous. In truth it is a splice, and no
cointegration test interprets one correctly — a splice looks like a structural
break, and a structural break looks like a relationship that decayed. Excluded
entirely rather than truncated. `BTTUSDT` (1:1000 redenomination to BTTC,
January 2022) went the same way on observation count.

### 2. Screening — 432 raw "discoveries", 83 of them expected from noise

Engle-Granger two-step on log closes, one fixed orientation per pair, plus a
Johansen trace test. Benjamini-Hochberg at q=0.05.

| | formation 2021-08→2023-07 | holdout 2023-08→2026-07 |
|---|---|---|
| pairs tested | 1,653 | 1,540 |
| raw hits at α=0.05 (Engle-Granger) | 432 | 91 |
| **expected by chance at this universe size** | **82.7** | **77.0** |
| **hits surviving Benjamini-Hochberg** | **180** | **0** |
| Johansen rejections, uncorrected | 559 | 194 |
| pairs passing both tests | 167 | 0 |

The formation window has a genuine excess — 432 against 82.7 expected, 5.2×. The
holdout window does not: **91 raw hits against 77.0 expected is barely above
noise, and not one pair survives the correction.**

**Persistence: relationships decay, they do not hold.**

| | |
|---|---|
| formation-window BH survivors | 180 |
| re-testable in the holdout | 175 |
| still significant uncorrected | **18 (10.3%)** |
| still significant under BH | **0** |
| base rate for *any* pair in the holdout | 5.9% |
| lift over base rate | **1.74×** |

A 10.3% persistence rate against a 5.9% base rate is not a stable relationship;
it is a coin weighted very slightly. This reproduces the literature's finding
that cointegrating vectors are time-varying, and it is the reason the hedge
ratio here is re-estimated on a rolling 90-day window rather than fitted once.

### 3. Break-even transaction cost — the ranking that matters

Signal fixed a priori and never searched: rolling 90-bar hedge ratio, 60-bar
z-score, enter at |z|=2, exit at z=0, abandon after 30 bars. Gross exposure
normalised to one unit across both legs, so `cost_bps` is a **round-trip** rate
on that unit — 3.0 bps at Hyperliquid maker, 80.0 bps at Kraken base-tier spot
maker. Traded strictly out of sample: selection on the formation window, scoring
begins the day it ends.

**Power floor applied: ≥20 trades and ≥250 scored bars.** 43 of 175 pairs clear
it. The unfiltered table is kept below, because the gap between the two is the
finding.

| pair | trades | RT/yr | gross %/yr | net HL %/yr | net Kraken %/yr | **break-even bps** | Sharpe | executable |
|---|---|---|---|---|---|---|---|---|
| C98/XTZ | 22 | 7.3 | 40.56 | 40.34 | 34.70 | **553.1** | 0.98 | no |
| THETA/WIN | 20 | 6.5 | 34.88 | 34.68 | 29.68 | **536.6** | 0.84 | no |
| KSM/WIN | 20 | 6.7 | 34.80 | 34.60 | 29.46 | **521.9** | 0.64 | no |
| ALICE/RAY | 21 | 7.2 | 32.95 | 32.74 | 27.22 | **459.8** | 0.60 | no |
| KSM/XTZ | 22 | 7.3 | 32.77 | 32.55 | 26.91 | **446.9** | 0.62 | no |
| AUDIO/THETA | 26 | 8.8 | 36.33 | 36.07 | 29.27 | **411.3** | 1.22 | no |
| QTUM/WIN | 21 | 6.8 | 26.85 | 26.64 | 21.38 | **392.9** | 0.70 | no |
| TLM/XTZ | 27 | 9.0 | 27.32 | 27.05 | 20.12 | **303.6** | 0.78 | no |

**The stage's premise is confirmed and it is not enough.** At 6–9 round trips a
year, Hyperliquid's 3 bps costs about 20 bps annually against returns in the
tens of percent — 98 of 175 pairs are profitable gross and **the same 98** are
profitable net of Hyperliquid cost. Even Kraken's punitive 80 bps leaves 85
profitable. Break-even costs of 300–550 bps sit **100–180× above** the cost of
the venue. Lower turnover did exactly what it was supposed to: **cost is no
longer the binding constraint.** Something else is.

**What the power floor removes.** Unfiltered, the table is led by
`BAKEUSDT/XTZUSDT` at 128.7% a year on 18 trades and `FTMUSDT/GRTUSDT` at 74.0%
on **9 trades over 531 bars**. Both have a leg that died mid-sample, so their
out-of-sample stretch is short and their returns rest on a handful of events.
132 of 175 pairs sit below the floor.

### 4. Executability — zero, for two independent reasons

Of the twelve Hyperliquid perps subscribed on 2026-08-03, **five existed on
Binance at 2021-08**: BTC, ETH, SOL, DOT, LINK. The other seven listed later or
never: ARB 2023-03, GMX 2022-10, TNSR 2024-04, NOT 2024-05, PUMP 2025-09, and
HYPE and MERL **never listed on Binance at all**.

That gives ten testable executable pairs in the main sample. **None survives,
and none is close:**

| pair | Engle-Granger p | BH q | survives |
|---|---|---|---|
| DOT/SOL | 0.0128 | 0.0858 | no |
| LINK/SOL | 0.0185 | 0.1088 | no |
| **BTC/ETH** | **0.1169** | 0.3189 | **no** |
| ETH/LINK | 0.1681 | 0.3785 | no |
| BTC/SOL | 0.4054 | 0.6333 | no |
| BTC/DOT | 0.8695 | 0.9487 | no |

**The published BTC-ETH result does not reproduce.** The strategy this stage was
asked to test — 14.89% annualised at Sharpe 2.23 — rests on a pair that is not
cointegrated at 5% even before any multiple-testing correction, on a
survivorship-free five-year sample.

#### The executable set, tested fairly

Reporting only the above would report a conclusion the window guaranteed, since
seven of twelve coins could not be in a 2021-08 universe. So the executable set
was re-screened on **2024-06 to 2026-07** (791 bars), where nine of the twelve
exist:

| | |
|---|---|
| pairs tested | 36 |
| raw hits at α=0.05 | **1** |
| expected by chance | **1.8** |
| surviving Benjamini-Hochberg | **0** |
| passing both tests | **0** |
| losing money gross | **23 of 36** |
| trades per pair | **5 to 9** |

Fewer raw hits than chance produces. The single Johansen rejection, ARB/GMX
(p=0.0136), **loses 8.4% a year gross**. BTC/ETH scores p=0.9275 in this window.
No pair exceeds nine trades in 425 out-of-sample bars — none has the power to
support any conclusion about its own Sharpe.

### 5. Walk-forward and deflated Sharpe

Best powered pair `C98USDT/XTZUSDT`, twelve consecutive 90-bar folds:

| fold | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| return % | +3.3 | +10.4 | +8.7 | −1.3 | +6.6 | −4.4 | +0.9 | −7.1 | **+51.5** | −1.8 | **+55.9** | −0.8 |
| Sharpe | 0.67 | 1.06 | 1.55 | −0.40 | 1.64 | −0.30 | 0.19 | −1.48 | 3.14 | −0.43 | 2.52 | −0.13 |

Seven positive, five negative, and **two of twelve quarters carry essentially
the entire return**. That is not a strategy with a stable edge; it is two events
with ten quarters of noise around them.

**Deflated Sharpe (Bailey & López de Prado, 2014), correcting for 1,653 pairs
screened:**

| | |
|---|---|
| annualised Sharpe | 0.98 |
| per-bar Sharpe | 0.0514 |
| **expected max per-bar Sharpe under the null, 1,653 trials** | **0.1058** |
| skew / kurtosis | 3.78 / 79.50 |
| observations | 1,095 |
| **deflated Sharpe** | **0.026** |

**The benchmark exceeds the result.** Searching 1,653 pairs of pure noise would
be expected to produce a best per-bar Sharpe of 0.1058; the actual best is
0.0514, less than half of it. The deflated Sharpe of 0.026 says there is roughly
a 2.6% probability this pair's true Sharpe is above zero. A kurtosis of 79
confirms what the fold table shows — the return is a couple of outliers, not a
distribution.

Embargo scaling confirmed for day-scale holding: 30 bars → 2,592,000,000,000,000
ns, exact in int64 (Stage C.2 machinery was sized for millisecond horizons).

### 6. Verdict

**No executable pair survives at Hyperliquid cost with enough trades to be
statistically meaningful. Not one.** Zero of the ten testable executable pairs
in the main sample, and zero of thirty-six in the recent window, are
cointegrated after correction — most are not cointegrated before it.

This is the project's fourth negative, and it fails differently from the first
three, which matters:

- **C.8 and C.9 failed on cost.** Edge per trade was smaller than cost per
  trade, by 15× and by 2.75–4.25 bps respectively.
- **C.10 does not fail on cost.** The turnover fix worked — break-even costs of
  300–550 bps against a 3 bps venue, a margin of 100–180×. Cost stopped being
  the constraint.
- **C.10 fails on the edge and on access.** The relationships do not persist
  (0 of 180 survive re-testing), the best surviving result is weaker than what
  screening 1,653 pairs of noise would produce, and the pairs that do look best
  are ones no reachable venue lets us short.

The honest summary is that the structural response was correct and the thing it
was applied to was not there. Cointegration among liquid crypto assets over
2021–2026, measured without survivorship bias and corrected for multiple
testing, is not distinguishable from noise out of sample.

**Data acquired this stage:** 3,936 monthly files, 295 symbols, 15.0 MB, all
free — 3,702 daily and 234 hourly. Hourly bars cover the nine executable
symbols over 2024-06→2026-07 and are retained for future intraday work; this
study runs on daily bars because the holding period is days. Every file carries
source, venue, URL, sha256 and retrieval date in
`data/vendor/archive/manifest.jsonl`. **Nothing was purchased.**

## Stage C.11 — funding rate carry — 2026-08-04

**This stage evaluates a carry trade, not a machine learning strategy.** Almost
none of the Phase B research layer is used: there are no features, no labels,
no model, no cross-validation, no train/test split. A carry has nothing to fit.
The income is mechanical — a perp trading above spot pays funding from longs to
shorts, and holding long spot against short perp collects it while price
exposure cancels. That is why it is worth testing after four predictive
hypotheses failed, and it is also why the risks live somewhere a backtest is
weak: in operations and across venues rather than in the arithmetic.

### 1. What the sample covers, and what it does not

| | |
|---|---|
| primary venue | **Hyperliquid perps** — the only shortable venue reachable from British Columbia |
| funding history | **2023-05-12 to 2026-08-04**, 3.23 years, 27,761 hourly observations for BTC |
| instruments | the 12 perps subscribed in C.9 |
| decay history | **Binance perps 2020-01 to 2026-07**, 8-hourly, for the years Hyperliquid did not exist |
| spot leg prices | Binance spot 1h (free archive) |
| perp prices | `spot × (1 + Hyperliquid premium)` — the venue's candle endpoint serves only the most recent ~5,000 bars (208 days) and cannot cover the sample |

**Regimes contained:** the 2023 recovery, the 2024 bull run, and the 2025–2026
compression. **Not contained:** a full bear market. Hyperliquid launched *after*
the 2022 drawdown, so the worst funding environment in recent crypto history is
outside its history entirely. Every Hyperliquid figure below is therefore drawn
from a favourable sample, and the Binance section exists to say what the missing
years looked like.

**A data hazard worth naming: the venue changed its own funding interval.**
Hyperliquid paid **eight-hourly** from launch until 2023-06-08 and **hourly**
after — 81 eight-hour steps, then 27,676 one-hour steps, plus three two-hour
gaps. Any annualisation that multiplies a mean rate by a fixed
intervals-per-year constant is silently wrong across that boundary, by a factor
of eight. Everything here divides accumulated funding by **elapsed time**
instead. On BTC the correction is small (14.21% vs 14.50% naive) because the
eight-hourly era is only 27 of 1,181 days — but it would be an 8× error on a
series with a different mix, and nothing in the output would have shown it.

### 2. What funding actually paid

| coin | years | annualised | % of time negative | negative runs | runs > 1 week | longest run | worst run cost |
|---|---|---|---|---|---|---|---|
| BTC | 3.23 | **14.21%** | 14.1% | 806 | 1 | 8.3 d | −0.41% |
| ETH | 3.23 | **14.33%** | 14.5% | 961 | 0 | 6.0 d | −0.71% |
| HYPE | 1.66 | **21.60%** | 6.3% | 448 | 0 | 0.6 d | −0.20% |
| LINK | 3.22 | **15.59%** | 13.6% | 579 | 3 | 16.4 d | −2.16% |
| PUMP | 1.07 | 14.35% | 7.2% | 280 | 0 | 1.5 d | −0.33% |
| SOL | 3.23 | 12.28% | 25.9% | 1,142 | 1 | 10.7 d | −1.00% |
| ARB | 3.23 | 11.64% | 22.8% | 1,286 | 0 | 6.9 d | −0.46% |
| DOT | 2.90 | 7.27% | 25.7% | 1,103 | 1 | **41.5 d** | −5.92% |
| NOT | 2.22 | 6.66% | 13.2% | 1,041 | 0 | 1.5 d | −1.18% |
| GMX | 3.20 | 3.75% | 25.4% | 1,250 | 2 | 15.8 d | −5.11% |
| MERL | 2.28 | **−22.38%** | 29.5% | 1,132 | 2 | 17.4 d | −22.65% |
| TNSR | 2.32 | **−32.41%** | 21.2% | 959 | 1 | 19.0 d | −46.52% |

The published 0.01%/8h ≈ 11% baseline is roughly right **for the liquid
majors** and badly wrong as a general claim. Two of twelve instruments paid
*negative* funding for years: shorting TNSR would have cost **75% of notional**
over 2.3 years. The thin end of the perp market is where a naive screen for
"high funding" would send an operator, and it is where the sign flips.

Negative runs are mostly short — BTC's longest is 8.3 days costing 0.41% — but
DOT's longest is **41.5 days** and GMX's worst costs **5.11%**. A strategy sized
on the average would have been financing a six-week loss on DOT.

### 3. Funding has compressed, and that is the most important number here

**Binance perps, annualised by calendar year:**

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (part) |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 17.19% | **30.61%** | 4.16% | 7.87% | 11.92% | 5.13% | **1.94%** |
| ETHUSDT | 27.41% | **37.54%** | 0.79% | 8.26% | 12.96% | 4.93% | **0.97%** |
| SOLUSDT | −12.52% | 28.59% | −35.56% | 1.30% | 13.62% | 0.35% | −2.59% |

Hyperliquid tells the same story internally: BTC's first half of the sample
annualised **20.02%** and its second half **8.15%**; ETH **21.27%** then
**7.10%**. Fitted decay slopes are **−6.31%/yr** (BTC) and **−7.67%/yr** (ETH).

**The yield is down roughly 85% from its 2021 peak and is running at 1–2%
annualised in 2026.** This is a crowded, widely published trade and it looks
exactly like one being competed away. Every historical average below is
therefore an overstatement of what is available now, and that matters more than
any of them.

**And the carry is a bull-market phenomenon.** Correlation of daily funding with
the trailing 30-day price trend is **0.57 (BTC), 0.50 (ETH), 0.54 (SOL)**. On
BTC, uptrend days pay **5.77 bps/day** against **1.87 bps/day** in downtrends —
a 3× difference. On SOL, downtrend days pay **−0.07 bps/day**, i.e. nothing.
Correlation with realised volatility is near zero (0.14, −0.14, 0.17), so this
is a direction effect, not a volatility effect. A delta-neutral trade whose
income depends on the market rising is not as neutral as its name.

### 4. Modelling both legs, and the capital nobody counts

Long spot on Kraken/Coinbase at **40 bps/side**, short perp on Hyperliquid at
**1.5 bps/side**. Two structural facts emerged from building this that a
single-venue model would have missed:

**Equal units are already delta-flat.** A 1:1 unit hedge does not drift out of
delta as price moves — both legs scale together, and only the perp's premium to
index separates them, which is basis points. Charging rebalancing against price
volatility would be charging for work the structure does not require.

**What actually grows is the margin requirement.** A short held while price
rises has a notional and an unrealised loss that both scale up, drawn from the
same margin account. So the real choice is not how to stay delta-neutral, it is
whether to bound the capital or bound the trading cost:

| BTC, band | rebalances/yr | rebalance cost | capital / notional | net on capital |
|---|---|---|---|---|
| 2% | 324.4 | 10.65% | 1.59× | 6.84% |
| 5% | 66.1 | 4.87% | 1.59× | 7.97% |
| **10%** | **19.3** | **2.70%** | **1.70×** | **8.00%** |
| 25% | 3.5 | 1.18% | 1.87× | 7.59% |
| never resize | 0 | 0 | **5.92×** | 6.43% |

A 2% band forces over 300 resizes a year and pays 10.65% of notional to the 40
bps spot leg. Never resizing pays nothing and needs **5.92× the notional in
capital** — on SOL, which rose most, **18.55×**. The optimum is a loose band,
and it is a shallow optimum.

**Per instrument, at each one's best band, net of every modelled cost:**

| coin | band | rebalances/yr | capital/notional | funding yield | **net on capital** | max drawdown |
|---|---|---|---|---|---|---|
| ETH | 10% | 29.8 | 1.63× | 14.66% | **8.07%** | −1.34% |
| BTC | 10% | 19.3 | 1.70× | 14.55% | **8.00%** | −0.92% |
| LINK | 25% | 9.8 | 1.97× | 15.89% | **7.43%** | −5.41% |
| SOL | 25% | 13.3 | 1.95× | 12.59% | **5.86%** | −6.10% |
| ARB | 25% | 12.0 | 1.92× | 11.93% | **5.57%** | −7.40% |
| DOT | 25% | 6.9 | 1.93× | 7.27% | 3.48% | −10.42% |
| PUMP | 25% | 15.8 | 1.90× | 9.07% | 3.26% | −5.89% |
| NOT | 25% | 23.6 | 2.05× | 6.66% | 1.68% | −12.53% |
| GMX | 25% | 10.5 | 2.00× | 3.81% | 1.28% | −13.87% |
| TNSR | 25% | 30.3 | 3.02× | −32.68% | **−10.45%** | −45.44% |

HYPE and MERL could not be modelled: neither has a Binance spot listing, so the
long leg cannot be priced here. They are also the two least likely to have a
tradeable spot leg on Kraken or Coinbase, which is the same problem in a
different form.

**Return on notional would have read 1.6–3.0× higher.** That gap is the whole
reason this stage reports on capital: the spot leg consumes its full notional on
one venue and the perp margin sits on another, and both are tied up.

### 5. Failure modes, measured

**Funding flipping negative.** BTC's worst episode was **5.3 days costing
0.41%** of notional. Holding through it cost 0.405%; exiting and re-entering
costs **0.83%**, because a round trip is 2 × (40 + 1.5) bps and the spot leg
dominates. **Holding is cheaper**, and it stays cheaper for every majors
episode in the sample — the exit option is essentially never right at these
fees. On DOT (41.5 days, −5.92%) and TNSR (−46.52%) it flips, but by then the
question is whether to be in the trade at all.

**Basis risk.** Hyperliquid's premium to its own index on BTC: mean **0.65 bps**,
p99 **14.59 bps**, max **52.85 bps**. The worst adverse hourly move — a widening
premium, which hurts a short — was **38.2 bps**, or **$38.20 on a $10,000
position**. Small. But this is measured against Hyperliquid's *index*, not
against Kraken or Coinbase, so it **understates** the true cross-venue basis by
whatever the index and the actual long venue differ by. That residual is not
measured here and should not be assumed to be zero.

**Liquidation of the perp leg.** At the sample's price path, with the rebalance
band active:

| leverage | margin | capital/notional | liquidation at | breaches in sample |
|---|---|---|---|---|
| 1× | 100% | 2.00× | +50% | 0 |
| 2× | 50% | 1.50× | +25% | 0 |
| 4× | 25% | 1.25× | +12.5% | 0 |
| 5× | 20% | 1.20× | +10% | 0 |
| **10×** | **10%** | **1.10×** | **+5%** | **6** |

Zero breaches up to 5×, six at 10×. Worth noting *why* the lower leverages
survive: **rebalancing is itself liquidation protection**, because each resize
re-establishes the short at the current price. A gradual 18% rise never
liquidates; an 18% gap does. The counted breaches assume no spot-leg gains are
transferred as margin — that collateral sits on another venue, and moving it in
time is exactly the operational assumption a backtest cannot validate.

**What cannot be measured at all**, stated rather than omitted: protocol failure
or exploit on Hyperliquid; venue insolvency or withdrawal freeze on either leg
(FTX in November 2022 sits inside the Binance sample and outside the Hyperliquid
one); oracle or index manipulation; operational failure by a solo operator
running two venues with no second pair of hands; and regulatory change closing
Canadian access to Hyperliquid, which would strand the only leg that can be
short. None has a frequency in three years of price history, and a backtest that
ignores them is not conservative — it is silent.

### 6. Verdict

**Against the honest benchmark, which is cash and not zero.** At a 4% risk-free
rate, **5 of 10 modelled instruments clear it** on the historical sample: ETH
8.07%, BTC 8.00%, LINK 7.43%, SOL 5.86%, ARB 5.57%. The margin over cash is
**1.6 to 4.1 percentage points**, for a position carrying liquidation tail risk,
cross-venue operational risk, and unmodellable venue risk.

**But the historical sample is not the current regime.** Funding annualised
1.94% (BTC) and 0.97% (ETH) in 2026 against 30%+ in 2021. At 2026 funding
levels, net of the same costs, **the trade does not clear cash at all** — it is
roughly break-even before any of the risks above are priced.

**This is the first stage that has not produced a clean negative, and that makes
it the most dangerous one.** The carry existed and paid. The measured 8% is
real. What the backtest cannot establish is the part that decides it:

- **It can establish** that funding was positive on the majors, what it paid,
  how often it went negative and for how long, what the two legs cost to run,
  and how much capital they tie up.
- **It cannot establish** whether two legs on two venues can be held for years
  without an operational failure — a missed rebalance, a stuck withdrawal, a
  venue outage during a gap move, a solo operator asleep. That gap is larger
  here than for anything previously tested, because every prior strategy failed
  on arithmetic that a backtest measures well. This one passes the arithmetic
  and is decided by the part it measures worst.

The recommendation is not "trade this". It is that **the yield decay is the
finding**, and any decision should rest on current funding rather than a
three-year average that is dominated by a regime that has ended.

**Data acquired this stage:** Hyperliquid funding for 12 perps (27,761 hourly
rows for BTC), Hyperliquid perp candles, Binance USD-M funding back to 2020-01,
and Binance spot hourly for the spot leg. All free, **nothing purchased**, every
file carrying source, URL, sha256 and retrieval date in
`data/vendor/archive/manifest.jsonl`.

## Validation run — 2026-08-05 08:19 UTC

### kraken — 2026-08-02 — **PASS**

Messages: **10153342** · recorded span: 86400s · feed gaps in span: 14 (503804 ms) · recorder downtime: 0 (0 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 503804 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-08-01 19:53:53Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `book`: 10040808 · `heartbeat`: 85277 · `status`: 14 · `subscribe`: 56 · `trade`: 27187

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 10,040,780 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 4109943 | 14 | n/a | 0 (0) | 4109943 | 0 (0) | 0 | 99.42% | 100.00% | 14 (14) | 4196356 |
| ETH/USD | 5930837 | 14 | n/a | 0 (0) | 5930837 | 0 (0) | 0 | 99.42% | 100.00% | 14 (13) | 6017250 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 19575 |
| 0.01 to 0.05 ms | 4245426 |
| 0.05 to 0.1 ms | 1040735 |
| 0.1 to 0.5 ms | 424309 |
| 0.5 to 1 ms | 492517 |
| 1 to 5 ms | 2072794 |
| 5 to 10 ms | 456298 |
| 10 to 50 ms | 916467 |
| 50 to 100 ms | 286451 |
| 100 to 500 ms | 196268 |
| 500 to 1000 ms | 2395 |
| 1000 to 5000 ms | 85 |
| 5000 to 30000 ms | 9 |
| >30000 ms | 12 |

p50 ≤ 0.1 ms · p90 ≤ 50 ms · p99 ≤ 500 ms · max 221710 ms

## Validation run — 2026-08-05 08:24 UTC

### coinbase — 2026-08-02 — **PASS**

Messages: **3255935** · recorded span: 86400s · feed gaps in span: 16 (399708 ms) · recorder downtime: 0 (0 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 399708 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-08-01 22:26:13Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `heartbeats`: 85318 · `l2_data`: 2980113 · `market_trades`: 190465 · `subscriptions`: 39

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 3,255,935 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 1567537 | 14 | 0 (0) | n/a | n/a | 0 (0) | 0 | 99.54% | 100.00% | 14 (14) | 1653950 |
| ETH-USD | 1412547 | 15 | 0 (0) | n/a | n/a | 0 (0) | 0 | 99.54% | 100.00% | 15 (14) | 1498961 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 39621 |
| 0.05 to 0.1 ms | 60817 |
| 0.1 to 0.5 ms | 78918 |
| 0.5 to 1 ms | 45938 |
| 1 to 5 ms | 247512 |
| 5 to 10 ms | 242016 |
| 10 to 50 ms | 2237528 |
| 50 to 100 ms | 274769 |
| 100 to 500 ms | 28655 |
| 500 to 1000 ms | 76 |
| 1000 to 5000 ms | 56 |
| 5000 to 30000 ms | 16 |
| >30000 ms | 12 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 187372 ms

## Validation run — 2026-08-05 08:49 UTC

### kraken — 2026-08-04 — **PASS**

Messages: **17289532** · recorded span: 86400s · feed gaps in span: 15 (45523 ms) · recorder downtime: 1 (574 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 46097 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-08-03 22:30:02Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `book`: 17170910 · `heartbeat`: 86311 · `status`: 9 · `subscribe`: 36 · `trade`: 32266

Integrity mechanism: **CRC32 book checksums** · sequence numbers: n/a (this feed provides none) · book checksums: 17,170,892 checked

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USD | 7343776 | 9 | n/a | 0 (0) | 7343776 | 0 (0) | 0 | 99.95% | 100.00% | 9 (2) | 7430184 |
| ETH/USD | 9827116 | 9 | n/a | 0 (0) | 9827116 | 0 (0) | 0 | 99.95% | 100.00% | 9 (5) | 9913524 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 29807 |
| 0.01 to 0.05 ms | 7187744 |
| 0.05 to 0.1 ms | 1886206 |
| 0.1 to 0.5 ms | 1102247 |
| 0.5 to 1 ms | 958592 |
| 1 to 5 ms | 3627561 |
| 5 to 10 ms | 769701 |
| 10 to 50 ms | 1306046 |
| 50 to 100 ms | 284877 |
| 100 to 500 ms | 136129 |
| 500 to 1000 ms | 591 |
| 1000 to 5000 ms | 26 |
| 5000 to 30000 ms | 4 |
| >30000 ms | 0 |

p50 ≤ 0.1 ms · p90 ≤ 10 ms · p99 ≤ 100 ms · max 22862.5 ms

## Validation run — 2026-08-05 08:54 UTC

### coinbase — 2026-08-04 — **PASS**

Messages: **3536182** · recorded span: 86400s · feed gaps in span: 2 (2524 ms) · recorder downtime: 1 (574 ms) · unclean terminations: 0 (0 ms) · excluded from coverage: 3098 ms (all kinds unioned and clamped to the span)

Warm start: previous-day tail replayed from 2026-08-03 20:47:21Z so books are live at midnight (state only — nothing before the day is scored).

Channels: `heartbeats`: 86332 · `l2_data`: 3111381 · `market_trades`: 338460 · `subscriptions`: 9

Integrity mechanism: **envelope sequence numbers** · sequence numbers: 3,536,182 checked · book checksums: n/a (this feed provides none)

| symbol | events | snaps | seq gaps (unexpl.) | cksum fails (unexpl.) | cksums verified | crossed (unexpl.) | locked | day coverage | coverage excl. gaps | snap compares (mismatch) | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC-USD | 1632430 | 12 | 0 (0) | n/a | n/a | 0 (0) | 0 | 100.00% | 100.00% | 12 (6) | 1718841 |
| ETH-USD | 1478924 | 15 | 0 (0) | n/a | n/a | 0 (0) | 0 | 100.00% | 100.00% | 15 (9) | 1565338 |

| inter-message arrival | count |
|---|---|
| 0 to 0.01 ms | 0 |
| 0.01 to 0.05 ms | 36637 |
| 0.05 to 0.1 ms | 57401 |
| 0.1 to 0.5 ms | 89297 |
| 0.5 to 1 ms | 50783 |
| 1 to 5 ms | 348592 |
| 5 to 10 ms | 322326 |
| 10 to 50 ms | 2373391 |
| 50 to 100 ms | 237739 |
| 100 to 500 ms | 19938 |
| 500 to 1000 ms | 56 |
| 1000 to 5000 ms | 18 |
| 5000 to 30000 ms | 2 |
| >30000 ms | 1 |

p50 ≤ 50 ms · p90 ≤ 50 ms · p99 ≤ 100 ms · max 47848.4 ms

## Stage C.13 — cross-sectional funding carry — 2026-08-05

C.11 tested cash-and-carry and found the yield real but decayed ~85%. This
stage tests a different structure on the same income stream: **long the perps
paying the most negative funding, short those paying the most positive, dollar
neutral, both legs on Hyperliquid at 1.5 bps a side.** No spot leg exists, so
the 80 bps venue that dominated every C.11 cost figure leaves the trade
entirely. The motivating observation was dispersion rather than level — C.11
measured TNSR at −32.41% annualised against HYPE at +21.60%, 54 points apart on
one venue at one moment.

**The finding is that the funding income is real and large, and the price term
eats all of it.** Net of everything the trade returns **+0.11% a year on
deployed capital** against a 4% risk-free rate.

### 1. The gate: has dispersion decayed?

This had to be answered before any construction, because a cross-sectional
strategy does not care about the funding *level* — long the cheap and short the
rich and the level cancels. What is left is the spread between instruments, and
that is a different quantity from the one C.11 measured.

**All instruments live each day, annualised, means of daily cross-sections:**

| year | mean cross-section | level | **decile spread** | stdev | IQR |
|---|---|---|---|---|---|
| 2023 | 52.5 | −2.65% | **380.58%** | 131.54% | 47.88% |
| 2024 | 129.9 | 24.87% | 156.32% | 60.96% | 19.46% |
| 2025 | 173.3 | −6.48% | 164.52% | 80.00% | 15.45% |
| 2026 (part) | 184.9 | −9.23% | 167.54% | 77.62% | 17.35% |

Read alone this says dispersion fell 57% from its 2023 peak and then **stopped
falling** — flat at 156–168% across three years. That reading is wrong, and the
control that shows why is the most useful thing this stage built.

**The same measure on a fixed cohort — the 38 instruments already live at
2023-08-10, holding universe composition constant:**

| year | cross-section | **decile spread** | IQR |
|---|---|---|---|
| 2023 | 33.8 | **241.50%** | 45.28% |
| 2024 | 36.7 | 163.61% | 19.27% |
| 2025 | 32.2 | **55.80%** | 10.22% |
| 2026 (part) | 30.0 | **53.45%** | 11.57% |

**Within a stable set of names dispersion collapsed 77%, and it did not
plateau.** The apparent flatness in the all-instruments series is the venue
listing new and wilder coins — the cross-section grew from 21 instruments to
190 — not the spread persisting. Two measurements of the same market disagree
by a factor of three, and the difference is entirely composition.

That is the same story C.11 told about the level (−85%), measured on a
different quantity, and it means the strategy is being tested on a spread that
has largely closed. Everything below is therefore a historical measurement, and
the 2023-heavy portion of it is not available now.

The IQR falls faster than the standard deviation in both series (−68% against
−39%), which says the remaining dispersion has retreated into a few extreme
names rather than being spread across the book. A strategy relying on it needs
those specific names to be tradeable at size, which this study does not
establish.

### 2. Universe, and why it is survivorship-free by construction

**232 perps considered, 231 usable, 55 of them delisted, 55 dying inside the
sample.** 4,411,046 funding observations, 1,182 trading days, zero fetch
failures.

Hyperliquid addresses perps by their **index in the `meta` universe array**, so
a delisted asset cannot be removed without renumbering every asset after it —
it is flagged in place and kept forever, and the funding and candle endpoints
keep serving its full history. FTT is still addressable with candles ending
2026-05-25; so are MATIC, UNIBOT, FRIEND and JELLY. The instruments whose
funding went pathological and then died are therefore *in* the screen, which is
exactly the population a survivorship-biased universe drops and precisely the
population a dispersion measurement is most sensitive to.

Membership is per day: an instrument is in the universe on a day the venue
published both a funding rate and a daily close for it. No rule consults the
end of the sample.

**Cross-section over time** — a strategy on 21 instruments is a different thing
from one on 190:

| | 2023-05 | 2023-12 | 2024-06 | 2025-01 | 2025-08 | 2026-08 |
|---|---|---|---|---|---|---|
| instruments live | 21 | 96 | 134 | 162 | 171 | 176 |

**The residual bias, stated plainly:** an asset purged from the array outright
would be invisible here and no check in this project could detect it. Positional
indices make that structurally unlikely and 55 retained delisted entries are the
empirical evidence, but that is evidence and not proof — and any residual bias
points toward *understating* dispersion, since the missing names would be the
extreme ones.

A second data note: C.11 reconstructed perp prices as `spot × (1 + premium)`
because the candle endpoint "cannot cover the sample". That is true at hourly
resolution — the 5,000-bar page limit is 208 days — and **false at daily**,
where 5,000 bars is 13.7 years. This stage therefore prices both legs from
Hyperliquid's own book in one request per coin, and HYPE and MERL, which C.11
could not model at all for lack of a Binance spot listing, are priced here.

### 3. The result, with the three terms kept apart

Base specification: 7-day trailing funding signal, weekly rebalance, bottom and
top decile of the live cross-section, dollar neutral, 1.5 bps maker a side.

| term | % of deployed capital, annualised |
|---|---|
| funding income | **+43.68%** |
| price return | **−42.91%** |
| trading cost | −0.66% |
| **net** | **+0.11%** |

**The funding income is real, large, and almost exactly cancelled by the price
term.** That is not a rounding artefact — it is the whole result, and it is why
ADR-036 requires these to be reported separately. A single net figure would
have hidden two effects of 40+ points each.

Deployed capital is **1.18× gross notional**, materially better than C.11's
1.6–3.0×, because both legs are margined on one venue rather than one leg
consuming its full notional on a second. That structural advantage is real and
it is not enough to matter here.

### 4. Why the price term loses, and what that makes this trade

| | |
|---|---|
| long/short basket price correlation | **−0.718** |
| beta to BTC | −0.157 (R² 0.044) |
| price-only return | **−25.85%/yr** of gross |
| funding-only return | **+51.36%/yr** of gross |
| price daily volatility | **1.81%** |
| funding daily volatility | **0.166%** |

**The price term is 10.9× more volatile than the funding term.** A trade whose
dominant source of variance is the leg that was supposed to be incidental is
not a carry trade with a residual.

The mechanism is visible and unsurprising once stated. Going long the
most-negative-funding perps means going long the instruments the market is
paying to be short — and those instruments keep falling. The negative funding is
**compensation for holding a falling asset, not a free income stream.** The
−0.718 correlation between the baskets says they diverge, and they diverge in
the direction that costs money.

The book is *not* a disguised market bet: beta to BTC is −0.157 with R² 0.044,
so BTC explains 4% of its price variance. That is the one thing dollar
neutrality did buy. It bought neutrality to the market and no protection at all
from the cross-section.

**Per year, funding and price apart:**

| year | funding | price | gross |
|---|---|---|---|
| 2023 | +69.30% | **−103.40%** | −34.09% |
| 2024 | +33.10% | −43.27% | −10.17% |
| 2025 | +40.89% | −19.62% | +21.26% |
| 2026 (part) | +39.41% | −18.19% | +21.22% |

The price drag was worst in 2023, when the cross-section was smallest and most
dominated by newly listed coins, and has shrunk since. Gross turns positive in
2025–26 — but gross excludes cost, and the base specification's *net* over the
whole sample is +0.11%.

### 5. Turnover, cost, and the break-even that decides it

| rebalance | turnover/rebalance | turnover/yr | funding | price | cost | **net** | max DD |
|---|---|---|---|---|---|---|---|
| 1 d | 27.5% | 100.9× | +94.20% | −84.63% | −2.25% | **+7.32%** | −72.4% |
| 3 d | 58.0% | 71.1× | +91.41% | −68.18% | −1.72% | **+21.51%** | −87.6% |
| **7 d** | **98.1%** | **51.7×** | **+43.68%** | **−42.91%** | **−0.66%** | **+0.11%** | **−75.9%** |
| 14 d | 123.4% | 32.7× | +36.28% | −44.54% | −0.36% | −8.62% | −76.3% |
| 30 d | 138.9% | 17.7× | +22.70% | −32.69% | −0.17% | −10.15% | −57.9% |

**Break-even transaction cost at the base specification is 1.76 bps a side
against 1.5 bps modelled** — a margin of 17%. This is the opposite of H4, where
break-even was 300–550 bps against a 3 bps venue and cost was nowhere near
binding. Here cost is *nearly* binding: a fee tier change, or the taker fills a
51× annual turnover would realistically incur, erases the result outright.

**And the parameter surface is noise.** Net ranges from −10.15% to +51.61%
across the sweep with no stable optimum: 3-day rebalancing returns +21.51%,
7-day +0.11%, 14-day −8.62%. The best cell in the whole sweep — 3 names a side,
+51.61%/yr, break-even fee 58.63 bps — carries a **−124.43% drawdown**, meaning
the equity fell further than the capital deployed against it. A concentrated
3-versus-3 book across a 138-instrument cross-section is variance, not edge.
**A result that swings 60 points on the choice of rebalance interval is being
fitted to the sample.**

### 6. Deployed capital, drawdown, and the regimes this cannot see

| | |
|---|---|
| deployed capital / gross notional | **1.18×** |
| net on capital | **+0.11%/yr** |
| net on notional | +0.14%/yr |
| **max drawdown** | **−75.85% of capital** |
| worst 30 days | −41.49% (from 2023-10-17) |
| worst 90 days | −48.05% (from 2023-10-16) |
| forced exits on delisting | 20 |
| held days with no price while still listed | 0 |

A −75.85% drawdown for +0.11% a year is not a trade-off anyone should take.

**Regimes absent, stated rather than omitted:** Hyperliquid launched 2023-05-12,
*after* the 2022 drawdown, so **no bear market sits inside this history at
all**. The sample holds the 2023 recovery, the 2024 bull run and the 2025–26
compression. A dollar-neutral book's price term is exactly what an untested
regime moves, and the one regime most likely to move it is the one missing.

### 7. Verdict

**Against cash at 4%, not against zero: the strategy returns +0.11% and fails
to clear the benchmark by 3.89 points.** It does not survive at current
dispersion levels, and it did not survive at historical ones either.

Three findings, in the order that matters:

1. **Dispersion has decayed like the level did.** 77% within a fixed cohort,
   from 241.5% to 53.45%. The all-instruments series looks flat only because the
   venue kept listing wilder coins; two measures of the same market differ by
   3× and the difference is entirely composition. The spread this stage set out
   to harvest has largely closed.

2. **This is not a carry trade.** The price term is 10.9× more volatile than
   the funding term and cancels it almost exactly (+43.68% against −42.91%).
   Negative funding is compensation for holding assets that keep falling, and
   the long/short basket correlation of −0.718 says the two legs diverge in the
   costly direction. Dollar neutrality bought market neutrality — beta −0.157,
   R² 0.044 — and bought nothing at all against the cross-section.

3. **Cost is nearly binding, unlike H4.** Break-even 1.76 bps against 1.5 bps
   modelled at 51.7× annual turnover. There is no margin for a fee change, a
   taker fill, or slippage.

**Data acquired this stage: nothing purchased.** 232 perps of funding history
and daily candles from Hyperliquid's free unauthenticated info endpoint, every
page stored immutably with source, URL, sha256 and retrieval date in
`data/vendor/archive/manifest.jsonl`.

## Stage C.14 — diagnosing the directional prediction failure — 2026-08-05

Two different failures were filed under one heading. On crypto spot AUC reached
0.941 at 100 ms against roughly 0.03 bps of gross capture — real discrimination
that could never pay 80 bps. On CME MBT AUC was 0.501 at 900 s, a coin flip.
This stage is a diagnostic, not a rescue attempt, and it confirms both closures
with better explanations than existed before.

### 0. The bars, as written before anything was computed

All thresholds below were committed to `progress.md` in **commit a2d7466**,
before a single C.14 figure was produced. The commit order is the evidence. No
bar was moved afterwards, and one place where the *code* disagreed with the
registered text was fixed in favour of the text (see §1).

| task | pass condition, as registered |
|---|---|
| 1 confidence vs magnitude | **confirms closure**: \|rho\| < 0.05 everywhere AND top-decile capture < 2× all-sample · **filter (weak)**: rho ≥ +0.10 AND ratio ≥ 2× · **filter (economic)**: top-decile capture ≥ 80 bps |
| 2 sample stability | **stable**: max AUC range ≤ 0.05 across days AND no capture sign flip · **materially unstable**: range > 0.10 at any horizon OR any sign flip |
| 3 cross-venue delta | **material**: ΔAUC ≥ +0.010 at half the horizons OR Δcapture ≥ +0.50 bps · **immaterial**: ΔAUC < +0.005 everywhere |
| 4 deep learning | at **900 s**, out of sample: AUC ≥ baseline **+0.020** AND gross capture ≥ baseline **+1.00 bps**. **Both required.** Any improvement failing the leakage suite is a **leak**, not a discovery |

**Scope actually run, and what was not.** Six validated days (2026-07-30 →
2026-08-04) on Kraken BTC/USD and Coinbase BTC-USD, at **stride 3** — every
third retained event bar, which coarsens the bar without biasing which moments
are sampled (ADR-025). The ETH pair on both venues was **not run**: the full
four-symbol stride-1 sweep is roughly five hours of LightGBM fits and this
stage had a deadline. That is a real reduction in coverage and it is stated
rather than omitted.

### 1. Confidence versus magnitude — the priority, and the explanation that was missing

AUC 0.94 beside 0.03 bps of capture is not a contradiction. **AUC is
magnitude-blind**: it asks only whether up-moves score higher than down-moves.
A model that calls the sign of every 0.01 bps flicker while being useless on the
5 bps moves posts a superb AUC and captures nothing. The test is whether
confidence (`|p − 0.5|`) tracks realised `|move|`.

**Kraken BTC/USD, 6 days, 165,075 samples:**

| horizon | AUC | gross capture | **Spearman rho** | top decile | ratio |
|---|---|---|---|---|---|
| 100 ms | 0.9432 | 0.0291 bps | **−0.3175** | 0.0720 | 2.47× |
| 500 ms | 0.9079 | 0.0576 | **−0.2407** | 0.2223 | 3.86× |
| 1 s | 0.8876 | 0.0850 | **−0.2150** | 0.2922 | 3.44× |
| 5 s | 0.8299 | 0.3053 | **−0.1572** | 0.6192 | 2.03× |
| 30 s | 0.7132 | 0.7237 | −0.0465 | 1.3139 | 1.82× |
| 900 s | 0.5401 | 0.2093 | +0.0606 | 5.0020 | 23.9× |

**Coinbase BTC-USD, 6 days, 41,780 samples:** rho = −0.3665, −0.3936, −0.3855,
−0.2987 at 100 ms / 500 ms / 1 s / 5 s, on AUC of 0.8917 → 0.7202.

**The correlation is not zero. It is strongly negative.** Confidence
concentrates in the *smallest* moves — the model is surest exactly where there
is least to win — and it does so at precisely the horizons where AUC looks best.
This is a **third world the pre-registration did not anticipate**, which
imagined either no relationship or confidence concentrating in larger moves. It
supports the closure of H1 more firmly than the "uncorrelated" case the bar was
written for, because it identifies a mechanism rather than an absence.

**A correction to my own instrument, recorded because it matters.** The
registered text gates the filter branch on `rho >= 0.10`, and the branch it
gates means "high-confidence predictions concentrate in **larger** moves". The
code tested `max|rho|`, which a large *negative* correlation would satisfy while
asserting the opposite. The code was fixed to match the registered text, not the
reverse (commit 5430eba), with a regression test. Under the bar as written, the
outcome is **INCONCLUSIVE on both venues** — neither the closure branch
(|rho| < 0.05) nor the filter branch (rho ≥ +0.10) fires.

**The honest reading is that the bar was mis-specified for the world that
occurred, and the finding is not ambiguous at all.** The pre-registration is
reported as it stands rather than rewritten, which is the point of having one.

**Is there a usable filter?** No. Top-confidence deciles do capture more than
the all-sample mean — 2× to 24× — but the mechanism is **accuracy, not
magnitude**: in the top decile the model is almost always right, so capture
approaches the mean absolute move there, while the full sample is diluted by
wrong calls. The absolute numbers settle it: the best top-decile capture across
both venues and all horizons is **5.00 bps against an 80 bps round trip**. The
economic bar is missed by 16×. **H1 does not reopen.**

**Calibration: rank-ordered, not accurate.** Worst calibration gap 0.6086
(Kraken) and 0.4628 (Coinbase), mean Brier 0.163 and 0.181. Kraken is well
calibrated at short horizons (gap 0.03–0.05 out to 5 s) and badly calibrated at
long ones (0.61 at 300 s). So the model knows which way more often than it knows
how sure it is, and the probabilities should never be read as probabilities at
the horizons where a position would actually be held.

### 2. Sample stability — the headline number does not reproduce

Phase B's figures rest on 2026-07-31, one day. Six validated days now exist.

**Two days are degraded and are named rather than averaged in:** 2026-07-30 has
56 samples (the recorder started mid-day), and **2026-08-01 is missing hours
02–06 on both venues** — a host-level outage with no feed-gap record, since the
recorder was down rather than disconnected — leaving 1,204 valid samples against
~30,000 on neighbouring days.

**On the four full days, Kraken BTC/USD:**

| horizon | AUC min | AUC max | range | capture min | capture max | sign flip |
|---|---|---|---|---|---|---|
| 100 ms | 0.9345 | 0.9389 | **0.0044** | 0.0185 | 0.0322 | no |
| 1 s | 0.8769 | 0.8887 | 0.0118 | 0.0466 | 0.1077 | no |
| 30 s | 0.6671 | 0.7246 | 0.0575 | 0.5001 | 0.7324 | no |
| 300 s | 0.5003 | 0.5587 | 0.0584 | **−0.6502** | **+1.5379** | **yes** |
| 900 s | 0.5132 | 0.5438 | 0.0306 | 0.5809 | 2.3370 | no |

**On the four full days, Coinbase BTC-USD:**

| horizon | AUC min | AUC max | range | capture min | capture max | sign flip |
|---|---|---|---|---|---|---|
| 100 ms | 0.8613 | 0.8911 | 0.0298 | 0.0009 | 0.0055 | no |
| 1 s | 0.7559 | 0.8065 | 0.0506 | 0.0084 | 0.0210 | no |
| 300 s | 0.4484 | 0.5474 | 0.0990 | **−0.3863** | **+0.4817** | **yes** |
| 900 s | **0.3612** | **0.5931** | **0.2319** | **−2.4378** | **+3.0497** | **yes** |

**Verdict: MATERIALLY UNSTABLE on both venues**, and the two venues fail
differently, which is worth separating:

- **Short horizons are remarkably stable.** Kraken's AUC at 100 ms varies by
  **0.0044** across four full days (0.9345–0.9389). The 0.94 figure is real and
  it reproduces. It is also, per §1, the horizon where confidence is most
  strongly anti-correlated with magnitude.
- **Long horizons do not reproduce at all.** Coinbase's 900 s gross capture
  ranges **−2.4378 to +3.0497 bps across four full days.** Phase B's headline
  **3.31 bps at 900 s came from 2026-07-31**, which is the +3.05 day here. On
  the other three full days the same measurement is +0.15, −2.44 and +0.74.

**That is the most consequential finding in this stage.** The number that
defined H1 is a single-day draw from a distribution centred near zero. This does
not reopen H1 — it makes the closure stronger, because the capture was not
merely too small to pay, it was **not reliably positive at all**.

### 3. Cross-venue features — worth essentially nothing where they can be computed

Cross-venue lead-lag and divergence z-score ranked near the top of Phase B
feature importance and were **100% NaN in the C.8 CME run**, so that test ran
without its best-scoring feature class. Kraken and Coinbase have overlapped
since 2026-07-31, so the A/B is now computable: same days, same folds, same
splits, the seven `xv_*` columns on versus off.

**Coverage first, because absent is not zero:** `xv_mid_diff_bps` 100%,
`xv_diff_z` 99.8–100%, the lead-lag ladder 67–83% non-NaN. The features were
genuinely present, unlike C.8.

| | Kraken BTC/USD | Coinbase BTC-USD |
|---|---|---|
| max ΔAUC | **+0.0044** | **+0.0037** |
| max Δgross capture | +0.0088 bps | +0.0426 bps |
| **outcome** | **IMMATERIAL** | **IMMATERIAL** |

Both clear the registered "immaterial" threshold of ΔAUC < +0.005 at every
horizon. **The best-scoring feature class in Phase B is worth four
ten-thousandths of AUC when actually computed.** Feature importance measured
what the model leaned on, not what the model gained — a distinction this project
should carry forward.

This closes a loose end on H2: **C.8's CME failure was not caused by the missing
cross-venue features.** Had they been present they would have contributed
nothing detectable, so AUC 0.501 on MBT stands as measured.

### 4. Deep learning — the capacity question, settled

The register closed H2 on **absent signal** rather than model capacity, so more
capacity was unlikely to help. Tested once, properly, against a bar written
before training: at 900 s, out of sample, under the same purged CV and embargo,
**AUC ≥ baseline + 0.020 AND gross capture ≥ baseline + 1.00 bps.**

Two architectures only — a 2-layer MLP and a single-layer GRU over a 16-bar
window, both 64 hidden units, 6 epochs, **no hyperparameter search**. Coinbase
BTC-USD, six days, 123,864 samples at 900 s.

| horizon | model | AUC | ΔAUC | gross capture | Δcapture | passes bar |
|---|---|---|---|---|---|---|
| **900 s** | LightGBM (baseline) | 0.5301 | — | +0.0843 bps | — | — |
| | MLP | 0.4949 | **−0.0352** | **−0.2894** | −0.3737 | **no** |
| | GRU | 0.4908 | **−0.0393** | **−0.3018** | −0.3862 | **no** |
| **1 s** | LightGBM (baseline) | 0.8119 | — | +0.0215 bps | — | — |
| | MLP | 0.7944 | −0.0174 | +0.0092 | −0.0123 | no |
| | GRU | 0.7957 | −0.0161 | +0.0122 | −0.0093 | no |

**Both deep models are worse than the tree on both metrics at both horizons.**
Not short of the bar — *below the baseline*. At 900 s both post AUC under 0.50
and negative gross capture, which is to say they are worse than not trading.

**The leakage suite passed, and the canary proves that means something.**

| probe | result | threshold | passed |
|---|---|---|---|
| window causality | 0 offenders in 512 rows | none may read ahead | **yes** |
| planted-future canary | AUC **0.9714** with a future column added | ≥ 0.90 | **yes** |
| label-shift control | AUC **0.5268** on labels rolled 5,000 rows forward | ≤ 0.55 | **yes** |

The canary matters more than the other two. A clean leakage result from a probe
that cannot detect a deliberate leak certifies nothing — this project's standing
"a check that cannot fail is not a check" rule, turned on the check itself. The
canary reached 0.9714 on a planted future column, so it was capable of firing;
it did not fire on the real path, and the label-shift control collapsed to
0.5268 as an honest windowed model must.

Since no model cleared the bar, the leak-versus-discovery rule never had to be
invoked. It is recorded anyway, because the value of stating it in advance is
that it applies to results not yet seen.

**This settles the capacity question for H2.** Model capacity was not the
constraint. It also settles it for H1 in the same breath: on the venue and
instrument where H1's edge was measured, a sequential model with 16 bars of
history does not find more than a gradient-boosted tree does — and neither finds
enough.

### 5. Verdict

**Both closures are confirmed, with better explanations than existed before, and
one of them is now on firmer ground than the number that originally closed it.**

**H1 — cost-bound, and the mechanism is now named.** AUC 0.94 at 100 ms is real
and it reproduces across days to within 0.0044. It is also **magnitude-blind**:
confidence is anti-correlated with realised move size at rho ≈ **−0.32**, so the
model is surest exactly where there is least to win. The best top-confidence
decile in the study captures **5.00 bps against an 80 bps round trip**. There is
no selection filter hiding in the predictions, and the probabilities are
rank-ordered rather than accurate (worst calibration gap 0.61).

**And H1's headline number does not reproduce.** The 3.31 bps at 900 s that
defined the hypothesis came from a single day; across four full days the same
measurement ranges **−2.44 to +3.05 bps**. That does not reopen H1 — it closes
it harder, because the capture was not merely below cost, it was not reliably
positive.

**H2 — signal-absent, and neither of the two obvious escape routes exists.** The
cross-venue features that were 100% NaN in C.8 are worth **+0.004 AUC** where
they can actually be computed, so their absence did not cause that failure. And
neither an MLP nor a GRU beats the tree — both are worse — on the very instrument
where the pipeline works best, with the leakage suite passing and its canary
demonstrably able to fire.

**What this stage did not establish.** Six days is not six regimes; the sample
spans one week of one market condition, and the research-honesty rule in
CLAUDE.md applies to every figure above. The ETH pair was not run. CME was not
re-run, because Task 3 could not have rescued it and Task 4 was tested where the
signal was strongest rather than where it was weakest — if capacity cannot help
at AUC 0.94, it will not help at 0.50.

**The one thing that would change the reading** is the top-confidence decile
clearing a round trip at some venue, which would make the filter economic rather
than merely real. It missed by 16× here.

## Stage C.16 — time-series momentum on the daily archive — 2026-08-06

Every closed hypothesis assumed mean reversion or microstructure prediction.
This tested the opposite premise — trends persist, recent winners keep winning
— on C.10's survivorship-free daily universe, expecting failure and pricing the
stage accordingly: nothing bought, everything read from disk.

**Verdict up front, by the registered bars: FAIL.** No specification beats
buy-and-hold BTC on risk-adjusted terms with a deflated Sharpe above 0.95;
three beat it with deflated Sharpe barely above 0.5, all at the same holding
period, which is the registered fitting-artifact pattern. And the effect, such
as it is, lives in the untradeable tail of the universe.

### 0. The bars, as registered (commit 88b69d8, before any result)

Grid **{14, 30, 90, 180}d lookback × {7, 30, 90}d hold = 12 specifications**,
primary **L90/H30**, all cells reported. PASS required all four: net-of-3bps
Sharpe ≥ BTC buy-and-hold on the identical window; deflated Sharpe ≥ 0.95
(n_trials = 12, C.10's estimator); alpha vs BTC > 0 with t ≥ 2; ≥ 8 of 12
specs positive. Sharpes excess of 4%/yr, both sides.

### 1. Universe — C.10's, reused verbatim

Loaded from `data/processed/pairs/universe_2021-08_2026-07.json`: **60 members,
58 in the matrix** — `LUNAUSDT` excluded by the splice detector (the 177,400×
ticker-reuse bar), `BTTUSDT` at 170 observations < 200 — identical exclusions
to C.10, which is the point of reusing the construction rather than repeating
it. **12 members died in-sample** and each shows up in the simulation as a
forced exit at its last print, charged one side of fees. Universe size decays
60 → 48 live members across the sample; a universe built from today's listings
would contain none of the deaths, and momentum is the strategy most flattered
by that omission, because dead coins are past losers and this book shorts past
losers.

### 2. The grid, in full — nothing dropped

Net = 1.5 bps/side (Hyperliquid maker). BE = break-even fee per side.

| spec | gross Sharpe | net HL | net Kraken | gross %/yr | RT/yr | BE bps | beta | alpha %/yr | alpha t | **DSR** | maxDD % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| L14/H7 | 0.383 | 0.372 | 0.110 | 25.40 | 19.0 | 66.7 | −0.206 | 29.4 | 1.19 | 0.506 | −84.0 |
| L14/H30 | 0.276 | 0.272 | 0.182 | 19.60 | 6.6 | 147.9 | −0.150 | 22.5 | 0.90 | 0.417 | −100.1 |
| L14/H90 | −0.018 | −0.020 | −0.052 | 2.89 | 2.6 | 55.6 | −0.029 | 3.4 | 0.13 | 0.192 | −178.4 |
| **L30/H7** | **0.653** | **0.647** | 0.472 | 41.90 | 13.1 | 159.6 | −0.340 | 48.6 | 1.95 | **0.732** | −49.0 |
| L30/H30 | 0.266 | 0.263 | 0.172 | 19.02 | 6.6 | 143.8 | −0.197 | 22.9 | 0.91 | 0.409 | −60.6 |
| L30/H90 | 0.071 | 0.070 | 0.037 | 8.21 | 2.5 | 164.0 | −0.105 | 10.3 | 0.39 | 0.253 | −111.4 |
| L90/H7 | 0.390 | 0.385 | 0.276 | 26.40 | 8.1 | 162.2 | −0.383 | 31.5 | 1.27 | 0.515 | −77.2 |
| **L90/H30 (primary)** | 0.304 | **0.302** | 0.247 | 20.76 | 3.9 | 265.0 | **−0.290** | 24.6 | **1.01** | **0.446** | −79.9 |
| L90/H90 | −0.269 | −0.270 | −0.304 | −10.85 | 2.4 | 0.0 | −0.199 | −8.2 | −0.33 | 0.083 | −158.0 |
| L180/H7 | −0.076 | −0.080 | −0.170 | −0.15 | 6.4 | 0.0 | −0.431 | 10.5 | 0.45 | 0.173 | −169.0 |
| L180/H30 | −0.112 | −0.113 | −0.160 | −1.99 | 3.2 | 0.0 | −0.377 | 7.3 | 0.31 | 0.156 | −165.8 |
| L180/H90 | −0.013 | −0.014 | −0.040 | 3.27 | 1.9 | 85.8 | −0.367 | 12.3 | 0.49 | 0.210 | −139.4 |

Buy-and-hold BTC on the primary window (1,736 days): **+13.40%/yr, vol 51.33%,
Sharpe 0.183**.

**Consistency: 7 of 12 positive net Sharpe, median 0.167, and the sign flips
with both parameters.** L90/H30 earns +20.8%/yr; L90/H90 loses −10.9%; every
L180 cell is flat-to-negative. The three specifications that clear the literal
criterion — beat BTC with deflated Sharpe above 0.5 — are **L14/H7, L30/H7,
L90/H7: all three at the 7-day hold**. An anomaly that appears only at one
holding period is the fitting artifact the registration named in advance. The
best single cell, L30/H7 at net Sharpe 0.647, deflates to **0.732** against
twelve trials — a 27% chance of being noise even before asking whether picking
it after the fact is legitimate, which it is not.

### 3. The beta control — the expected failure did not happen, and what did is worse for the hypothesis

The registered concern was momentum-as-beta: a net-long book riding a rising
market. The measured book is the opposite. **Beta to BTC is negative in every
cell** (−0.03 to −0.43), mean net exposure at the primary is **−0.275** — the
book is net short on average — and the up/down split runs:

| primary spec | BTC trailing 30d up (872 d) | down (834 d) |
|---|---|---|
| annualised return | **−14.73%** | **+56.89%** |

The mechanism is legible: over 2021-08 → 2026-07 most alts spent most of the
sample below their trailing price, so trailing-sign momentum held them short
and collected the bleed. This is not a trend-following discovery — it is a
**short-the-alt-decline position with a long-BTC hedge missing**, earning only
while the market fell. Alpha against BTC is positive at the primary (+24.6%/yr)
but at **t = 1.01** it is one standard error from zero, and no cell in the grid
reaches t = 2.

### 4. Costs are irrelevant, exactly as predicted — which sharpens the failure

Turnover runs 1.9–19.0 round trips a year; break-even costs run **66–265 bps a
side** on positive-gross cells against 1.5 bps modelled (Hyperliquid) and 40
(Kraken, longs-only bound). Cost changes the Kraken column and nothing about
the verdict: this is the H4 pattern again — remove the cost constraint entirely
and there is no significant edge underneath. The failure is signal
significance, not friction.

### 5. Statistical versus executable — the effect lives in the untradeable tail

Of the 58-symbol matrix, **27 have a live Hyperliquid perp today**; the other
31 include every dead coin and most of the small caps whose decline the short
leg was harvesting. Kraken adds nothing (BTC/ETH spot, no shorts).

| primary L90/H30 | full universe (58) | executable subset (27) |
|---|---|---|
| net HL Sharpe | 0.302 | **0.013** |
| alpha vs BTC %/yr | 24.6 | 8.0 |
| deflated Sharpe | 0.446 | 0.223 |

**The statistical result and the executable result are different results.** On
the symbols an order could actually reach, the strategy is indistinguishable
from flat. The part of the book doing the earning is precisely the part that
cannot be traded — echoing C.10, where five of twelve subscribed perps did not
exist at the sample start, in mirror image.

### 6. Verdict

**FAIL against the registered bars**: primary beats BTC's Sharpe (0.302 vs
0.183) but fails deflation (0.446 < 0.95, and < 0.5 — the literal criterion),
fails alpha significance (t = 1.01 < 2), and fails consistency (7/12 < 8/12).
Stated plainly, as the registration requires: **no specification beats
buy-and-hold BTC on risk-adjusted terms with a deflated Sharpe above 0.95; the
three that beat it with deflated Sharpe above 0.5 are all at the 7-day hold,
deflate to noise, and evaporate on the executable subset.**

The regime caveat cuts both ways and is stated: the sample contains the 2022
collapse, the 2024 bull and the 2025–26 compression — more regime diversity
than any tick-level stage — but the strategy's entire income arrived in
down-trending periods, so a future without an alt bear removes even the
insignificant effect measured here.

**Data acquired this stage: none.** Everything read from C.10's archive; the
one network touch was the cached Hyperliquid universe snapshot for the
executability count.

## Stage C.15 — liquidation aftermath: the data does not exist — 2026-08-06

The hypothesis was that reversion after liquidation prints exceeds reversion
after ordinary trades of similar size, because a margin engine's order is
mechanical rather than informed. The stage never reached the hypothesis. Task 1
— establish whether liquidations are identifiable at all — returned a clean
negative, and the instruction for that outcome was to stop and report it as the
finding rather than proxy the label away.

### 1. Data availability, checked against the recorded bytes rather than the documentation

Four facts, in decreasing order of generality:

**The recorded feed carries no liquidation field.** Every trade fill in the
recorded week — **2,639,510 fills across 116 hour files, 2026-08-01 →
2026-08-06, twelve instruments** — has exactly one key-set:
`(coin, hash, px, side, sz, tid, time, users)`. One key-set, 2.64 million
observations, no flag.

**No channel mentions liquidations at all.** A string sweep for `liquidat` (any
case) across every recorded message in every subscribed channel — `l2Book`,
`bbo`, `trades`, `activeAssetCtx` — returns **zero occurrences** for the week.

**The one anomalous field value is not a liquidation marker.** 18.0% of fills
(473,824) carry an all-zeros `hash`. That prevalence alone rules out
liquidations, and ground truth confirms it: cross-referencing a recorded
zero-hash fill against the venue's own `userFillsByTime` endpoint matched it by
`tid` to a fill carrying `twapId` and `dir='Close Short'` with **no
`liquidation` key** — zero-hash marks scheduled/TWAP-style executions, not
forced ones.

**No public historical source exists.** Probing the info endpoint for
`liquidations`, `recentLiquidations` and `liquidationHistory` returns HTTP 422
(unknown type). The venue *does* label liquidations — `userFillsByTime` fills
carry a `liquidation` object when the fill was one — but only **per user**: you
must already know the liquidated address to ask. Enumerating liquidations you
have not yet identified is exactly the query the public API does not offer, and
labeling the recorded week through per-user queries would take one polite
request per fill-participant against 2.64M fills — weeks of querying to label
seven days of history, and nothing before 2026-08-01 at any price.

This is the C.1 lesson applied again: the check was run against recorded bytes,
not documentation, and the answer was decided by a field inventory rather than
by an assumption in either direction.

### 2. Sample size, stated honestly

**Identifiable liquidations in the recorded data: zero.** Not "low hundreds" —
the events are presumably *in* the 2.64M fills, but they carry no mark that
distinguishes them, and the entire hypothesis rests on the distinction between
mechanical and informed flow. Proxying liquidations with large trades would
erase the very thing under test, and was declined per the stage's own
instruction.

Consequently no control was computed, no reversion was measured, and **the
Task 2 bar was never registered** — registration attaches to a comparison this
data cannot support, and registering a bar for an impossible test would be
ceremony rather than discipline.

### 3. What would make this testable

Any one of: the venue adding a liquidation flag to the public trades stream; a
public global liquidation-history endpoint; or labeled vendor history covering
the subscribed instruments with timestamps alignable to recorded BBO mids at
one-second precision. The matched-control design is fully specified and waiting
in HYPOTHESES.md (H10): match by size, instrument and time of day; mid moves at
1 s / 10 s / 60 s / 300 s; 95% confidence interval sized to the actual count;
reversion judged against spread-at-event plus the 3 bps round trip, never cost
alone.

**Data acquired this stage: none.** Seven single-shot probes to the free info
endpoint; nothing purchased, nothing subscribed, recorders untouched.

## Stage C.17 — medium-horizon prediction on untested feature classes: the final research door — 2026-08-06

Ten register entries preceded this stage. The external audit identified exactly
one closure that was feature-limited rather than cost-proven: days-to-weeks
prediction, where weekly turnover makes cost structurally irrelevant, on
information classes no model here had seen. This stage tested that door with
six bars registered before any data was touched, and a condition agreed in
advance: **a FAIL ends the alpha search of this project by decision.**

**The verdict is FAIL. Zero of forty cells pass all six bars. The alpha search
of this project concluded by decision on 2026-08-06** — a choice recorded in
commit 370ba41 before the result existed, executed here exactly as written.

### 0. The bars, as registered (commit 370ba41, before any data)

Grid: feature classes surviving the availability audit (+ a combined class) ×
horizons {1, 2, 4, 8} weeks × {long-only, long-short}, weekly rebalance, BTC
and ETH, ridge λ=1 walk-forward with purge and embargo ≥ horizon, **n_trials =
40**. PASS required all six: (1) net Sharpe at Hyperliquid cost ≥ buy-and-hold
BTC on the identical window; (2) alpha vs BTC > 0 with t ≥ 2; (3) deflated
Sharpe ≥ 0.95 over 40 trials; (4) net annualised return > 4.5%; (5) executable
as specced; (6) positive net Sharpe in ≥ 2/3 of the winning class's cells.
Artifact patterns named in advance: one-horizon effects, one-variant effects,
long-only beta ≥ 0.5 in a rising sample, single-regime earnings, a combined
class outrunning its components.

### 1. Availability audit — what free actually means

| source | verdict | granularity / history | measured reality |
|---|---|---|---|
| Coin Metrics community | **usable, with a caveat that becomes the story** | daily, to genesis; BTC 6,350 obs, ETH 3,951 | `FlowInEx*/FlowOutEx*/SplyEx*` exist — genuine netflows, class B survives. **But the snapshot retrieved 2026-08-06 ends 2026-05-23: a measured 75-day staleness.** Registered rule says measured lag wins, so every CM feature carries **+75 days**. CC BY-NC 4.0. Whole-file regeneration; past rows revise. |
| DefiLlama stablecoins | usable | daily, 2017-11 → today (3,173 obs) | current through retrieval day; reconstructed history revises; lag +1 day |
| CryptoQuant free tier | **out** | — | HTTP 401 without an account key; not freely scriptable |
| Blockchain.com charts | **out** | — | reachable, but no exchange-flow series exists on the API |
| CoinGecko | not needed | — | price already on disk from the C.10 Binance archive |
| exchange-published flows | **none exists** | — | no reachable exchange publishes wallet-flow history free |

Both new sources are declared in `config/venues.yaml` (kind `archive`, ADR-031
scheme) and every retrieval is a dated immutable snapshot with sha256 in the
C.10 manifest. Funding and basis classes came from archives already on disk at
zero cost. **Lags applied: A +1d, B +75d (measured), C 0d, D 0d** — recorded
per the registration, with the planted-future canary and prefix-invariance
probes green against this pipeline (`tests/test_medium.py`).

### 2. The grid, in full — 40 cells, nothing dropped

Sample: weekly, 2020-08-02 → 2026-07-26; scored windows begin after 52 training
weeks plus embargo. Net = 1.5 bps/side. Classes: A stablecoin, B netflow,
C funding, D basis, E combined.

| cell | weeks | net %/yr | net Sharpe | DSR | beta | alpha %/yr | alpha t | BTC Sharpe same window |
|---|---|---|---|---|---|---|---|---|
| A/h1w/LO | 207 | −1.8 | −0.178 | 0.000 | 0.32 | −14.0 | −0.98 | 0.667 |
| A/h1w/LS | 207 | −37.8 | −0.733 | 0.000 | −0.38 | −23.0 | −0.85 | 0.667 |
| A/h2w/LO | 205 | −15.1 | −0.657 | 0.000 | 0.27 | −24.7 | −1.92 | 0.614 |
| A/h2w/LS | 205 | −62.1 | −1.166 | 0.000 | −0.48 | −44.9 | −1.74 | 0.614 |
| A/h4w/LO | 201 | −23.7 | −0.920 | 0.000 | 0.30 | −34.7 | −2.62 | 0.643 |
| A/h4w/LS | 201 | −79.6 | −1.493 | 0.000 | −0.42 | −63.8 | −2.42 | 0.643 |
| A/h8w/LO | 193 | −22.1 | −0.841 | 0.000 | 0.32 | −31.5 | −2.30 | 0.492 |
| A/h8w/LS | 193 | −68.2 | −1.280 | 0.000 | −0.39 | −56.9 | −2.06 | 0.492 |
| B/h1w/LO | 207 | +28.4 | 0.657 | 0.032 | **0.53** | +7.9 | 0.63 | 0.667 |
| B/h1w/LS | 207 | +22.6 | 0.426 | 0.010 | 0.04 | +21.0 | 0.95 | 0.667 |
| B/h2w/LO | 205 | +23.5 | 0.534 | 0.018 | **0.51** | +5.2 | 0.41 | 0.614 |
| B/h2w/LS | 205 | +15.1 | 0.248 | 0.004 | 0.00 | +15.0 | 0.66 | 0.614 |
| B/h4w/LO | 201 | +13.2 | 0.273 | 0.005 | 0.46 | −3.8 | −0.31 | 0.643 |
| B/h4w/LS | 201 | −5.8 | −0.229 | 0.000 | −0.10 | −2.0 | −0.09 | 0.643 |
| B/h8w/LO | 193 | +14.3 | 0.308 | 0.007 | 0.43 | +1.7 | 0.13 | 0.492 |
| B/h8w/LS | 193 | +4.5 | 0.011 | 0.001 | −0.17 | +9.4 | 0.40 | 0.492 |
| C/h1w/LO | 207 | +22.6 | 0.460 | 0.011 | **0.56** | +1.1 | 0.08 | 0.667 |
| C/h1w/LS | 207 | +11.0 | 0.135 | 0.002 | 0.10 | +7.3 | 0.28 | 0.667 |
| C/h2w/LO | 205 | +14.4 | 0.268 | 0.004 | **0.53** | −4.5 | −0.33 | 0.614 |
| C/h2w/LS | 205 | −3.3 | −0.142 | 0.000 | 0.04 | −4.5 | −0.18 | 0.614 |
| C/h4w/LO | 201 | +19.3 | 0.468 | 0.014 | 0.41 | +4.0 | 0.32 | 0.643 |
| C/h4w/LS | 201 | +6.3 | 0.045 | 0.001 | −0.20 | +13.7 | 0.54 | 0.643 |
| C/h8w/LO | 193 | +6.1 | 0.059 | 0.002 | 0.47 | −7.8 | −0.60 | 0.492 |
| C/h8w/LS | 193 | −12.0 | −0.306 | 0.000 | −0.08 | −9.6 | −0.35 | 0.492 |
| D/h1w/LO | **59** | +41.7 | 0.894 | 0.206 | 0.55 | +9.6 | 0.30 | **1.162** |
| D/h1w/LS | **59** | +37.4 | 0.634 | 0.140 | −0.04 | +39.9 | 0.79 | **1.162** |
| D/h2w/LO | **57** | +71.1 | 1.417 | 0.413 | **0.73** | +20.7 | 0.64 | **1.386** |
| D/h2w/LS | **57** | +86.6 | 1.616 | **0.499** | 0.31 | +65.1 | **1.35** | **1.386** |
| D/h4w/LO | **53** | +62.3 | 1.117 | 0.296 | **0.84** | +7.7 | 0.21 | **1.353** |
| D/h4w/LS | **53** | +72.0 | 1.155 | 0.310 | 0.51 | +38.9 | 0.70 | **1.353** |
| D/h8w/LO | **45** | +86.6 | 1.532 | 0.464 | **0.96** | −0.4 | −0.01 | **2.055** |
| D/h8w/LS | **45** | +82.2 | 1.325 | 0.384 | 0.70 | +19.2 | 0.33 | **2.055** |
| E/h1w/LO | 59 | +34.6 | 0.633 | 0.144 | 0.73 | −8.4 | −0.26 | 1.162 |
| E/h1w/LS | 59 | +23.2 | 0.352 | 0.087 | 0.33 | +3.9 | 0.08 | 1.162 |
| E/h2w/LO | 57 | +31.7 | 0.581 | 0.142 | 0.76 | −21.2 | −0.69 | 1.386 |
| E/h2w/LS | 57 | +7.8 | 0.078 | 0.056 | 0.38 | −18.6 | −0.42 | 1.386 |
| E/h4w/LO | 53 | +57.5 | 1.058 | 0.280 | 0.84 | +2.6 | 0.08 | 1.353 |
| E/h4w/LS | 53 | +62.5 | 1.117 | 0.300 | 0.52 | +28.8 | 0.60 | 1.353 |
| E/h8w/LO | 45 | +36.4 | 0.729 | 0.200 | 0.61 | −18.3 | −0.44 | 2.055 |
| E/h8w/LS | 45 | −18.3 | −0.390 | 0.032 | −0.02 | −16.6 | −0.26 | 2.055 |

Class consistency (fraction of cells with positive net Sharpe): A **0/8**,
B 7/8, C 6/8, D 8/8, E 7/8. **The best deflated Sharpe in the grid is 0.499
against a bar of 0.95; the best alpha t is 1.35 against a bar of 2.**

### 3. The beta control — every apparent success is a named artifact

**Class A (stablecoin) is worse than useless under honest lags**: negative in
all eight cells, alpha reliably negative. The free stablecoin-supply signal, as
actually available, subtracts value.

**Classes B and C are the pre-registered beta artifact.** Their positive cells
are long-only with **beta 0.43–0.56** in a net-rising sample, alpha t never
above 0.95, and up-trend returns of +29% to +68% against down-trend returns of
−15% to −30%. That is the market, sampled through a lagged feature. The
long-short variants — where beta cancels — collapse toward zero, which is the
one-variant artifact pattern named in advance.

**Class D (basis) is the seduction this registration existed to survive.**
Sharpe 0.89–1.62, returns 37–87%/yr — and **45–59 scored weeks**, because the
Hyperliquid premium series begins 2023-05 and the walk-forward consumes 52
training weeks plus embargo. Its scored window is mid-2024 onward: the bull
compression, and nothing else. On those same windows **buy-and-hold BTC's
Sharpe is 1.16–2.06** — the benchmark column, not the strategy column, is doing
the work. Beta runs to 0.96 at the long horizons; the up/down split shows
+98% to +166% in up-trends against −4% to −63% in down; the best cell's
deflated Sharpe is 0.499 — a coin flip's credibility after 40 trials. Three
registered artifact patterns at once: short single-regime window, beta-carried
long-only, and earnings in exactly one trend direction.

**Class E (combined) inherits D's window and underperforms D** — the
combined-class-outruns-components pattern did not even occur; combination
diluted.

Costs, as designed, decided nothing: break-even fees on positive cells run 22
to 1,059 bps a side against 1.5 modelled, and the long-only spot columns at 25
vs 40 bps a side change no verdict — turnover of 1.5–16.8 round trips a year
makes the cost column an afterthought, which is the one thing this stage
predicted that came true. The two cells reaching four of six bars (D/h2w, both
variants) fail precisely the two bars that measure evidence rather than
return: alpha significance and deflation.

### 4. Verdict, and the decision it triggers

**FAIL.** No cell passes all six registered bars; no cell passes the two
statistical ones individually. The prompt's requirement to say it plainly:
**no specification beats buy-and-hold BTC on risk-adjusted terms with a
deflated Sharpe at or above 0.95 — or even 0.5 — and the cells that beat it on
raw Sharpe are beta on a short window, per the artifact patterns registered in
advance.**

**Accordingly, and by the condition agreed before any data was touched: the
alpha search of this project ends by decision, dated 2026-08-06.** Eleven
register entries stand — nine tested and closed, one untestable on available
data (H10), and H7 closed by this same decision. **The census (H6) is the sole
remaining open item**, running at zero cost on data the recorders are already
capturing. The durable output of this project is the standing infrastructure:
three continuously validated recorders, a provenance-complete free-data
archive, a validation harness that has caught real defects in its own inputs,
and a register documenting to a closable standard why each of nine strategy
families does not work for a solo operator at these venues, fees, and data
access. That is the conclusion, recorded as a choice made before the result
rather than a reaction to it.

**Data acquired this stage: nothing purchased.** Two new free archives
(Coin Metrics community, DefiLlama stablecoins) declared, snapshotted, and
manifested; ~26 Binance kline months backfilled from the free dumps.
