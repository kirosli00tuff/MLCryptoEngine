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

- 2026-08-01 — Stage C.1: venue expansion for data collection only — CME micro
  futures via Databento and Hyperliquid perps. No trading logic, no order
  placement, no credentials with trade permission.
  - **Hyperliquid discovery (live, before hardcoding):** the info endpoint
    ({"type":"meta"}) reports 232 perp assets; BTC (szDecimals 5, maxLeverage
    40) and ETH (szDecimals 4, maxLeverage 25) exist under exactly those
    names. Live WS capture (committed as
    tests/fixtures/hyperliquid_messages.ndjson, one real message set per
    channel): l2Book is a full 20-level-per-side snapshot per push — observed
    BTC inter-snapshot intervals 0.37–5.4 s in a quiet window; bbo fires only
    on top-of-book change (px/sz/n, no depth); trades carry the taker side
    (B/A) with exchange ms time, tid, tx hash; activeAssetCtx carries
    funding/OI/mark/oracle/mid; the resubscribe ack is followed immediately
    by a fresh snapshot, which is the reconnect recovery path — no separate
    snapshot request exists or is needed.
  - **Hyperliquid recorder** (data/recorder/hyperliquid.py): four channels ×
    BTC/ETH through the existing reconnect/gap machinery; registered in
    RECORDER_TYPES but **deliberately not activated** — starting it requires
    restarting the systemd unit, which briefly interrupts Kraken/Coinbase
    (the restart gap would be self-recorded per ADR-007). Activation is the
    operator's call: `systemctl --user restart mlce-recorder`.
  - **Validation extended:** hyperliquid replays through validate_venue_day;
    integrity reports sequence numbers AND checksums as n/a (never 0) and the
    mechanism is **snapshot cadence** — inter-snapshot interval distribution
    (count/p50/p95/max per symbol), stale intervals >10 s with gap-window
    explanation, and a hard failure only for unexplained silence >60 s;
    coverage scoring unchanged. Warm-start replay is skipped (every message
    is a full book) and report.md says so instead of warning about cold start.
  - **Databento adapter** (data/databento/): GLBX.MDP3 for MES/MBT, MBP-10 →
    canonical book rows, trades → canonical trade rows, both stamped
    source="databento" with ts_ns = Databento capture-hardware clock and
    exchange_ns = CME exchange clock — the canonical schemas now carry
    source/exchange_ns columns and document that rows from different sources
    must never be ordered against each other on ts_ns. Ingest verifies
    per-instrument sequence monotonic continuity and marks checksums/cadence
    n/a. Raw DBN files live immutably under data/vendor/databento/
    (gitignored; store refuses overwrite). **No live pull yet:** fetch
    requires DATABENTO_API_KEY from the environment (free signup credit
    covers adapter validation); the mapping is validated against synthetic
    records in tests/test_databento.py until the operator provisions a key.
  - **Feature capability matrix** (research/features/capabilities.py, a
    module not prose): hyperliquid supports spread/microprice/BBO- and
    trade-derived features and NOT ofi/queue-imbalance/depth/slope;
    kraken/coinbase/cme support the full library; undeclared venues raise.
    FeatureEngine consults it at construction and nulls unsupported features;
    require_supported() raises rather than returning a value (tested).
  - **Fees:** hyperliquid base tier 1.5/4.5 bps maker/taker (verified
    2026-08-01, sources in venues.yaml comment; tiers are 14-day-weighted
    volume, not this schema's 30-day model — only base tier recorded). CME
    recorded as a conservative 4.5 bps venue-wide approximation of
    per-contract dollar fees (MBT-worst-case, dated comment; Phase C must
    model dollar fees properly). All three original schedules have now
    changed or been found stale at least once — hence ADR-012.
  - Tests: 138 total (14 new — HL channel parsing from committed real
    fixtures, cadence scoring incl. the silence failure, reconnect+gap with
    resubscribe-snapshot recovery, Databento mapping round-trips with clock
    provenance, sequence audit, capability matrix enforcement). make lint /
    make typecheck / make test clean. Existing recorder confirmed alive
    (heartbeats: kraken 3,136,023 / coinbase 1,486,994 msgs this session).

- 2026-08-01 — Stage C.2: Hyperliquid recording activated; bbo capability
  verified against recorded data; real cadence measured. **Two documented
  behaviours turned out to be wrong, in opposite directions.**
  - **Why Hyperliquid was not recording:** nothing in the recorder — it was
    already registered and would have started on the next restart. The
    misleading part was `make status`, which iterated `cfg.venues` and so
    demanded a heartbeat from `cme`, a vendor-fed venue with no recorder
    process; it printed "no heartbeat in log" forever and exited non-zero,
    which as a cron health check would have cried wolf permanently. Status
    now expects heartbeats only from venues in `RECORDER_TYPES`.
  - **Restart:** `systemctl --user restart mlce-recorder` (never a kill), so
    zstd frames closed cleanly and the lifecycle logic self-recorded the
    downtime: session end 18:51:59.364Z -> start 18:51:59.913Z, derived as a
    **548 ms clean downtime gap** on kraken and coinbase (hyperliquid's
    first session has a start marker and no prior end, correctly yielding no
    gap). All three venues then showed heartbeats <30 s old, and
    `data/raw/venue=hyperliquid/date=2026-08-01/hour=18/` appeared.
  - **bbo DOES carry best-level sizes — the matrix was right.** Checked
    171,195 recorded bbo updates: **every one** carries `px` and `sz` on
    both sides, plus `n` (resting order count). Sample shape, for later
    re-checking:
    `{"channel":"bbo","data":{"coin":"BTC","time":1785610320070,"bbo":[{"px":"62362.0","sz":"13.27152","n":29},{"px":"62363.0","sz":"1.21691","n":4}]}}`
    Microprice weights the mid by resting size, so `micro_minus_mid` is
    genuinely supported and stays in `BBO_AND_TRADE_FEATURES`. bbo also
    fires on **size-only** changes (164,821 of 171,195 updates) — better
    than the documented "on BBO change", since queue changes at a static
    touch are visible.
  - **l2Book is ~10x slower than documented — the real finding.** Documented
    minimum interval is roughly 0.5 s per block. Measured over 3,148
    intervals per coin: **p50 5,387 ms · p90 5,505 ms · p99 5,635 ms · max
    6,915 ms · zero intervals >10 s.** Remarkably regular, and ten times
    slower than advertised. Nothing sub-5-second is measurable from l2Book
    alone; the 100 ms / 500 ms / 1 s label horizons exist on this venue only
    via bbo.
  - **bbo cadence** (the channel that actually matters here): BTC p50 123 ms
    · p90 404 ms · p99 1,163 ms · max 4,789 ms (n=88,755); ETH p50 128 ms ·
    p90 440 ms · p99 1,281 ms · max 5,895 ms (n=82,438). **trades:** BTC p50
    0 ms · p90 1,497 ms · max 11,050 ms; ETH p50 67 ms · p90 1,732 ms · max
    11,041 ms (bursts share a timestamp, hence the 0 ms median).
  - **Per-feature audit of everything the matrix credits to Hyperliquid**
    (inputs checked against recorded bbo/trades, not docs): `spread_abs`,
    `spread_bps`, `micro_minus_mid` — px+sz both sides present, PASS.
    `signed_vol_1s/5s/30s`, `trade_count_5s`, `interarrival_mean_ms`,
    `interarrival_std_ms`, `vwap_minus_mid_5s`, `time_since_trade_ms` —
    trades carry coin/px/sz/side/time/tid, PASS. `rvol_1s/5s/30s`,
    `ret_1s`, `abs_ret_1s` — need mid updates inside a 1 s window; bbo at
    p50 123 ms supplies ~8/s, PASS. `xv_mid_diff_bps`, `xv_diff_z`,
    `xv_leadlag_0`, `xv_leadlag_m500`, `xv_leadlag_p500` — 500 ms bins vs
    123 ms updates, PASS. **`xv_leadlag_m100` and `xv_leadlag_p100` — FAIL:**
    100 ms bins against a 123 ms median interval leave most bins empty, so
    the correlation is a sparse subsample rather than a measurement. Both
    moved into a new `SUB_100MS_FEATURES` category and removed from
    Hyperliquid's capability set (kraken/coinbase/cme keep them).
  - **Load-bearing caveat now enforced in code:** every feature Hyperliquid
    is credited with needs the **bbo** channel, and
    `data/book/hyperliquid_parse.py` currently maps **only l2Book** (bbo is
    deliberately not merged into book state, per ADR-013). Until bbo is
    plumbed into the event stream, those features would be computed from
    5.4-second snapshots — silently stale by orders of magnitude. New
    `REQUIRED_CHANNELS` + `assert_stream_supports()` make that fail loudly;
    the plumbing itself is deferred (this stage builds no research
    components).
  - 141 tests (3 new); make lint / make typecheck / make test clean; all
    three recorders alive.

- 2026-08-02 — Stage C.2: bbo plumbed into the event stream, horizons
  extended to 15 minutes, Phase B rerun on corrected Kraken fees.
  **Headline: expected value never crosses zero at any horizon, on either
  venue, under either cost assumption.**
  - **bbo plumbing.** New `BboEvent`/`Bbo` types keep the touch structurally
    separate from book state (ADR-013): the Hyperliquid parser now emits
    both channels, bbo lands as `kind="bbo"` rows carrying best price, size
    and resting order count per side, and the feature engine takes its
    touch, mid, returns and realized vol from bbo while l2Book supplies
    depth only. A stale 5.4 s snapshot can no longer overwrite a 123 ms
    price — pinned by a test. `assert_stream_supports` now reads the
    parser's own `EMITTED_CHANNELS` rather than a hand-kept list, so the
    gate tracks the code; tests cover both directions.
  - **One classification corrected while plumbing:** `qimb_best` consumes
    exactly the inputs microprice does (best price + size, both sides), so
    it moved from `DEPTH_FEATURES` to `BBO_AND_TRADE_FEATURES`. Two
    features with identical inputs cannot live in different categories;
    Stage C.1 had put it under DEPTH by analogy with the depth ladder.
  - **Horizons 60 s / 300 s / 900 s added**, every existing horizon kept, so
    the decay curve extends rather than shifts. The embargo hazard was real
    and had a second instance: `MAX_LABEL_HORIZON_NS` was hardcoded at 30 s,
    which would have marked every 900 s label gap-validated when its label
    window was 30x longer than the window actually checked. Both now derive
    from the horizon set via `embargo_ns_for()` / `MAX_HORIZON_MS`. Three
    tests pin it: embargo scales with the longest horizon in the run, a
    long-horizon `PurgedKFold` genuinely trains on less data than a short
    one, and the triple barrier stays armed a full 15 minutes.
  - **Rerun (report.md 2026-08-02 01:05 UTC), kraken + coinbase, both cost
    modes, 8 horizons.** hyperliquid skipped — no data for 2026-07-31.
    Kraken now carries the corrected base tier (40/80 bps vs the stale
    25/40), which is why its numbers moved: maker EV floor went from ~-50 to
    ~-80 bps and taker from ~-80 to ~-160 bps. Nothing about the conclusion
    changed except its size.
  - **Zero-crossing horizon: none. It never crosses within the tested
    range**, for any venue/symbol/cost combination. Best cases at 900 s:
    kraken ETH/USD maker -76.1 bps (floor -80), coinbase BTC-USD maker
    -76.7 (floor -80), coinbase ETH-USD maker -77.4. Read the gap from the
    floor as the gross edge the model actually captures: **~3.9 bps at 900 s
    on kraken ETH/USD, ~3.3 bps on coinbase BTC-USD** — against an 80 bps
    maker round trip. Taker is worse by the full fee difference
    (kraken -156.4 at best). At 300 s kraken BTC/USD is *negative* against
    its own floor (-80.5 vs -80.0), i.e. the model there is worse than not
    trading.
  - **Shape of the decay, which is the real information.** AUC falls
    monotonically from 100 ms to ~300 s and then ticks back up: kraken
    BTC/USD 0.941 -> 0.901 -> 0.879 -> 0.813 -> 0.666 -> 0.603 -> **0.499**
    -> 0.539; coinbase BTC-USD 0.886 -> ... -> 0.551 -> 0.534 -> 0.550 ->
    0.596. Direction is highly predictable at 100 ms and indistinguishable
    from a coin flip by 300 s. The uptick at 900 s rests on one day and
    about 30 non-overlapping 15-minute windows — noise until more days
    exist, and it must not be read as edge returning at longer horizons.
  - **Interpretation, plainly.** Short horizons: real predictability, moves
    far too small to pay 80-160 bps. Long horizons: moves large enough to
    matter in principle, but predictability has decayed to nothing, and the
    captured edge (~4 bps at 900 s) is still an order of magnitude short of
    the round trip. Retail spot fees do not merely reduce this edge, they
    exceed it everywhere in the tested range. That is the case for the
    lower-fee venues Stage C.1 added, not a reason to keep extending
    horizons on these two.
  - **Task 4 — what is measurable on Hyperliquid** once its data matures,
    from its measured cadence (bbo p50 123 ms / p90 404 ms; l2Book p50
    5,387 ms). Via bbo: **500 ms and longer are measurable** (~4 updates per
    500 ms window, ~8/s), with 1 s and beyond comfortable. **100 ms is not**
    — the median inter-update interval (123 ms) exceeds the horizon, so most
    100 ms labels would resolve against the entry mid itself and collapse
    toward zero by construction. From l2Book alone only 30 s and longer
    would have been measurable, which is exactly why bbo had to be plumbed.
    Trades (BTC p50 0 ms, p90 1,497 ms) are ample for trade-derived features
    at every horizon. Net: Hyperliquid can test 500 ms -> 900 s, losing only
    the shortest horizon — and it is the venue whose 1.5/4.5 bps fees make
    the cost side of this comparison worth running at all.
  - No Hyperliquid results computed: only partial days exist.
  - 147 tests (7 new); make lint / make typecheck / make test clean; all
    three recorders confirmed alive.

- 2026-08-02 — Stage C.3: bought one CME trading day (MES + MBT), measured
  both contracts, and split the capability matrix per contract.
  **MBT is not a microstructure instrument. MES is.**
  - **Spend: $3.2053 of the $25 cap**, four requests on 2026-07-31
    (continuous front month, `stype_in="continuous"`). Estimate vs actual:
    Databento bills on *billable size*, and every delivered file matched its
    quoted billable size exactly, so the pre-request quote equalled the
    charge to the cent. Per request — estimate / billable bytes / on-disk
    zstd / wall time:
    MES mbp-10 $2.5686 / 5,515,991,008 / 369,879,307 (14.9x) / 727 s ·
    MES trades $0.5698 / 21,849,216 / 8,368,475 (2.6x) / 6 s ·
    MBT mbp-10 $0.0652 / 139,971,744 / 13,241,389 (10.6x) / 15 s ·
    MBT trades $0.0018 / 68,448 / 29,684 (2.3x) / 6 s.
    **391 MB on disk for one contract-day across four requests.**
  - **The stage prompt's cost premise was wrong, and it mattered.** Quoted
    estimates were MES 2.597/0.605 and MBT 0.402/0.016 for a ~$3.62 total;
    actual MES came in slightly cheaper and **MBT priced ~6x below the
    estimate**. More importantly the prompt reasoned that "MBT costs roughly
    eight times less than MES per day, which implies roughly eight times
    fewer billable events". The real ratio is **39x on book data**
    (5.52 GB vs 0.14 GB billable) and **319x on trades** (21.8 MB vs 68 KB).
    Sizing the sparsity gap at 8x would have badly understated it.
  - **Measured event rates, 2026-07-31, 21.00 h span each:**
    - **MES: 14,989,106 book updates (198.3/s)**, inter-update p50
      **0.084 ms**, p90 7.78 ms, p99 110.4 ms, max 2,841 ms.
      **455,192 trades**, inter-trade p50 **26.3 ms**, p90 420 ms,
      mean 177.7 ms, max 21.7 s.
    - **MBT: 380,358 book updates (5.0/s)**, inter-update p50 **1.273 ms**,
      p90 **307.1 ms**, p99 2,394.6 ms, **max 20,478,692 ms = 5.69 hours
      with no book update at all**. **1,426 trades in the entire session**,
      inter-trade p50 **10,292 ms (10.3 s)**, p90 98.0 s, mean 40.8 s,
      max 1,116,786 ms (18.6 min).
  - **Share of intervals falling below each label horizon** (how often a
    fresh observation exists inside the window) — book / trades:
    100 ms: MES 98.86% / 72.33%, MBT 81.02% / 17.59% ·
    500 ms: MES 99.94% / 91.40%, MBT 92.69% / 26.76% ·
    1 s: MES 99.99% / 95.84%, MBT 96.10% / 29.87% ·
    5 s: MES 100.00% / 99.82%, MBT 99.80% / 40.56% ·
    30 s: MES 100% / 100%, MBT 100% / 72.63% ·
    60 s: MBT trades 83.40% · 300 s: 97.27% · 900 s: 99.62%.
  - **Measurability verdict, same reasoning that moved Hyperliquid features
    into SUB_100MS_FEATURES (median update interval vs window width):**
    - **MES — every horizon in the set, 100 ms through 900 s, is
      measurable.** At p50 0.084 ms the book delivers ~1,187 updates inside
      a 100 ms window, and trades arrive every 26 ms. This is a genuine
      microstructure instrument at the full horizon range.
    - **MBT — book-derived features are measurable from 500 ms upward;
      trade-derived features are not measurable below 30 s, and short
      trade-window features are not measurable at all.** Median 10.3 s
      between trades means a 1 s window is empty in ~90% of samples and a
      5 s window in ~59%: `signed_vol_1s`, `signed_vol_5s`,
      `trade_count_5s` and `vwap_minus_mid_5s` would be constant zeros
      dressed as measurements. Saying it plainly, as instructed: **MBT is
      too sparse for short-horizon microstructure research.** Its book
      p90 of 307 ms also means ~19% of 100 ms label windows contain no
      book update, and the 5.7-hour dead spell is a hole no gap sidecar
      records (vendor data has no reconnect log) — anything computed
      across it would be stale by construction.
  - **Capability matrix restructured per contract.** A venue is not always
    homogeneous: MES and MBT share a feed, schema and clock yet differ 39x
    in book rate. `CONTRACT_CAPABILITIES[(venue, contract_root)]` now
    overrides the venue entry, with `contract_key()` normalising `MES.c.0`,
    `MESU6` and `MES` to one entry so a roll cannot silently change what a
    contract is credited with. MES gets the full library; MBT loses
    `SHORT_TRADE_WINDOW_FEATURES`. Unmeasured CME contracts fall back to the
    venue entry rather than inventing capabilities. 8 new tests.
  - **Cost per day, for future backfill decisions** (measured, not
    estimated): **MES $3.1384/day** (mbp-10 + trades), **MBT $0.0670/day**.
    Extrapolated over ~252 trading days: **MES ~$791/yr, MBT ~$17/yr**;
    book-only, MES ~$647/yr and MBT ~$16/yr. The prompt's ~$105/yr MBT
    figure assumed the 8x ratio; at the measured 39x it is ~6x cheaper
    still. See ADR-016.
  - **Databento credit balance is not retrievable:** the Python client's
    metadata API exposes `get_cost`, `get_billable_size`,
    `get_record_count`, `get_dataset_range`, `get_dataset_condition` and
    the `list_*` calls, but no account-balance method. Spend is tracked
    from per-request costs instead — $3.2053 to date.
  - Raw DBN stored immutably under `data/vendor/databento/GLBX.MDP3/
    date=2026-07-31/` (gitignored); `fetch_day` refuses to overwrite, so a
    re-run cannot silently re-bill.
  - 155 tests; make lint / make typecheck / make test clean.

- 2026-08-02 — Stage C.3 (base tasks): Databento connectivity, symbology
  resolution, cost gate, and validation of the purchased day.
  - **Credential security, checked before anything else.** `.env` is
    gitignored (`.gitignore:2`) and untracked; the key value appears in no
    tracked file and nowhere in git history (checked against every commit);
    `.env.example` lists `MLCE_DATABENTO_API_KEY` with no value. All three
    conditions already held — nothing to fix. The key now loads through the
    pydantic-settings config layer as a `SecretStr` (repr redacts to
    `**********`) and the `os.environ` path was deleted, so there is exactly
    one credential path and it fails at startup with a named variable.
    CLAUDE.md rule 4 records the distinction: a read-only market-data vendor
    key is permitted; anything that can place an order or move money is not.
  - **Task 1 — connectivity, metadata-only, zero cost.** 29 datasets visible
    under entitlements; **GLBX.MDP3 accessible**; 14 schemas (`mbo, mbp-1,
    mbp-10, tbbo, trades, bbo-1s, bbo-1m, ohlcv-1s/1m/1h/1d, definition,
    statistics, status`); range **2010-06-06 → 2026-08-02**; condition for
    2026-07-31 reports `available`.
  - **Task 2 — symbology resolved, not assumed.** `continuous → raw_symbol`
    is rejected (422 `symbology_invalid_request`); the supported pair is
    **`continuous → instrument_id`**, and `end_date` must be strictly after
    `start_date` (equal dates give 422 `data_date_range_start_on_or_after_end`).
    Resolved for 2026-07-31 with `stype_in="continuous"`:
    **`MES.c.0` → instrument_id 42003239 = raw `MESU6`** and
    **`MBT.c.0` → instrument_id 42101132 = raw `MBTN6`**. Cross-checked
    against `parent → instrument_id` (`MES.FUT`/`MBT.FUT`), which lists both
    ids under exactly those raw symbols, and against the symbology block
    Databento embeds in the purchased DBN files.
  - **Symbology finding that qualifies the amendment's MBT conclusion.**
    `MBTN6` is the **July 2026** contract and CME Micro Bitcoin futures
    expire the **last Friday of the contract month — 2026-07-31, the day
    measured**. The MBT sparsity numbers were therefore taken on an expiring
    contract, after open interest had rolled to August. `MESU6` is the
    September quarterly (expires 2026-09-18) and is unaffected. ADR-016 is
    amended: its MBT conclusion is provisional pending re-measurement on a
    non-expiry day. Budget was deliberately left unspent rather than buying
    a second day, per the stage instruction.
  - **Task 3 — cost gate (`data/databento/budget.py`).** Prices every
    request through the free metadata endpoints, checks it against
    `budget.vendor_usd_cap` (config/default.yaml, default 25 USD) minus
    cumulative spend from an append-only ledger at
    `data/vendor/spend_ledger.jsonl`, and commits the charge *before*
    issuing the request so a crash cannot lose spend. Unpriceable requests
    are refused rather than assumed cheap. `fetch_day` performs the gate
    itself, so no caller can bypass it by forgetting. 7 tests including the
    required refusal test and one proving many small requests cannot walk
    past a cap none individually breaches.
  - **Process failure, recorded.** The four downloads were issued *before*
    the gate existed, under the amended task list which omitted it —
    **$3.2054 spent ungated**. The ledger was seeded with those real charges
    rather than started at zero, so the cap reflects reality:
    **$3.2054 spent, $21.7946 remaining of $25.00, 4 requests.** A guardrail
    that arrives after the action it guards is documentation, not a
    guardrail (ADR-017).
  - **Task 5 — validation through a vendor-aware harness**
    (`data/databento/validate.py`). Ordering clock is **`ts_recv`**,
    Databento's capture-server hardware timestamp, because it is the one
    clock stamped by a single machine and monotone with respect to arrival;
    **`ts_event`** (CME matching-engine clock) is kept as reference only and
    never ordered on, and neither is ever ordered against recorder-clock
    rows (ADR-011). Integrity: MDP3 sequence continuity is verified and
    counted; **book checksums and snapshot cadence report `None`/"n/a", not
    zero** (Stage 1.6 rule).
  - **Scheduled closures handled explicitly** (`data/databento/session.py`):
    the daily 16:00-17:00 US/Central maintenance halt and the Friday-16:00
    to Sunday-17:00 weekly close are expected absence, converted through
    `zoneinfo` so DST does not silently shift them by an hour. For Friday
    2026-07-31 that leaves **21.00 h of scheduled-open time**, and coverage
    is measured against that rather than 24 h. Writing this surfaced a real
    bug: overlapping closure windows were summed without merging, so the
    Friday close and Sunday's own halt double-counted an hour — the same
    double-counting class as the Stage 1.5 gap accounting, fixed by reusing
    `merge_windows`. 5 tests.
  - **A flaw in my own coverage metric, found and fixed.** The first
    implementation counted first-to-last span minus closures, which reported
    **100% coverage for MBT while it sat on a 13-minute hole**. Coverage now
    means "fresh data existed": unexplained silences over 60 s are excluded
    from covered time and reported separately, so the metric cannot flatter
    a feed with holes in it. The fix changed MBT's verdict from PASS to
    FAIL, which is the correct answer.
  - **Validation verdict, 2026-07-31 mbp-10, against 21.00 h scheduled open:**
    - **`MES.c.0` (MESU6) — PASS.** 14,989,106 events · sequence checks
      14,989,106 with **0 regressions** · checksums n/a · snapshot cadence
      n/a · **0 out-of-order** on the ordering clock · 0 exchange-clock
      regressions · **0 crossed, 0 locked** · **coverage 100.000%** · zero
      unexplained quiet windows. This is the stage deliverable: one
      validated day.
    - **`MBT.c.0` (MBTN6) — FAIL, for a fully explained reason.** 380,358
      events, sequence-clean (0 regressions), 0 out-of-order, 0 crossed —
      but **coverage 71.494%**, with **5.986 h of scheduled-open time lost
      to unexplained silence** across 4 windows: **20,479 s (5.69 h) from
      15:18:41Z**, plus 803 s, 160 s and 109 s clustered at 15:00-15:05Z.
    - **The cause is expiry, not thin liquidity.** MBTN6 expired on
      2026-07-31; CME Bitcoin futures settle against the CF Bitcoin
      Reference Rate at 16:00 London (15:00 UTC in BST). The book stutters
      at 15:00-15:05Z and stops entirely at 15:18:41Z, running dead until
      the Friday close at 21:00Z. **The contract ceased trading mid-session
      because it expired.** The FAIL is the harness correctly refusing to
      certify a day where 29% of open time has no data.
    - This is decisive for ADR-016: the earlier "MBT is too sparse for
      short-horizon research" reading is **not a valid characterisation of
      MBT's normal liquidity** — it measured a contract dying. Re-measure on
      a mid-life contract (e.g. MBTQ6 well before its August expiry) before
      drawing any conclusion about MBT. The per-contract capability entry
      stays as the conservative default meanwhile.
  - **Budget deliberately left unspent:** $21.7946 of $25 remains. Buying a
    second MBT day to settle the expiry question was the obvious temptation
    and is explicitly out of scope for this stage.

- 2026-08-02 — Stage C.4: MBT re-measured on a mid-life contract. **The
  C.3 sparsity finding was wrong by an order of magnitude and is withdrawn.**
  - **Contract chosen:** `MBT.c.0` and `MES.c.0` on **2026-07-15**
    (Wednesday). Symbology resolved `MBT.c.0` -> instrument_id 42101132 ->
    **MBTN6**, expiring 2026-07-31, so **16 days to expiry** — clear of the
    two-week bar and clear of the back-month trap (MBTN6 is the front month,
    not a thin deferred contract; `.c.0` returns the same id on 2026-07-08,
    07-15 and 07-22). `MES.c.0` -> 42003239 -> **MESU6**, expiring
    2026-09-18, so 65 days out. Same date for both, 23.00 h scheduled-open
    (one maintenance halt, no weekend).
  - **Spend, gated:** priced first, all four requests cleared the cost gate.
    MES mbp-10 $1.8250 (3,919,183,440 B billable -> 257,740,072 B on disk,
    15.2x) · MES trades $0.4513 (17,307,408 -> 6,535,166, 2.6x) · MBT
    mbp-10 $0.7326 (1,573,286,112 -> 133,552,415, 11.8x) · MBT trades
    $0.0199 (764,784 -> 341,907, 2.2x). **Total $3.0289**; estimate matched
    billable exactly, as before. Cumulative **$6.2343 of $25.00 spent,
    $18.7657 remaining, 8 requests**. Note the stage prompt expected "well
    under one dollar" — actual is 3x that because MES mbp-10 alone is $1.83;
    the gate cleared it and it sits well inside the cap.
  - **Validation verdicts (corrected coverage metric, scheduled-closure
    aware):**
    - **MBT mbp-10 — PASS.** 4,275,234 book events over 23.00 h
      (**51.6/s**), sequence checks 4,275,234 with **0 regressions**, 0
      out-of-order, **0 crossed, 0 locked**, **coverage 100.000%**, zero
      quiet windows. Checksums and snapshot cadence n/a, not zero.
    - **MES mbp-10 — FAIL, on one criterion.** 10,649,955 events
      (**128.6/s**), 0 sequence regressions, 0 out-of-order, coverage
      100.000%, zero quiet windows — but **193 crossed book events** (plus
      14 locked) out of 10.6M, i.e. 0.0018%. Reported, not suppressed: the
      harness is right to refuse certification, and whether transient
      crossed tops are legitimate in CME MBP-10 (implied vs outright
      liquidity is the usual explanation) needs a deliberate decision rather
      than a quietly loosened threshold. **No data was altered and no check
      was relaxed to make it pass.**
  - **Measured event rates, both contracts, 2026-07-15:**
    - **MES**: book p50 **0.1 ms**, p90 50 ms, max 2,700,023 ms; trades
      360,571, interval p50 **50 ms**, p90 500 ms.
    - **MBT**: book p50 **0.5 ms**, p90 50 ms, max 126,485 ms; trades
      15,933, interval p50 **1,000 ms**, p90 30,000 ms.
  - **Share of intervals below each label horizon (book / trades):**
    100 ms: MES 98.28% / 69.83%, **MBT 96.38% / 41.28%** ·
    500 ms: MES 99.84% / 90.42%, MBT 99.28% / 49.38% ·
    1 s: MES 99.97% / 94.87%, MBT 99.74% / 55.67% ·
    5 s: MES 100.00% / 99.44%, MBT 99.99% / 80.18% ·
    30 s: MES 100% / 100%, MBT 100% / 95.86% ·
    60 s / 300 s / 900 s: MBT trades 98.44% / 99.94% / 100%.
  - **The ratio C.3 got wrong: MES/MBT = 2.49x on book events** (10,649,955
    vs 4,275,234) and **22.6x on trades** (360,571 vs 15,933), against the
    **39.4x / 319x** measured on the expiry day. MBT carries **11.2x more
    book events and 11.2x more trades** on a mid-life day than on its expiry
    day, and its median trade interval is **10x faster** (1.0 s vs 10.3 s).
  - **Capability matrix revised on evidence:** the
    `SHORT_TRADE_WINDOW_FEATURES` restriction on MBT is **removed** — both
    CME contracts now carry the full library. MBT's book supports every
    horizon (96.38% of intervals under 100 ms); its 1 s trade window is
    thinner than MES's but populated (55.7% of gaps under 1 s), and a zero
    there is a true quiet second rather than a dead contract's fabricated
    zero. The category is retained for the next genuinely thin contract,
    pinned by a test. **ADR-018 supersedes ADR-016**, which is left unedited
    as the record of how a price signal was misread as a liquidity signal.
  - **Revised backfill economics:** MBT costs **$0.7525/day** mid-life, not
    the $0.067 the expiry day implied; MES **$2.2763/day** on the same
    session. Over ~252 sessions that is roughly **$190/yr MBT vs $573/yr
    MES — 3x apart, not 47x**, and MBT is usable. Which to backfill is now a
    real choice.
  - **Standing rule added to CLAUDE.md** after a third instance of the same
    defect: any computation over time intervals unions overlapping windows
    before summing, reusing `merge_windows` rather than reimplementing it,
    and a new interval calculation is expected to have a test containing at
    least one overlapping pair. The three instances: Stage 1.5 gap
    accounting, Stage 1.6 span clamp, Stage C.3 closure windows.
  - Interval statistics moved out of a scratchpad script into
    `IntervalStats` in `data/databento/validate.py`, accumulated in the same
    single pass as validation: a log-spaced histogram plus one counter per
    label horizon, so 15M intervals cost fixed memory (4 tests, one pinning
    the bound).

- 2026-08-02 — Stage C.5: MES crossed books diagnosed and classified; crossed
  state can no longer reach the feature pipeline; backfill plan set.
  **The 193 crossings are real, expected, and entirely inside the CME
  maintenance halt. No adapter defect.**
  - **Diagnosis, on evidence, before changing anything.** Extracted all 193
    crossings from the stored MES 2026-07-15 mbp-10 file with context:
    - *Adapter mixing instruments — RULED OUT.* The file holds exactly one
      instrument_id (42003239, MESU6) across all 10,649,955 records and all
      193 crossings. No implied, spread or calendar instrument is present, so
      nothing is being merged that should be kept apart.
    - *Unhandled action semantics — RULED OUT.* Crossings occur under every
      action type (add 43, cancel 70, modify 79, trade 1), so no single
      unhandled action explains them. More fundamentally the adapter never
      applies actions: mbp-10 delivers the resolved 10-level book inside each
      record, so a crossing is present in the vendor's record as delivered.
    - *Sequencing / wrong timestamp — RULED OUT.* Crossing is detected within
      a single record, so inter-record ordering cannot manufacture it.
      (Ordering is `ts_recv` regardless, per ADR-011.)
    - *Genuine sub-millisecond transient — RULED OUT.* The inversion is bid
      7655.00 vs ask 7615.75 — 39.25 points — and persists across many
      records for roughly 15 minutes, not one update.
    - *Vendor flagged them bad — RULED OUT.* 192 of 193 carry only F_LAST
      (flags=128), the same flag 10,289,383 ordinary records carry; none is
      marked F_MAYBE_BAD_BOOK.
    - *Vendor aggregation artifact — NOT SUPPORTED, and not bought.* mbp-10
      is a derived aggregation and only `mbo` could confirm at order
      granularity; the time evidence below explains the data without it, so
      no data was purchased to settle it.
  - **What the time distribution showed: 192 of 193 crossings fall in the
    21:00Z hour** (first 21:45:22.809Z), and the last at **22:00:00.009Z**.
    21:00-22:00 UTC is the **CME daily maintenance halt** (16:00-17:00
    US/Central) already in the session calendar. Order entry and cancellation
    continue while matching is suspended, so the book legitimately crosses;
    it uncrosses at the reopen auction, which is why the final crossing lands
    9.9 ms after 22:00:00Z.
  - **Classified, not suppressed.** Crossings inside a **no-match window**
    (scheduled closure + a 1 s reopen-auction grace, bounded well above the
    measured 9.9 ms) count as `crossed_explained` and are excluded from the
    failure criterion while remaining counted and printed — the same
    treatment as out-of-span gaps and scheduled closures. A crossing outside
    those windows still fails, pinned by a test.
  - **Revalidation on the stored days:** MES 2026-07-15 **PASS** (193
    crossed, 193 explained, 0 unexplained, coverage 100.000%); MBT
    2026-07-15 **PASS** unchanged (0 crossed) — nothing was fixed at another
    contract's expense; MES 2026-07-31 PASS; MBT 2026-07-31 still correctly
    FAILS on 71.494% coverage (expiry day).
  - **Feature-level guard, independent of the cause.** `BookState` now
    carries `crossed`/`locked` — columns the schema always had but the
    stream reader silently discarded — and exposes `usable`. A crossed book
    nulls every touch- and depth-derived feature, never enters the return
    series or realized-vol windows, and drives `book_is_valid` false so the
    pipeline marks the sample invalid via the same path as gap windows.
    Trade-derived features keep flowing (trades are unaffected by an
    inverted book); locked books are counted and reported but not excluded.
    6 regression tests built from the measured timestamps and prices.
  - **Backfill recommendation (recommend only; nothing purchased):**
    - **Buy MBT first.** It is the same asset the three live recorders
      already capture, so it directly answers the question Phase B raised —
      *is BTC microstructure tradeable at ~4.5 bps taker instead of the
      80-160 bps that killed spot?* — and it enables cross-venue features
      against Kraken/Coinbase/Hyperliquid. MES is a different asset class
      and answers a new question rather than the open one. C.4 established
      MBT is adequate: 51.6 book updates/s, 96.38% of intervals under 100 ms.
    - **Contiguous months needed: 6 minimum, 12 preferred.** Walk-forward
      with a 3-month train and 1-month test window yields 3 folds at 6
      months and 9 at 12; fewer than ~6 folds cannot distinguish a real
      pattern from one regime. 12 months also spans a full seasonal cycle.
    - **Estimated cost** at measured rates (MBT $0.7525/day, MES
      $2.2763/day, ~21 sessions/month): **MBT 6 months ~$95, 12 months
      ~$190; MES 6 months ~$287, 12 months ~$574.** Both fit a sane research
      budget; buying both for 12 months is ~$764.
    - **Roll handling is mandatory before any multi-month feature run.**
      Continuous stitching (`.c.0`) splices a different instrument at each
      roll, so the price series has a discontinuity there that is a contract
      change, not a market move. **MBT rolls monthly (12 discontinuities per
      year); MES rolls quarterly (4).** Every roll boundary must be treated
      exactly like a gap window: no feature lookback and no label horizon may
      span it, and the roll timestamps come from symbology resolution rather
      than being inferred from price jumps. This is the one respect in which
      MES is the easier instrument, and it is a real cost of choosing MBT.
    - **Do not buy until roll-boundary exclusion exists**, or the first
      multi-month run will silently train across 12 contract changes.
  - **Budget: $6.2343 of $25.00 spent, $18.7657 remaining. This stage bought
    no data.**

- 2026-08-02 — Stage C.6: roll-boundary exclusion built and proven on stored
  data. **The backfill was NOT purchased: pricing returned $159.66 for six
  months against a ~$95 expectation, so the stage stopped as instructed.**
  - **Roll boundaries derived from symbology, never detected from price**
    (`data/databento/rolls.py`). `symbology.resolve` (continuous ->
    instrument_id) returns the exact date intervals per instrument, so a roll
    is a bookkeeping fact rather than a classification problem. Detection
    from price jumps was rejected because it has two failure modes: it fires
    on genuine market moves and misses quiet rolls, where adjacent contracts
    trade within a tick and the splice produces no jump at all. Resolution
    costs nothing, so it never touches the spend gate.
  - **Seven MBT rolls resolved over 2026-02-01..2026-08-02**, stored at
    `data/vendor/databento/rolls/MBT_c_0.jsonl`: 2026-02-01, 03-01, 03-29,
    04-26, 05-30, **06-27** (42012278 -> 42101132, the MBTN6 splice sitting
    between the two MBT days already on disk), and 08-01. Monthly cadence
    confirmed: consecutive boundaries are 20-40 days apart and the
    to_instrument of each chains into the from_instrument of the next.
  - **The window orientation was wrong first time, and the correction
    matters.** A sample at t reads [t - lookback, t + horizon], so it is
    unsafe exactly when that span contains the roll R, which solves to
    **t in [R - horizon, R + lookback)** — backward by the *label horizon*,
    forward by the *feature lookback*, the opposite of the natural reading.
    The first implementation had it reversed and would have excluded samples
    *after* the roll while leaving the genuinely dangerous ones (those whose
    15-minute labels reach forward across the splice) in the training set.
    Both bounds come from configured values, so extending the horizon set
    widens the exclusion automatically. Current width: 16 min per roll
    (15 min back, 1 min forward), ~1.6 h/yr for a monthly roller.
  - **Enforced through the existing invalidity path**, not a parallel one:
    roll windows join gap windows, book-invalid periods and halt-period
    crossings, and are unioned with scheduled closures before any time is
    summed — the fourth instance of the CLAUDE.md interval rule, with an
    overlapping-pair test as that rule requires. Validation reports roll
    exclusions as their own count and duration so a large exclusion is
    visible rather than absorbed into coverage.
  - **Proven on data already paid for** (Task 3): the 2026-06-27 boundary
    lies between the stored MBT days of 07-15 and 07-31; the exclusion
    covers 06-26 23:45Z -> 06-27 00:01Z; a sample 10 min before the roll is
    excluded (its label crosses), one 20 min before is not (its label
    resolves first). 6 regression tests from the real roll.
  - **Purchase stopped — pricing, per month, MBT mbp-10 + trades:**
    2026-02 $32.6706 · 2026-03 $29.9141 · 2026-04 $21.1582 · 2026-05
    $18.4347 · 2026-06 $36.1880 · 2026-07 $21.2955 · **total $159.6612**
    (mbp-10 $155.5590, trades only $4.1022 — essentially all of the cost is
    depth). That is **68% above the ~$95 expectation** and exceeds even the
    raised cap's remaining $113.77, so nothing was downloaded.
  - **Why the C.5 estimate was wrong: the per-day rate was right, the
    days-per-month multiplier was not.** C.5 projected $0.7525/day x ~21
    sessions/month x 6 = ~$95, using an equity-style 21 trading days. The
    six-month range actually bills across ~181 calendar days — CME crypto
    futures run Sunday 17:00 CT to Friday 16:00 CT, so nearly every calendar
    day carries data. Implied rate is $0.8821/day, only 17% above the
    measured single-day figure; the 68% overshoot is almost entirely the
    session-count assumption. **A per-day cost is not a per-month cost until
    you know how many days a month bills.**
  - **Options, for a deliberate decision rather than an automatic one:**
    4 months (2026-04..07) prices at **$97.08** and fits the current cap
    with $16.69 to spare, giving 2 walk-forward folds at 3-month train /
    1-month test rather than 3. Six months needs the cap raised to ~$170.
    Dropping the trades schema saves only $4.10 and would cost every
    trade-derived feature, so it is not a real economy.
  - Cap raised deliberately from 25.0 to **120.0** in config/default.yaml
    with a dated comment recording that the purchase was refused at that
    number; the gate stayed in force and refused correctly.
  - **Budget: $6.2343 spent of $120.00, $113.7657 remaining. This stage
    bought no data.**

## 2026-08-02 — Stage C.7: four-month MBT backfill, stopped at two months by an OOM in our own fetch path

**Outcome: partial. April and May 2026 are bought and validated. June was
charged and never delivered; July was never attempted. The range cannot be
completed under the $120 cap as the ledger now stands, and the cap was not
raised.**

- **Repricing (Task 1) reproduced C.6 exactly.** MBT.c.0 mbp-10 + trades:
  2026-04 $21.1582 · 2026-05 $18.4347 · 2026-06 $36.1880 · 2026-07 $21.2955
  = **$97.0764**, against C.6's $97.08 — a $0.0036 drift across sessions.
  June is a genuine 73% outlier (76.3 GB billable vs ~44 GB either side),
  not noise to average away.

- **Estimates against actuals, per month:**

  | month | quoted | charged | delivered | on disk |
  |---|---|---|---|---|
  | 2026-04 | $21.1582 | $21.1582 | yes | 3,734,780,651 B + 10,486,479 B |
  | 2026-05 | $18.4347 | $18.4347 | yes | 3,266,885,235 B + 8,504,784 B |
  | 2026-06 | $36.1880 | **$35.5144** | **no** | — |
  | 2026-07 | $21.2955 | $0.0000 | no | — |

  Quoted and charged agree to the cent **because they are the same number**:
  the gate commits the quote before issuing the request (ADR-017), so the
  ledger records intent, not a vendor-confirmed charge. This is not an
  independent reconciliation and must not be read as one. The only true
  actual is the Databento invoice.

- **Why June died: a defect in `fetch_range`, not a vendor failure.**
  `client.timeseries.get_range()` without `path` builds the entire response
  in memory before writing a byte. April (44 GB billable) and May (38.5 GB)
  fit; June (76.3 GB) grew to **9.1 GB resident and was OOM-killed** at
  19:55:43 local — `Out of memory: Killed process 4144248 (python3)
  total-vm:16005712kB, anon-rss:9105252kB` on a 14 GiB machine. The charge
  had already been committed. Fixed: downloads now stream via `path=` to a
  `.partial` sibling and are renamed only on success, so a killed process
  leaves an obviously-incomplete file rather than a truncated one at the
  real path that a later run would trust. `fetch_day` had the same latent
  bug and was routed through the same helper. 3 regression tests.

- **The four-month range no longer fits.** Ledger: **$81.3416 spent,
  $38.6584 remaining** of the $120 cap. Finishing needs $57.4835
  (June $36.1880 + July $21.2955). Re-running June alone would leave $3.14
  and the gate would then refuse July. Stopped and reported rather than
  raising the cap or silently shortening the range.
  **Whether June was actually billed is not determinable from the client** —
  `metadata` exposes `get_cost` and `get_billable_size` (pre-request
  estimates) and no usage endpoint. The stream ran ~19 minutes before the
  kill. If the Databento portal shows June was *not* billed, reversing that
  ledger entry restores $74.17 and the full four months fit with $16.69 to
  spare, no cap change. **Check the portal before any retry** — the gate
  cannot detect a double-spend it already recorded.

- **Validation (Task 3), every purchased day, MBP-10:**

  | | April | May |
  |---|---|---|
  | days scored | 26 | 27 |
  | PASS / FAIL | 24 / 2 | 26 / 1 |
  | events | 119,781,838 | 104,643,837 |
  | scheduled-open | 506.00 h | 483.00 h |
  | coverage | 97.68% | 98.76% |
  | sequence checks / regressions | 119,781,838 / **0** | 104,643,837 / **0** |
  | crossed (explained / unexplained) | 2,334 / **0** | 2,910 / **0** |
  | locked | 43 | 8 |

  224,425,675 events over 989.00 h scheduled-open, **zero sequence
  regressions and zero unexplained crossed books** across both months. Every
  crossing fell inside a scheduled no-match window, as ADR-019 predicted.

- **Roll boundaries: 7 on file, 3 interior to Apr–Jul — and that is correct,
  not a missing roll.** Splices at 04-26, 05-30, 06-27 sit between four
  contracts (42185193 → 42013708 → 42012278 → 42101132); the 03-29 and
  08-01 splices are the range's own edges. N contracts give N−1 interior
  boundaries, so 4 monthly expiries yield 3. The positive evidence that
  nothing was dropped is that the chain is contiguous — every
  `to_instrument` equals the next `from_instrument`. A missing roll would
  break that chain, which is what `tests/test_rolls.py` asserts.

- **Finding: the roll exclusion is centred on the wrong instant, and
  excludes none of the damage it exists to exclude.** Both coverage failures
  are the last Friday of the month — MBT expiry:

  | | 2026-04-24 | 2026-05-29 |
  |---|---|---|
  | coverage | 71.46% | 71.60% |
  | silent | 5.993 h | 5.965 h |
  | events | 413,952 | 555,756 |
  | roll windows / excluded | 1 / **0 s** | 1 / **0 s** |

  MBT settles at 16:00 London; CME closes at 16:00 CT = 22:00 London. That
  gap is **exactly 6 hours**, matching both silences to within two minutes.
  The `.c.0` series holds the expiring contract through settlement and does
  not splice until the *next* session, so the C.6 exclusion window — 900 s
  back, 60 s forward around the splice — lands in already-closed time and
  removes **0 seconds** of the dead book. Samples on an expiry session would
  read a settled, motionless book as if it were live. The exclusion must be
  driven by settlement time, not splice time. Not fixed in this stage; the
  data is on disk and the fix belongs with the feature build.

- **Finding: 2026-04-03 is Good Friday** — 72.62% coverage with *no* quiet
  window recorded, i.e. the feed simply ends early rather than going silent
  mid-session. `data/databento/session.py` models the daily maintenance halt
  and the weekend but has **no CME holiday calendar**, so every exchange
  holiday will fail coverage this way.

- **Finding: 2026-05-30 (Saturday) has 0 h scheduled-open and 555,474
  events, and passes.** Coverage is `nan` on a zero denominator, and a `nan`
  verdict is not a failure. A day with events but no scheduled-open time
  should be scrutinised, not waved through — same family as the Stage 1.6
  bug where the coverage metric flattered a feed with holes in it.

- **Vendor condition flags did not predict validation outcomes.** The two
  days Databento marked *degraded* — 2026-04-10 and 2026-05-24 — both passed
  at 100.00% coverage. The six *missing* days were all Saturdays, absent
  from the file with zero scheduled-open time, as expected. The three real
  failures were flagged by neither.

- **Exclusion totals: 11.958 h of 989.00 h scheduled-open = 1.21%.** All of
  it unexplained-silence time (5.993 h + 5.965 h on the two expiry days);
  roll exclusion contributed **0.0000 h**, for the reason above. Windows are
  unioned through `merge_windows` before summing, per the standing rule.

- **Per-day billing rate: it does not match C.6's implied $0.8821, and the
  per-day model is itself wrong.** Delivered months bill **$0.6491/day**
  ($39.5929 over 61 days) — **26% below** C.6's figure. But the monthly
  rates are $0.7053 (Apr), $0.5947 (May), $1.2063 (Jun), $0.6870 (Jul): a
  **2.03× spread**. C.6's constant would have mis-estimated every single
  month, low on June and high on the rest. Cost tracks market activity, not
  the calendar. **Future projections must price the actual range through
  `get_cost` — which is free — rather than multiply any per-day figure.**
  Billable-to-disk compression was stable at 11.80× (Apr) and 11.79× (May).

- **Range conditions (Task 4): two months, one regime, and the honesty rule
  applies with more force than before.** Full-session daily events span
  413,952 to 7,325,851 — 17.7×, though that low is the April expiry day;
  excluding expiry sessions the range is ~2.06M to 7.33M, about 3.6×. There
  is a visible step down inside May: 4.5–7.3M/day through 05-22, then
  2.06–4.15M/day from 05-25 on. April averages ~12% more events per
  scheduled hour than May. This is April–May 2026 only — it is **not**
  regime-diverse, and with the range halved it now spans two consecutive
  months of one season. Any Phase B metric fitted on it carries the standing
  caveat, leading the section.

- `make lint`, `make typecheck`, `make test` clean — 182 tests pass. Two
  pre-existing `zip()` lint errors in the C.6 roll code fixed to
  `itertools.pairwise`. All three crypto recorders untouched and live.

## 2026-08-03 — Stage C.8: the Phase B edge does not transfer to CME MBT

**Answer: it vanished. Costs fell 15x by changing venue; the gross edge fell
15x with them. Expected value never crosses zero at any horizon.**

- **Pipeline ran end to end on the two validated months.** 224,425,675 vendor
  events ingested to per-day Parquet (6.9 GB), 53 days of samples extracted,
  purged-CV evaluation across 8 horizons and 2 cost modes. Ordering clock is
  **`ts_recv`, Databento's capture-server hardware clock**, mapped to `ts_ns`;
  `ts_event` (CME MDP3 exchange clock) is kept as `exchange_ns` and never used
  for ordering — the same receive-side discipline the WebSocket recorders use,
  and the two are never ordered against each other.
- **Headline, 900 s maker:** Coinbase BTC-USD captured 3.31 bps gross against
  80 bps of cost (EV −76.69). MBT captures **0.22 bps** against **5.33 bps**
  (EV **−5.11**). AUC 0.596 → **0.501**. See report.md for the full table.
- **The negative result changed character, which is the useful part.** Spot had
  a real edge buried under fees — a cost problem. CME has affordable costs and
  no edge. Fixing the cost problem revealed a second, independent one.
- **The one apparent positive was checked and reversed.** +0.215 bps at 900 s
  was the only figure clearing rounding noise; a stride-1 control on 10 April
  days returns **−0.785 bps** with AUC 0.490. Noise around zero, as AUC ≈ 0.50
  implied. Nothing is handed to Phase C as a hypothesis.
- **Cost model rebuilt for per-contract fees (ADR-023).** The stage's premise —
  "CME costs under one basis point round trip" — is an MES property. MBT is
  0.1 BTC, so at April–May prices its notional is **$7,608** against MES's
  ~$34,000, and its CME exchange fee is **$1.15/side against MES's $0.35**.
  Same dollar cost, ~5x the rate. Sourced and dated in config/venues.yaml;
  the exchange component rests on a broker's republication because CME's own
  fee finder is interactive, and CME changed its schedule effective
  **2026-04-01, inside this data range**.
- **Capability matrix applied: 35 of 42 features computed.** All 7 cross-venue
  features are 100% NaN — Kraken/Coinbase/Hyperliquid have no April–May data
  because those recorders started later. Absent, not silently zero. Short
  trade-window features are populated (29.0–59.7% nonzero), confirming
  ADR-018's "quiet market, not an absent one".
- **Walk-forward: one clean fold, not three (ADR-024).** 42/14-day windows over
  a 61-day span yield 2 folds, the second truncated 5 days past the data
  (43,340 samples vs 252,596). Windows were not shrunk to manufacture folds.
- **Exclusions run through the single existing invalidity path.** CME has no
  recorder, so closures, no-match windows, roll splices and **observed
  silences** are unioned into the same `[start, end)` list the sampler already
  consumes. The silence class is new and load-bearing: C.7 showed the roll
  exclusion, centred on the splice, covers **0 s** of the ~6.0 h expiry-day
  dead book. Silences are derived from the data, not the calendar. On
  2026-04-06 the detector also finds the daily maintenance halt and
  `merge_windows` unions it with the calendar closure rather than
  double-counting — the fifth instance of the interval rule, with the
  overlapping-pair test it requires.
- **Two OOM kills, one avoided and one not.** `load_samples` concatenated every
  day into one Arrow table and then built a float64 dict — two full copies —
  while loading 18 columns training never reads. Fixed before it fired
  (one file at a time, selected columns, float32, `ts_ns` kept integral since
  1.8e18 exceeds float64's exact-integer range). It still OOM-killed at
  **5.48 GB** on the full 5.4M samples, and the stride in ADR-025 is what
  actually made it fit. **The first fix reduced the peak and I reported it as
  bounded; it was not.** Measuring the reduction is not the same as measuring
  the requirement.
- **A silent-empty bug cost a full overnight cycle.** The vendor venue gate
  walked one directory too far (`.parent.parent` lands on `venue=cme`, whose
  children are `symbol=` not `date=`), producing an empty date set reported as
  "no recorded data" while 6.9 GB sat on disk. It returned success-shaped
  output instead of raising. Regression test added. `main()` also re-extracted
  samples unconditionally where the trades path checks first — a re-run to
  reach training would have silently redone 5 hours of work.
- **Measured, not assumed:** decode+map 165K rec/s (181 MB peak) · ingest ~40K
  rows/s (386 MB, 30.5 B/row) · extraction 10,582 events/s (1,272 MB peak,
  107,377 samples/day, 99.7% valid) · training 1,109,072 samples in ~18 min.
  Ingest reproduced C.4's MBTN6 count exactly (4,275,234).
- **This stage bought no data.** Ledger unchanged at $81.3416 of $120.
- `make lint`, `make typecheck`, `make test` clean. All three recorders alive
  and untouched throughout. Both runs logged to research/experiments.jsonl
  (`99ad7dde`, `464f8937`).

## 2026-08-03 — Stage C.9: spread-to-cost measured across 28 instruments; all fail

**Every instrument with a measurable market fails spread − adverse − cost, by
2.75 to 4.25 bps. The thin tail is the one thing left genuinely open, and the
subscription extension made in this stage will close it for free.**

- **The correction, stated plainly.** After C.8 a claim was made and not
  verified: spread capture is dead everywhere because fees exceed the spread.
  It was checked on **two instruments** (MBT 1.93 bps vs 5.33 bps cost, and ES
  by estimate) and generalised — from two of the *tightest* instruments
  available, which is the worst possible basis. Fees hold roughly constant in
  bps as notional scales; spreads do not. This stage measured 28 instruments.
- **Hyperliquid was subscribed to BTC and ETH only** — 2 of 177 live perps, and
  the two where the ratio is worst. Over 53.13 quoted hours: BTC **0.164 bps**
  (ratio 0.055), ETH **0.545 bps** (ratio 0.182) against a 3.00 bps maker round
  trip. Neither spends measurable time above 3 bps. Spread is **time-weighted**,
  not update-weighted — what a resting quote faced, not how often it changed.
- **Subscription extended to 12 coins** spanning the venue's own liquidity
  ranking (24h notional, metaAndAssetCtxs, 2026-08-03): BTC, ETH, HYPE, SOL,
  PUMP, DOT, LINK, ARB, GMX, MERL, TNSR, NOT — a 110x range of impact spread
  (0.72 to 79.18 bps). Applied by managed systemd restart; all 12 verified
  recording bbo and trades within 40 s, lifecycle boundary logged as a clean
  end/start pair 574 ms apart, other venues undisturbed.
- **CME survey: 16 micro contracts, bbo-1s only, $0.7763 total.** Priced before
  buying. No mbp-10 bought for any new contract.
  **Not one liquid contract has a ratio above 1.0.** Best is M6A micro AUD at
  **0.98** — break-even on fees before adverse selection. Then MNQ 0.91, M6E
  0.86, MGC 0.84, M6B 0.82, MES 0.59, MYM 0.49, M2K 0.43, MBT 0.43, MET 0.09.
  MET is the notional effect in extremis: 0.1 ETH is a **$191** contract, so a
  $1.94 round turn is 102 bps.
- **Three contracts are too inactive to call a market.** SIL shows a ratio of
  3,889 on **69 quote updates in a day**; MHG 65.0 on 1,494. A spread you cannot
  be filled against is not an opportunity. Reported as an open question, not as
  an opportunity and not as a dismissal.
- **Two contracts are a failed measurement, not data.** 2YY and 5YY returned 10
  and 1 usable records with mids of 1.4e9 and 4.6e9 — an unresolved continuous
  symbol. Recorded as failed rather than reported as thin. The micro yield
  contracts (2YY/5YY/10Y/30Y) quote in yield, not price, so bps-of-notional is
  the wrong frame and no ratio is computed for them.
- **Adverse selection, measured with no fill simulation** (signed post-trade
  mid drift, resolving against the last mid at or before each deadline):
  HL BTC +0.063/+0.215/+0.289 bps, HL ETH +0.106/+0.298/+0.384, CME MBT
  +0.657/+0.678/+0.643 at 100 ms / 1 s / 5 s. Positive everywhere; MBT's is ~3x
  the majors' and already flat by 100 ms.
- **spread − adverse − cost:** HL BTC **−3.05**, HL ETH **−2.75**, CME MBT
  **−4.25** bps. For the ten liquid CME contracts without trades data the
  conclusion follows without them: ratio < 1 means the net is negative before
  adverse selection is charged, and adverse selection is positive everywhere.
- **This assumes a fill, which nothing here models.** Queue position decides
  whether the passive order fills at all, so these are an *upper bound* — and
  the upper bound is already negative.
- **Recommendation: do not build Phase C fill simulation against any of these.**
  C.8 needed a model to fail; this needs only subtraction. What stays open is
  the thin tail, and the ten thin perps subscribed here answer it with quotes
  *and* aggressor-signed trades at zero marginal cost. Re-run this census in a
  week.
- **Budget:** $0.7763 spent on the survey; **$82.1179 of $120, $37.8821
  remaining**, cap unchanged. 29 ledger requests.
- `make lint`, `make typecheck`, `make test` clean — **207 tests**, 10 new.
  `tests/test_hyperliquid.py` subscription assertion rederived from config
  instead of a hardcoded 2-coin list, so growing the list no longer breaks it.
  All recorders alive.
