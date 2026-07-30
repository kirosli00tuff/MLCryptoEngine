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
