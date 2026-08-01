# Progress

Current phase: **Phase A — data pipeline** (implementation complete; the phase
checkbox stays unchecked until full recorded days clear `make validate`)

## Phases

- [ ] **Phase A — data pipeline** ← current: storage, order book reconstruction
      validated against full recorded days
- [ ] Phase B — feature and label library, gradient boosted tree baseline, purged
      cross-validation (pipeline built and validated 2026-08-01; the research
      conclusion stays open until it has run over enough days to cover multiple
      volatility regimes — that depends on continuous recording, not more code)
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

- 2026-07-30 — Stage 1.6 Task 1 landed: gap windows are clamped to the recorded
  span. `account_gaps` previously summed the *full* duration of every unioned
  window touching the span, so a gap that began before recording started
  contributed its entire pre-recording length to in-span gap time — the same
  class of defect as Stage 1.5 (counting time that is not a hole in recorded
  data), just smaller. Windows are now intersected with `[span_start, span_end)`
  before summing; the trimmed remainder is reported as
  `gaps_partially_outside_span` / `gap_ms_clipped_outside_span` rather than
  silently truncated. Scoping is half-open everywhere: the old `touches_span`
  used `<=`/`>=` while `GapRecord.overlaps_ns` used `<`/`>`, so a gap ending
  exactly at `span_start` was treated as touching and then counted in full. One
  predicate (`gaps_touching_span`) now serves both coverage accounting and
  anomaly explanation, so they cannot disagree. The `GapAccountingError`
  invariant is kept but re-scoped: after clamping it can only fire on genuine
  corruption (merge regression, inverted span), which the docstring says
  explicitly. 12 new tests covering gap-before-span, straddling either
  boundary, enclosing the span, exact-boundary abutment, and both corruption
  paths. Impact today is bounded — the enclosed 2026-07-31 run makes span ≈ day
  — but any partial-day run would have inflated gap time and could have
  spuriously raised `GapAccountingError`.

- 2026-07-30 — Stage 1.6 Task 2: audited the Kraken checksum-vs-sequence
  asymmetry. **It was not already correct — the harness had three ways to score
  a false pass, all now fixed.** (1) Kraken replays with `seq_ok=True`
  unconditionally, so `seq_gaps` was always 0 and the report printed `0 (0)`,
  indistinguishable from a continuity check that ran and found nothing;
  symmetrically Coinbase printed `0 (0)` checksum failures despite the feed
  providing no checksums. Both counters are now `None` when the mechanism does
  not exist and render as `n/a`, never `0`. (2) The worse hole: a Kraken symbol
  missing its `instruments` precisions builds no checksum function, so every
  update replayed *entirely unverified* and the venue-day passed on `0`
  failures out of `0` comparisons. `BookBuilder.checksums_verified` and
  `SequenceTracker.observations` now count comparisons actually performed, and
  a declared mechanism that ran zero comparisons is a FAIL. (3) The
  crossed/locked criterion is computed identically per venue (it is pure book
  state) but is only meaningful alongside whatever invalidates the book between
  snapshots — that mechanism is now named in report.md on every venue-day and
  quoted in each crossed-book failure reason. New `data/validate/integrity.py`
  owns the applicability logic; venue capability is declared in `venues.yaml`
  (`sequence_numbers: false` for Kraken, `true` for Coinbase) and defaults to
  `false` so an undeclared venue is reported n/a rather than credited.
  7 regression tests in `tests/test_integrity_scoring.py` replay both real
  fixtures end-to-end through `validate_venue_day`.

- 2026-07-30 — Stage 1.6 Task 3 landed: continuous recording is now the default
  operating mode. systemd **user** units for the recorder and telemetry probe
  under `ops/deploy/` (`Restart=always`, `RestartSec` backoff, journald,
  absolute `WorkingDirectory` and `uv` path since systemd expands neither `~`
  nor `$HOME`), documented in `ops/deploy/README.md` with
  `systemctl --user enable --now` and `loginctl enable-linger` — the latter
  being the step whose omission fails silently until the first reboot.
  `systemd-analyze --user verify` caught a real bug before install:
  `StartLimitIntervalSec` was in `[Service]`, where systemd ignores it, so the
  "five restarts in ten seconds then fail permanently" default would still have
  applied — exactly the outcome `Restart=always` is there to prevent. Moved to
  `[Unit]`; both units now verify clean. **The units are written and documented
  but deliberately NOT enabled or started** — activating them during the
  in-flight 2026-07-31 capture would start a second recorder writing the same
  hour files. Activation is the operator's call once the day validates; the
  README says so at the top. Disk guard (`data/recorder/diskguard.py`) runs on
  the heartbeat cycle and logs a warning below `disk.warn_free_gb` (50 GB) and
  an error below `disk.critical_free_gb` (20 GB); it warns only — never stops
  recording, never deletes, pinned by a test that asserts recorded bytes survive
  repeated CRITICAL readings. New `make status` reports process liveness,
  heartbeat age per venue, the current day's partition sizes and free disk, and
  exits non-zero when unhealthy so it works as a cron check. Building it
  surfaced a second real bug: substring-matching `/proc` command lines counted
  the launching `bash -c` wrapper as *both* processes, so matching is now
  token-exact on `-m <module>`. 20 new tests (68 total).

