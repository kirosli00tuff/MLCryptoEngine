# Progress

Current phase: **Phase A — data pipeline** (implementation complete; the phase
checkbox stays unchecked until full recorded days clear `make validate`)

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

- **Resolved finding (2026-07-30, Stage 1.5 Task 1): the "28 gaps / 32,402 ms in a
  24-second recording" was two accounting defects amplifying one real, already-fixed
  reconnect storm.** Evidence from `data/raw/venue=coinbase/gaps.jsonl`: all 28
  records carry the identical reason `ConnectionClosedError: sent 1009 (message too
  big) frame after reading ~1.03 MB exceeds limit of 1048576 bytes` and span
  15:15:01–15:15:58 UTC — the failed `--dry-run` diagnostic run *before* the
  max_size fix landed (Stage 1 commit 34aebd5 raised the websockets frame cap to
  64 MiB; close code 1009 disappeared afterwards). The actual recording ran
  15:17:56–15:18:20; zero of the 28 gaps overlap it. Defect one: dry-run mode wrote
  gap records to the permanent sidecar despite recording no data (fixed — dry-run
  now only logs to structlog). Defect two: validation summed every gap overlapping
  the calendar day, with no union and no relationship to the recorded span (fixed —
  gaps are unioned via `merge_windows`, attributed in-span vs out-of-span, and a
  `GapAccountingError` invariant refuses to produce coverage numbers when unioned
  in-span gap time exceeds the recorded span). The 28 records remain on disk as
  evidence and are reported by the harness as out-of-span. Trust takeaway: numbers
  derived from side-channel records deserve the same cross-checking as the primary
  data — this bug would have silently poisoned every partial-day validation.
- The Rust side of the desktop app is written but was not compiled in the
  implementation environment (no Rust toolchain or webkit2gtk dev libraries
  available there). First `make desktop` on this machine will surface any
  compile fixups; build steps and system packages are documented in
  `desktop/README.md`. The frontend half is verified (tsc + vite build clean,
  rendered and inspected in a browser).

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
- 2026-07-30 — Deliverable 10 landed: pytest suite (27 tests) with real recorded fixtures from both venues — Kraken replay proves zero CRC32 checksum failures over the snapshot + 60 consecutive live updates; Coinbase fixture sequence-contiguous; config missing-secret failure path; Parquet round-trip schema stability (caught and fixed a real DuckDB hive-partitioning bug that silently overrode exact symbols); fake-WS reconnect test verifying gap logging and lossless capture across an abnormal 1011 close. make lint / make typecheck / make test all pass clean; frontend tsc + vite build clean. Phase A implementation complete — checkbox stays unchecked until real full-day data clears make validate.
- 2026-07-30 — Stage 1.5 Task 1 landed: gap accounting fixed. Root cause investigated from raw gaps.jsonl (see Open questions): 28 out-of-span records from the pre-max_size dry-run reconnect storm were being summed against a later 24s recording. Dry-run no longer writes gap records; merge_windows unions overlapping/duplicate windows; validation attributes gaps in-span vs out-of-span (out-of-span reported, never counted); GapAccountingError invariant fails loudly when unioned in-span gap time exceeds the recorded span. 9 regression tests added (36 total). Verified on the real polluted day: in-span gaps now 0, the 28 records surfaced with explanation, invariant holds.
- 2026-07-30 — Stage 1.5 Task 3 landed: Cortex repointed to reality. CortexPanel, ExperiencePanel, and lib/experience.ts removed — no component presents a fabricated learning metric. New FeedActivityPanel (same aesthetic) drives node population and pulse rate from live per-venue message throughput and connection state, labeled 'live from recorder heartbeats', with the Phase B model-instrument destination documented at the top of the file. New PhaseProgressPanel shows validation-derived progress plus last-validated book state (mid/spread/depth per symbol, new real fields in SymbolReport) and arrival percentiles. tsc + vite build clean.
- 2026-07-30 — Stage 1.5 Task 4: checks green (ruff/mypy/36 tests/tsc+vite). First
  Rust compile attempted: rustup 1.97.1 installed to ~/.cargo, but `cargo check`
  stops in libdbus-sys — Ubuntu 26.04 is missing webkit2gtk-4.1, gtk+-3.0, and
  dbus-1 dev packages, and installing them needs sudo (exact one-line apt command
  now in desktop/README.md). Two-minute verification capture on both venues passed
  validation's gap invariant: feed gaps in span 0 ms (unioned) ≤ recorded span; the
  28 stale dry-run records remain quarantined as out-of-span.

## Full-day recording run (in progress)

Started: **2026-07-30T19:58:34Z** · target day to enclose: **2026-07-31 UTC**
· earliest stop: **2026-08-01T00:15Z** (margin on both ends).

Exact commands used (detached; survive terminal/session exit):

```bash
cd ~/Documents/GitHub/MLCryptoEngine
setsid nohup uv run python -m data.recorder  > logs/record_run.out    2>&1 < /dev/null &
setsid nohup uv run python -m ops.telemetry  > logs/telemetry_run.out 2>&1 < /dev/null &
```

Status checks: `tail -f logs/recorder.log` (heartbeats), `pgrep -af "data.recorder|ops.telemetry"`.
After 2026-08-01T00:15Z, stop with `pkill -TERM -f "python -m data.recorder"; pkill -TERM -f "python -m ops.telemetry"`
(SIGTERM = graceful zstd flush), then run
`uv run python -m data.validate --date 2026-07-31` (or plain `make validate` to
revalidate every recorded day) and review report.md against all four Phase A
acceptance criteria. Do not check the Phase A box unless the verdict is PASS on
both venues.
