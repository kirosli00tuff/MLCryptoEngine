# MLCryptoEngine

A personal quantitative research project: a machine learning engine trained on
tick-level historical market data that detects short-horizon microstructure patterns,
targeting execution from a VPS co-located in the same cloud region as the exchange
matching engine.

**Stage 1 (this codebase) records and validates public market data only.** There is no
trading logic, no order placement, and no API key with trade or withdraw permission
anywhere in this stage.

## Venues

| Venue | Why | Matching engine | Reach from |
|---|---|---|---|
| Kraken spot | Legal for Canadian residents, deep CAD/USD books | Equinix London (LD4) | AWS eu-west-2 |
| Coinbase Advanced Trade | Legal for Canadian residents, deep USD books | AWS us-east-1 | AWS us-east-1 |
| CME micro futures | Regulated BTC/ETH exposure via Interactive Brokers | CME Globex (Aurora) | Databento feed |

Binance, Bybit, OKX and KuCoin are excluded: not legally available to Canadian
residents.

## What is here

- `data/recorder/` — lossless asyncio WebSocket capture of order book and trade feeds
  (raw exchange-native NDJSON, zstd-compressed, hourly rotation, nanosecond receive
  timestamps).
- `data/book/` — L2 order book reconstruction with sequence validation and
  crossed/locked book detection.
- `data/store/` — Parquet storage partitioned by venue/symbol/date and DuckDB query
  helpers.
- `data/validate/` — data quality harness; Phase A passes only when full days of
  Kraken and Coinbase data reconstruct with zero unexplained crossed books.
- `ops/telemetry/` — continuous round-trip latency measurement to venue REST endpoints,
  feeding Phase C backtests with measured distributions instead of guessed constants.
- `desktop/` — Tauri 2 desktop app (Rust + React + Tailwind): recorder control,
  data coverage, latency percentiles, live log stream, and settings.

## Quick start

```bash
# 1. Install Python dependencies (requires uv: https://docs.astral.sh/uv/)
make install

# 2. Copy the environment template and fill in what you need (no secrets required in Stage 1)
cp .env.example .env

# 3. Record public market data from Kraken and Coinbase
make record

# 4. In another terminal: reconstruct books and validate the recorded data
make validate

# 5. Run the desktop app (requires Rust + Node; see desktop/README.md)
make desktop
```

`make help` lists every target. See `CLAUDE.md` for the full operating manual,
`progress.md` for current status, and `DECISIONS.md` for why things are the way they
are.

## Project phases

- **Phase A** — data pipeline, storage, order book reconstruction validated *(current)*
- **Phase B** — feature and label library, gradient boosted tree baseline, purged CV
- **Phase C** — hftbacktest simulation with measured latency and true fee tiers
- **Phase D** — paper trading against live feeds on a placed VPS
- **Phase E** — minimum viable live capital