## Full-day recording run (completed)

Started: **2026-07-30T19:58:34Z** · target day to enclose: **2026-07-31 UTC**
· earliest stop: **2026-08-01T00:15Z** (margin on both ends).
**Outcome:** recorder exited cleanly 2026-08-01T01:06:40Z; all 24 hour
partitions present on both venues, zero error-level log lines; 2026-07-31
validated **PASS on both venues** (see 2026-08-01 log entry below).

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

- 2026-08-01 — Stage 1.7: full-day validation OOM diagnosed, validator made
  streaming, day-boundary warm start added, 2026-07-31 validated: **PASS on
  both venues.**
  - **Failure.** `uv run python -m data.validate --date 2026-07-31` printed both
    "validating" lines then died with exit 143 and no report section. journalctl
    shows the kernel OOM killer (global_oom, not systemd-oomd) killed python3
    three times (18:33/22:17/22:52 PDT) at 12.4–12.8 GB anon RSS on this 14 GiB
    + 4 GiB swap machine.
  - **Diagnosis (confirmed, not assumed).** A single-venue single-symbol probe
    showed RSS growing linearly with retained rows — ~2.3 KB/row, 37 MB →
    2,289 MB over 2.0M messages / 994k rows, no plateau. Cause:
    `validate_venue_day` materialized every emitted snapshot row per symbol and
    wrote Parquet once at end of day; the ~20M-message Kraken day extrapolates
    to ~23 GB. The validator had only ever been exercised on ≤30k-message
    samples — three orders of magnitude below a real day.
  - **Fix: streaming replay.** New `BookDayWriter` (data/store) streams rows as
    50k-row Parquet row groups to a temp file renamed into place on close —
    idempotent, and a crashed run never leaves a partial file at the final
    name. The replay retains only current book state, running aggregates, and a
    bounded anomaly ledger (timestamps nowhere near any gap window are counted
    unexplained immediately; only near-gap timestamps are kept for span-scoped
    re-evaluation — semantics identical to before). Progress prints every 1M
    messages with day position, elapsed time, and RSS. Memory regression guard
    (tests/test_validate_memory.py): a 400k-message synthetic day validated in
    a subprocess must stay under a 600 MB peak-RSS ceiling — 1,462 MB (RED)
    against the old code, ~440 MB streaming (GREEN). The real full day replays
    at a flat ~430–445 MB.
  - **Second tooling gap found on the way: cold start at the day boundary.**
    Continuous recording keeps one WS session running across days, so a day's
    opening book snapshot lives in the *previous* date's partition; replayed
    cold, real 2026-08-01 scored 0% coverage and 0 checksums verified despite
    lossless capture. Fix: warm-start replay (data/validate/warmup.py) locates
    the previous day's last snapshot per symbol (newest hour first), replays
    that tail through midnight building state only, resets all counters at the
    boundary, and preserves sequence continuity across midnight — a
    cross-boundary sequence break is scored to the day (pinned by test).
    report.md now states warm vs cold start on every venue-day.
  - **Partial day exercised for real.** 2026-08-01 (66-minute span) went
    through span-clamped gap accounting twice without `GapAccountingError`;
    with warm start both venues cover exactly the recorded span (4.63% of the
    calendar day) and fail only the full-day coverage criterion — the correct
    verdict for a partial day.
  - **Verdict for 2026-07-31 (report.md section "2026-08-01 06:52 UTC"): PASS
    on both venues.** Kraken: 17,489,620 msgs over the full 86,400 s span, 6
    feed gaps (12,883 ms unioned+clamped), CRC32 mechanism performed
    17,361,554 comparisons — BTC/USD 7,745,333 events, 7,745,333 checksums
    verified, 0 failures (0 unexplained), 0 crossed, 0 locked, day coverage
    100.00%; ETH/USD 9,616,221 events, 9,616,221 verified, 0 (0), 0 crossed,
    100.00%. Coinbase: 3,408,568 msgs over 86,400 s, 5 feed gaps (6,155 ms),
    sequence mechanism performed 3,408,568 comparisons — BTC-USD 1,588,608
    events, 0 seq gaps (0 unexplained), 0 crossed, 100.00%; ETH-USD 1,457,355
    events, 0 (0), 0 crossed, 100.00%. Rows regenerated: 7,831,738 + 9,702,626
    (kraken), 1,675,019 + 1,543,769 (coinbase).
  - **Noted honestly, on the record:** (1) "coverage excl. gaps" prints
    100.01–100.02%: a book that stays valid across a reconnect credits the gap
    interval to the numerator while the denominator excludes it. The error is
    bounded by unioned in-span gap time (≤12.9 s ≈ 0.015% here); true
    outside-gap coverage is ≈99.985%, comfortably above the 99.9% threshold,
    so the verdict is unaffected — but the artifact should be cleaned up
    before coverage numbers feed anything downstream. (2) TOB-vs-snapshot
    compares mismatch at some reconnect snapshots (coinbase 7 of 12 and 9 of
    15, kraken 0 of 6 and 2 of 6): expected staleness across a disconnect,
    informational, not a pass/fail criterion.
  - Phase A checkbox intentionally left unchecked — both venue-days meet the
    stated criteria, but checking the box is the operator's call.

