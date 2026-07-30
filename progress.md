# Progress

Current phase: **Phase A — data pipeline** (implementation in progress)

## Phases

- [ ] **Phase A — data pipeline** ← current: storage, order book reconstruction
      validated against full recorded days
- [ ] Phase B — feature and label library, gradient boosted tree baseline, purged
      cross-validation
- [ ] Phase C — hftbacktest simulation with measured latency distributions and true fee
      tiers
- [ ] Phase D — paper trading against live feeds on a placed VPS
- [ ] Phase E — minimum viable live capital

Phase A passes only when a full day of Kraken data and a full day of Coinbase data both
reconstruct with zero unexplained crossed-book events and full-day coverage outside
logged reconnect gaps. Implementation being complete does not check the box; only
recorded data clearing `make validate` does.

## Open questions

(none yet)

## Log

- 2026-07-30 — Repo created. Scaffolding, operating docs (CLAUDE.md, README.md,
  DECISIONS.md, report.md), .gitignore and .env.example landed.
- 2026-07-30 — Python tooling landed: uv-managed pyproject with core/dev/research groups, ruff + mypy strict config, pre-commit hooks, Makefile targets (install/lint/typecheck/test/record/validate/telemetry/desktop/clean). Added zstandard and pyyaml to core beyond the spec list: zstd NDJSON capture and YAML config both require them.
- 2026-07-30 — Typed config layer landed: pydantic-settings with MLCE_ env overlay over config/default.yaml + config/venues.yaml (Kraken + Coinbase endpoints, depths, snapshot behaviour, AWS regions, documented fee tiers). Missing required secrets raise MissingSecretError at startup.
- 2026-07-30 — Market data recorder landed: asyncio Kraken (WS v2 book depth 100 + trade) and Coinbase (level2 + market_trades + heartbeats) connectors; raw exchange-native NDJSON with nanosecond receive timestamps, zstd per-message block flush, hourly rotation under data/raw/venue=/date=/hour=; jittered exponential reconnect with gaps.jsonl sidecar; structlog JSON heartbeats to logs/recorder.log; --dry-run prints first 50. Verified live: 7.7k Kraken + 1k Coinbase messages in 25s round-trip through the reader. Fixed real-world bug: Coinbase snapshots exceed websockets' 1 MiB default frame cap (raised max_size to 64 MiB).
- 2026-07-30 — Order book reconstruction landed: BookBuilder (snapshot + incremental, depth truncation, zero-qty removal, crossed/locked counting, invalid-until-snapshot on gap or checksum failure), SequenceTracker for Coinbase envelope continuity, Kraken WS v2 CRC32 checksum verification with per-symbol precisions, venue parsers, and event+interval snapshot emitter. Verified against real recorded data: 7,703 Kraken updates with zero checksum failures; Coinbase sequence-contiguous, zero crossed/locked.
- 2026-07-30 — Storage & query layer landed: documented Parquet schema for book snapshots (dict-encoded venue/symbol/kind, zstd, depth arrays), deterministic part names so reprocessing overwrites (idempotent), DuckDB helpers returning Polars frames plus per-partition coverage/size reporting. Verified end-to-end on real recorded data (3,316 rows round-tripped).
- 2026-07-30 — Validation harness landed: make validate replays every recorded venue-day (single replay implementation), scores channel counts, sequence gaps, checksum failures, crossed/locked events (explained vs unexplained via gap windows), valid-book coverage, arrival distribution, and TOB-vs-snapshot compares; regenerates processed parquet idempotently; appends dated sections to report.md and writes logs/validation_summary.json for the desktop app. Verified on real data: correct FAIL verdicts for the 24s sample (coverage < full day), zero unexplained anomalies.
- 2026-07-30 — Latency telemetry landed: scheduled RTT probes to venue public REST endpoints, rolling exact P50/P95/P99, per-venue-day Parquet (idempotent day rewrite, restart-safe seeding) plus logs/telemetry_latest.json with recent history for the desktop chart. Verified live: real probes recorded for both venues. Note on constant-latency backtest bias already in CLAUDE.md rule 3.
- 2026-07-30 — Desktop app landed: Tauri 2 Rust backend (spawns/supervises recorder+telemetry via uv with SIGTERM-graceful stop, tails structured logs as events, scans dataset inventory, reads validation/telemetry JSON, persists settings to OS config dir, window-state plugin) + React/TS/Tailwind v4 dark terminal frontend: venue status cards with live heartbeats and sparklines, latency now/chart (Recharts), coverage calendar, filterable log stream, growing 'Cortex' neural-net canvas driven by real recorded experience, Settings page (repo path, venue toggles, masked API keys stored locally only). Frontend verified: tsc clean, vite build clean, dashboard + settings render with zero console errors and designed empty states outside the shell. Rust compile not verified here (no Rust toolchain/webkit dev libs in this environment) — build steps documented in desktop/README.md.