- 2026-08-01 — Stage 1.8: process lifecycle gaps. Recorder downtime is now a
  recorded, explained gap kind instead of an invisible hole.
  - **Problem.** gaps.jsonl only records disconnects the recorder observed
    while running; systemd restarts, crashes, OOM kills, reboots, and manual
    stops left no record. Tonight's real case: down 01:06:40Z→07:11:59Z with
    nothing in either venue's gaps.jsonl. Validation subtracts only logged
    gaps, and Phase B will exclude feature windows only inside logged gaps —
    so a long unlogged outage read as an unexplained coverage failure and a
    two-second restart left a spannable discontinuity nothing flagged.
  - **Fix.** Session markers (`sessions.jsonl` per venue, written by the
    recorder: `start` on startup before connecting, `end` in the graceful
    SIGTERM path; dry-run writes none, same rule as gap records). Validation
    derives downtime gaps from the marker sequence: end→start = clean
    `downtime` gap; start→start with no end between = the previous process
    died uncleanly, gap measured from last observed activity (final raw
    message on disk) and marked `unclean`, never silently treated as clean.
    Derived gaps flow through the same span clamping, unioning, and anomaly
    explanation as feed gaps; report.md now shows feed gaps, recorder
    downtime, and unclean terminations separately plus the unioned total that
    coverage excludes. 9 new tests (85 total).
  - **Coverage numerator fixed while proving it.** The known 100.01% artifact
    became a 34-point lie on 2026-08-01: books left "valid" across the 6-hour
    downtime credited the hole as covered (41.6% claimed). Credited intervals
    now subtract their overlap with the gap-window union, so numerator and
    denominator agree on what a gap is. 2026-07-31 remains PASS (coverage
    prints ≤100.00% now); the artifact noted in the Stage 1.7 entry is closed.
  - **Backfill.** Markers written for what logs document (recorder's own
    structlog timestamps): end 01:06:40.445906Z, start 07:11:59.279027Z, end
    07:12:53.345944Z, start 07:12:53.681722Z, and end 07:26:17.581971Z for
    the old-code process stopped by tonight's deliberate restart (it predates
    the feature, so it could not write its own). Sidecar records only; raw
    captured data untouched.
  - **Live confirmation.** `systemctl --user restart mlce-recorder` at
    07:26:17Z: the new code wrote its start marker (07:26:17.909Z) unprompted,
    and validation derives three clean downtime gaps per venue — 21,918,833 ms
    (the outage), 335 ms and 327 ms (the two restarts). 2026-08-01 now
    validates with `recorder downtime: 3 (21919496 ms)` explained and honest
    coverage of 7.95% (coinbase) / 8.07% (kraken) outside gaps — a partial-day
    FAIL on the full-day criterion, which is expected and not a data problem.

- 2026-08-01 — Stage 2: Phase B research layer built, leakage-tested, reviewed,
  and run end to end on the full validated 2026-07-31 day. **Everything below
  is pipeline validation, not evidence of edge** (one day, one regime; the
  standing rule is now in CLAUDE.md).
  - **What landed.** Trades extraction (`data/trades/`, raw → processed
    Parquet, venue snapshot-replays excluded); point-in-time event stream
    (`research/stream/`, local receive clock for all ordering and horizons,
    exchange ts kept but never ordered on, previous-day feature warm-up tail
    flagged and never trained on); samplers (`research/sampling/`: event bars
    default, imbalance bars, time bars for comparison only, per-venue-hour
    counts reported); 42-column feature library (`research/features/`: CKS
    order-flow imbalance, queue imbalance, Stoikov microprice displacement,
    spread, depth/slope/asymmetry/DWP, signed volume with per-venue signing
    method — Kraken venue flag, Coinbase tick rule — intensity, interarrival,
    VWAP−mid, realized vol windows, and cross-venue mid-diff bps / divergence
    z-score / lead-lag correlations on the common local clock); labels
    (`research/labels/`: fixed-horizon 100 ms–30 s, Lopez de Prado triple
    barrier with vol-scaled barriers, cost-aware net labels that must clear
    2×maker or 2×taker+spread from config/venues.yaml); purged k-fold with
    embargo + walk-forward + append-only experiment log
    (`research/validation/`, first entry logged); baselines and LightGBM with
    fixed defaults, no search (`research/models/`); Phase B report sections
    led by the caveat line; and the PerformanceReport contract
    (`backtest/reporting/`: mode backtest|paper|live required with no
    default, JSON Schema + generated desktop TS types via `make types`,
    drift-fails-CI test). No UI components, no mock reports.
  - **Leakage suite** (tests/test_leakage.py): prefix invariance (features at
    t exactly reproducible from events strictly before t, catching off-by-one
    inclusion), planted-future correlation sweep over every feature on a
    seeded random walk, and a deliberately leaky canary the detector must
    flag. All pass; the suite also runs inside every `python -m research`
    invocation and its result is quoted in report.md.
  - **Scale guards.** Extraction of a 400k-event synthetic day in a
    subprocess must stay under 900 MB peak RSS; the pending-labels buffer is
    hard-capped (oldest sample flushes censored if labels stall). Full real
    day: kraken BTC/USD 9.3M events → 153,942 valid samples in ~7 min at flat
    RSS; ETH/USD 11.2M events → 190,959 samples; coinbase ~31k/29k samples —
    the 3–9× venue rate asymmetry made visible, as designed.
  - **Code check** (python-reviewer agent over the full diff) found 2
    HIGH / 2 MEDIUM / 1 LOW, all fixed and pinned by tests before the final
    run: triple-barrier timeouts now resolve at the deadline mid (not a mid
    arbitrarily past it), the pending buffer is capped, interarrival stats
    are age-bounded to the gap-check lookback, Python floor aligned to 3.12,
    censored-sample dict entries cleaned. The pre-fix run's outputs were
    discarded and regenerated with the fixed code.
  - **Result (pipeline validation only, quoting report.md 2026-08-01 17:45
    UTC).** Direction is genuinely predictable at short horizons and decays
    exactly as microstructure literature predicts — kraken BTC/USD AUC 0.940
    at 100 ms → 0.901 (500 ms) → 0.878 (1 s) → 0.809 (5 s) → 0.668 (30 s);
    coinbase BTC-USD 0.886 → 0.552. And it is worthless net of costs at
    tier-0 fees, exactly as the cost-aware framing predicted: expected value
    per trade ≈ −50 bps (kraken maker) to −120 bps (coinbase taker) for the
    model, the regressor, and the last-sign baseline alike — the always-trade
    evaluation pays the full round trip on every prediction while typical
    mid moves at these horizons are single-digit bps. AUC 0.94 with −50 bps
    EV in one table is the whole point of ADR-009. (Metric note: hit rate at
    the shortest horizons reads low because zero-move outcomes count as
    misses; it is labeled a secondary diagnostic.)
  - **Deferred deliberately:** hyperparameter search (after the pipeline is
    trusted, per ADR-010), deep learning (ADR-010), imbalance-bar threshold
    tuning, maker queue/fill modeling (Phase C's job), and any multi-day
    conclusion — the Phase B research conclusion stays open until the
    pipeline runs over enough days to cover multiple volatility regimes,
    which depends on continuous recording, not on more code.
  - make lint / make typecheck / make test: clean (124 tests).
  - **Correction (2026-08-01, Stage C.1):** the Phase B Kraken results above
    were computed with a stale fee schedule. Kraken restructured on
    2026-07-09 to 0.40% maker / 0.80% taker at base tier; venues.yaml carried
    the pre-restructure 0.25%/0.40%. The Kraken EV numbers are therefore
    optimistic by roughly 30 bps per round trip (maker: 50 → 80 bps) — which
    strengthens, not weakens, the conclusion that nothing at these horizons
    is tradeable at retail spot fees. venues.yaml base tier corrected;
    non-base tiers still carry pre-restructure values pending verification.
