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

## 2026-08-04 — Stage C.9.1: validation venue handling and session marker ordering

**Two defects from a post-incident check. Neither lost data. One would have
aborted every validation run from here on; the other turned out to be already
correct, and the interesting part is why.**

- **Task 1 — validation aborted on `cme` before validating anything.** The CLI
  treated every configured venue as replayable and raised `ValueError: No replay
  support for venue 'cme'`. Venues iterate in sorted order, so `cme` came first
  and took the three healthy venues down with it: three days went unscored
  because of the one venue that is never going to have raw capture.
- **Fixed by declaring the difference, not routing around it.** `VenueConfig`
  now carries `kind`: `recorder` (captured live into `data/raw/`) or `vendor`
  (purchased into `data/vendor/`), defaulting to `recorder` so an undeclared
  venue fails loudly rather than quietly dropping out. New
  `data/validate/scope.py` plans the whole run up front into three outcomes that
  never collapse into each other: **replay**, **skip with a reason**, and
  **`VenueConfigurationError`** (exit 2, distinct from exit 1 "nothing to do").
  A recorder venue with no parser still raises — that one *is* a defect.
- **The two skip reasons are worded to be unmistakable.** Vendor: *"not captured
  live — it has no raw data on any date by design"*. Recorder: *"no recorded
  data for 2099-01-01 (6 other recorded date(s) under data/raw)"*. Skips are
  written into report.md, not only printed: a section listing two venues where
  three were expected has to say what happened to the third.
- **`cme` stays in the venue list.** Named explicitly, `--venue cme --date
  YYYY-MM-DD` now scores stored vendor day files through
  `data.databento.validate` — which until this stage had **no caller anywhere in
  the repository**. A default sweep skips vendor venues rather than streaming
  gigabyte DBN files on every `make validate`; multi-day `range=` files keep
  their own entry point.
- **Task 2 — the reported premise was half right, and the half that was wrong is
  the point.** `derive_downtime_gaps` does **not** trust file order. It has
  sorted by `ts_ns` since the commit that introduced it (`2f94b53`, 2026-08-01
  00:32 PDT), six hours before the first out-of-order pair was written. On the
  actual on-disk sequence it produces a correct **327 ms clean `downtime` gap**.
- **What file order would have produced, measured rather than assumed:** a
  **602 ms `unclean` termination** — a graceful systemd restart reported as a
  crash — with the 327 ms clean gap lost entirely. Kind matters more than
  duration here: `unclean` is the signature of a crash, OOM kill or power loss,
  and one appearing in a report is a reason to go looking.
- **So the sort was load-bearing and undocumented.** Added: the rationale in the
  module docstring (two processes append to one file during every restart —
  unreliable by design, not an anomaly to prevent), an `end`-before-`start`
  tie-break for identical timestamps, and the invariant the prompt asked for —
  `NegativeGapError` on any `GapRecord` whose window runs backwards, enforced on
  the model so no future derivation can reintroduce it.
- **The code it replaces silently dropped inverted pairs.** `if marker.ts_ns >
  pending_end.ts_ns:` would have hidden exactly the corruption worth knowing
  about, and hidden it twice over: `merge_windows` also filters inverted
  windows, so a negative gap vanishes from the coverage union while still being
  counted in its per-kind total, leaving the two to disagree with nothing to
  show why.
- **Task 3 — nothing downstream consumed a bad pairing.** The only runs
  published after the mis-ordered markers were written (2026-08-01 07:28 and
  07:32 UTC) report **3 recorder-downtime gaps totalling 21,919,496 ms, 0
  unclean**. Clock-ordered pairing gives exactly 21,919,496 ms; file-ordered
  would have given 2 downtime + 1 unclean (602 ms), 21,919,770 ms. The published
  figures reconcile to the nanosecond with correct ordering. No day needs
  recomputing, and none was recomputed.
- **Task 4 — 2026-08-03 validated, all three live venues PASS.** Kraken
  16,653,584 msgs (7 feed gaps, 14,593 ms; 16,531,192 CRC32 checksums verified,
  0 failures; coverage 100.00% excl. gaps). Coinbase 3,460,641 msgs (0 gaps;
  3,460,641 sequence numbers checked, 0 gaps; 100.00%). Hyperliquid 1,489,552
  msgs (1 feed gap, 1,142 ms; 32,200 snapshots; 100.00%). Zero crossed and zero
  locked books on every symbol. Zero recorder downtime and zero unclean
  terminations on all three.
- **Correction to the stage premise: the 05:40:40 UTC restart is on 2026-08-04,
  not 08-03.** `1785822040408043821` is `2026-08-04T05:40:40.408Z` — 22:40 PDT
  on Aug 3, which is where the date came from. 2026-08-03 UTC contains no
  session markers at all, so its downtime is legitimately zero. The restart
  pairs correctly as a **574 ms clean `downtime` gap** (`end` 05:40:40.408044 ->
  `start` 05:40:40.982369), verified directly and pinned by the regression test.
- **New finding, not in scope to fix: a 22.6 s host stall at 19:51:25.336Z.**
  All three venues fall silent within **1 ms of each other** and resume 22.5 to
  22.8 s later — one host, not three venues. **Zero logged gaps overlap it on
  any venue**, so the WebSocket connections stayed up and the process simply
  stopped reading its sockets. Invisible in the verdict (22.6 s of 86,400 is
  0.026%, and coverage still rounds to 100.00%), and invisible in the arrival
  histogram, where it is one entry in a max. The **snapshot-cadence check is the
  only thing that caught it** — Hyperliquid reports 1 unexplained stale interval
  of 28,100 ms, which is the stall plus its surrounding 5.4 s cadence. Cause
  unknown; a stall of that length with connections intact points at the host
  (I/O or memory pressure on a 14 GiB machine that was also running C.9
  analysis that afternoon), not at any venue. Recorded for a future stage.
- **Also observed, not a defect:** on a snapshot-stream venue the
  "snapshot compares (mismatch)" column does not mean what it means elsewhere.
  Hyperliquid shows 6,616 of 16,099 (BTC) and 6,884 of 16,099 (ETH) — it is
  comparing consecutive *full* snapshots 5.4 s apart, so a differing top of book
  is the market moving, not a reconstruction error. It is scored against nothing
  and fails nothing; noting it so a future reader does not mistake 41% for a
  problem.
- `make lint`, `make typecheck`, `make test` clean — **219 tests**, 12 new
  (`tests/test_validate_scope.py`, plus three in `tests/test_downtime_gaps.py`
  built from the literal on-disk marker sequence). Both recorder units
  `active running` under `systemctl --user`, all three feeds at age 0 s,
  undisturbed throughout.
- **Vendor dispatch verified against a known answer, not just implemented.**
  `--venue cme --date 2026-07-31` reproduces C.6's recorded verdicts exactly:
  `MES.c.0` **PASS** (14,989,106 events, 0 sequence regressions, 0 out-of-order,
  0 crossed, coverage 100.00%) and `MBT.c.0` **FAIL** (380,358 events, coverage
  **71.49%** vs C.6's 71.494%, 5.99 h of unexplained quiet across 4 windows vs
  C.6's 5.986 h across 4). MBT's failure is the fully-explained expiry-day
  behaviour from C.6 — MBTN6 expired that day, settled against the CF Bitcoin
  Reference Rate at 15:00 UTC, and its book ran dead from 15:18:41Z to the
  21:00Z Friday close — not a new finding. Matching a previously recorded
  number to three decimal places is the check that the new routing scores the
  same file the same way.

## 2026-08-04 — Stage C.10: cointegration pairs trading

**The turnover fix worked and the edge was not there. Break-even costs of
300–550 bps against a 3 bps venue — a margin of 100–180x — and still no
executable pair survives, because the relationships do not persist and the
pairs that look best cannot be shorted anywhere reachable.**

- **Task 1 — free history, survivorship-free by construction.** 3,936 monthly
  files, 295 symbols, 15.0 MB, **nothing purchased**. Sample 2021-08-01 to
  2026-07-31, 1,826 daily bars. Selection rule: symbols with a Binance monthly
  bar file in the sample's **first** month, ranked by **that month's** quote
  volume — 710 USDT candidates, **291 listed at 2021-08**, top 60 taken.
- **20% of the universe died inside the sample.** Twelve of 60: MATIC (2024-09),
  FTM (2025-01), EOS (2025-05), BAKE (2025-09), SRM (2022-11), BTT (2022-01),
  EPS (2022-05), and five more. A universe screened on today's liquidity drops
  one in five of this sample — and drops exactly the relationships that ended.
- **Only Binance can do this.** Its dumps retain delisted directories (FTT,
  LUNA, SRM, BUSD, WAVES all still resolve, verified 2026-08-04). Kraken's
  `AssetPairs` and Coinbase's `products` list only live products, so neither is
  ever used to select a universe; Kraken additionally hard-caps OHLC at **720
  candles**, about two years, and cannot carry the sample at all.
- **A second bias the survivorship fix does not cover: ticker reuse.**
  `LUNAUSDT` has an unbroken run of files and is two different assets — Terra
  collapsed May 2022, Terra 2.0 relaunched on the same ticker. Caught exactly:
  17.46 → 1.08 → 0.00032 → **8.87, a 177,400x jump in one bar**. Excluded
  entirely, not truncated. BTTUSDT (1:1000 redenomination) went too.
- **New venue kind `archive`, in its own `sources` block** (ADR-031). Not under
  `venues`: an archive has no endpoint, no book depth, and above all **no fee
  schedule** — publishing one for Binance would invite modelling a strategy on
  fees no order of ours could pay. `plan_run` lists archives among its skips so
  one that stops being refreshed is visible rather than absent.
- **Task 2 — 1,653 pairs, and 83 of the hits are the null behaving normally.**
  Formation 2021-08→2023-07: **432 raw hits vs 82.7 expected by chance**, 180
  surviving Benjamini-Hochberg. Holdout 2023-08→2026-07: **91 raw vs 77.0
  expected — barely above noise — and zero surviving BH.**
- **Relationships decay.** Of 180 formation survivors, 175 re-testable, **18
  (10.3%) still significant uncorrected, 0 under BH**, against a 5.9% base rate
  for any pair — a lift of **1.74x**. This reproduces the literature's finding
  that cointegrating vectors are time-varying, which is why the hedge ratio is
  re-estimated on a rolling 90-day window rather than fitted once.
- **Tasks 3–4 — cost stopped being the constraint, which is the real news.**
  At 6–9 round trips a year, Hyperliquid's 3 bps costs ~20 bps annually against
  returns in the tens of percent: **98 of 175 pairs profitable gross and the
  same 98 profitable net of HL cost**; 85 still profitable at Kraken's 80 bps.
  Best powered pair C98/XTZ: 40.56% gross, 40.34% net HL, **break-even 553.1
  bps** — 184x the venue's cost. C.8 and C.9 died on cost; C.10 did not.
- **Task 4 — executability is zero, for two independent reasons.** Of the 12
  subscribed Hyperliquid perps, only **5 existed on Binance at 2021-08** (BTC,
  ETH, SOL, DOT, LINK); HYPE and MERL have **never** listed there, and ARB, GMX,
  TNSR, NOT, PUMP came later. Of the ten testable executable pairs, none
  survives — and **BTC/ETH scores p=0.1169**, not cointegrated even uncorrected.
  **The published BTC-ETH result the stage was asked to test does not
  reproduce.**
- **Given a fair test, the executable set still fails.** Re-screened on
  2024-06→2026-07 where 9 of 12 exist: 36 pairs, **1 raw hit against 1.8
  expected by chance**, 0 surviving BH, **23 of 36 lose money gross**, and no
  pair exceeds **9 trades** in 425 out-of-sample bars. The one Johansen
  rejection (ARB/GMX) loses 8.4% a year. BTC/ETH scores p=0.9275 here.
- **Task 5 — the deflation benchmark exceeds the result.** Best powered pair:
  annualised Sharpe 0.98, per-bar 0.0514, against an **expected max per-bar
  Sharpe under the null of 0.1058 across 1,653 trials**. **Deflated Sharpe
  0.026.** Kurtosis 79.5, and the 12-fold walk-forward shows why — **two of
  twelve quarters carry essentially the whole return** (+51.5%, +55.9%), seven
  positive, five negative. Embargo scaling confirmed at day magnitude: 30 bars =
  2,592,000,000,000,000 ns, exact in int64.
- **A look-ahead bug I introduced and caught.** The first run ranked
  BAKEUSDT/EPSUSDT first at **223% annualised from 4 trades** — EPSUSDT died in
  2022-05, inside the formation window. `start` was an offset from the end of
  each pair's own series, so any pair whose overlap was shorter than the holdout
  traded **in-sample on the window it had been selected on**. Fixed to index by
  date (`searchsorted` on the holdout start); the flashiest number in the table
  was the bug. Pinned by regression test.
- **Verdict: the fourth negative, and it fails differently.** C.8 and C.9 died
  because edge per trade was below cost per trade. C.10's turnover fix removed
  cost as the constraint entirely — and the strategy still fails, on persistence
  (0 of 180 survive re-testing) and on access (0 executable pairs). Cointegration
  among liquid crypto assets over 2021–2026, measured without survivorship bias
  and corrected for multiple testing, is not distinguishable from noise out of
  sample.
- `make lint`, `make typecheck`, `make test` clean — **242 tests**, 23 new
  (`tests/test_pairs.py`, `tests/test_archive.py`). statsmodels added to the
  research group for Engle-Granger and Johansen. All recorders alive throughout;
  2026-08-03 still validates PASS on all three venues.
- **Known noise, not a defect:** statsmodels' `coint_johansen` emits
  `ComplexWarning` on some pairs — its eigenvalue solve returns a negligible
  imaginary part which the library discards. Johansen is reported alongside
  Engle-Granger, never alone, and no conclusion here rests on it.

## 2026-08-04 — Stage C.11: funding rate carry

**The first stage that did not produce a clean negative, which makes it the
most dangerous one. The carry is real and paid ~8%/yr net on deployed capital
on the majors — but the yield has decayed ~85% from its 2021 peak and is
running at 1–2% in 2026, so the historical average describes a regime that has
ended.**

- **This is a carry trade, not a machine learning strategy.** No features, no
  labels, no model, no cross-validation — almost none of the Phase B research
  layer applies, and reaching for it here would be theatre. Stated in the
  report and in ADR-033.
- **Task 1 — free funding + basis history, nothing purchased.** Hyperliquid
  funding for all 12 subscribed perps (27,761 hourly rows for BTC, 2023-05-12
  to 2026-08-04), HL perp candles, Binance USD-M funding back to 2020-01 for
  the decay question, Binance spot 1h for the long leg. Two new `archive`
  sources declared per C.9.1; every file carries source, URL, sha256 and
  retrieval date in the C.10 manifest.
- **A data hazard caught before it mattered: the venue changed its own funding
  interval.** Hyperliquid paid **eight-hourly** from launch until 2023-06-08
  and **hourly** after (81 eight-hour steps, then 27,676 one-hour). Any
  annualisation using a fixed intervals-per-year constant is silently wrong
  across that boundary **by a factor of 8**. Everything now divides accumulated
  funding by elapsed time. On BTC the correction is small (14.21% vs 14.50%)
  because the 8h era is 27 of 1,181 days — small **by luck, not by design**.
- **Task 2 — funding characterised, and the general claim is false.** The
  ~11%/yr baseline holds for the majors (BTC 14.21%, ETH 14.33%, LINK 15.59%,
  HYPE 21.60%) and fails badly elsewhere: **MERL −22.38%/yr and TNSR
  −32.41%/yr**. Shorting TNSR would have cost **75% of notional** over 2.3
  years. The thin end of the perp market is where a naive "high funding" screen
  sends you and where the sign flips.
- **Negative runs are the statistic, not the negative fraction.** BTC's longest
  is 8.3 days costing 0.41%; **DOT's longest is 41.5 days** and GMX's worst
  costs 5.11%. A position sized on the average would have been financing a
  six-week loss on DOT.
- **Yield decay is the finding.** Binance BTC by year: 2021 **30.61%** → 2024
  11.92% → 2025 5.13% → **2026 1.94%**. ETH: 37.54% → 12.96% → 4.93% →
  **0.97%**. Hyperliquid says the same internally — BTC first half 20.02% vs
  second half 8.15%; decay slopes −6.31%/yr (BTC), −7.67%/yr (ETH). **Down ~85%
  from peak.** This is a crowded published trade behaving exactly like one.
- **The carry is a bull-market phenomenon.** Correlation of daily funding with
  the trailing 30-day trend is **0.57 / 0.50 / 0.54** (BTC/ETH/SOL). BTC pays
  **5.77 bps/day in uptrends vs 1.87 in downtrends**; SOL pays −0.07 bps/day in
  downtrends. Correlation with realised vol is ~0, so it is direction, not
  volatility. A "delta-neutral" trade earning most of its income when the market
  rises is not as neutral as its name.
- **Task 3 — two structural findings from building the model.** **Equal units
  are already delta-flat**: a 1:1 unit hedge does not drift as price moves, so
  charging delta rebalancing against volatility charges for work the structure
  does not require. **What grows is the margin requirement**, so the real choice
  is bound-the-capital vs bound-the-cost. On BTC a 2% band costs **10.65% of
  notional** in fees over the sample; never resizing needs **5.92× notional in
  capital** (18.55× on SOL). The band is swept, never chosen.
- **Return on deployed capital, per instrument at its best band:** ETH **8.07%**,
  BTC **8.00%**, LINK 7.43%, SOL 5.86%, ARB 5.57%, DOT 3.48%, PUMP 3.26%, NOT
  1.68%, GMX 1.28%, TNSR **−10.45%**. Return on *notional* would have read
  1.6–3.0× higher — that gap is why ADR-035 changed the metric.
- **A modelling error I made and fixed.** The first version held deployed
  capital fixed at entry while crediting funding on a notional that grew with
  price: SOL reported **306% of notional collected and 64%/yr**. Arithmetically
  consistent, economically impossible — that short would have been liquidated
  long before collecting it. Now the margin account is tracked and capital is
  the **peak** requirement over the path.
- **Task 4 — failure modes measured.** Worst BTC negative-funding episode: 5.3
  days, −0.41%; **holding (0.405%) is cheaper than exiting (0.83%)** because a
  round trip pays the 40 bps spot leg twice. Basis: HL premium mean 0.65 bps,
  p99 14.59, worst adverse hourly move **38.2 bps = $38.20 on $10k** — but
  measured against HL's own index, so it **understates** true cross-venue basis.
  Liquidation: **0 breaches up to 5× leverage, 6 at 10×** — and rebalancing is
  itself the protection, since each resize re-establishes the short at the
  current price. Counted without crediting spot gains as perp margin, because
  that collateral is on another venue.
- **Unmodellable risks stated, not omitted:** protocol failure, venue
  insolvency or withdrawal freeze, oracle manipulation, solo-operator failure
  across two venues, and regulatory loss of Hyperliquid access.
- **Verdict.** Against a 4% risk-free rate, **5 of 10 clear it** historically by
  1.6–4.1 points. At 2026 funding levels the trade **does not clear cash at
  all**. A backtest can establish that the carry existed and what it paid; it
  cannot establish whether two legs on two venues survive years without an
  operational failure — and this is the first strategy whose verdict turns on
  the part a backtest measures worst.
- `make lint`, `make typecheck`, `make test` clean — **256 tests**, 14 new
  (`tests/test_carry.py`). All recorders alive throughout.

## 2026-08-04 — Stage C.12: hypothesis register

**Consolidation only. No new analysis, no new experiments, no new data. Every
figure in the register is transcribed from a report.md section and was checked
against it rather than recalled.**

- **Created `HYPOTHESES.md` at the repository root** — one entry per tested
  hypothesis, ordered by close date, each carrying the measured number that
  decided it, the sample and its limitations, the report.md section where the
  working lives, and what would reopen it.
- **The register's organising distinction is between two kinds of closure**,
  because confusing them is the expensive mistake a future session would make:
  - **cost-bound** — a real signal smaller than the cost of capturing it, which
    reopens at a materially lower fee tier and where a better model could matter
    *if* costs fell (H1, H3);
  - **signal-absent** — nothing there to capture, which **does not reopen on a
    better model, a better feature set, or lower fees** (H2, H4).
- **Five closed:** H1 directional prediction on crypto spot (3.31 bps capture vs
  80 bps cost, AUC 0.596 — signal real, arithmetic fails by 23×); H2 transfer to
  CME (AUC 0.501, 0.22 bps vs 5.33 — cost solved, signal gone); H3 spread
  capture (spread − adverse − cost negative on all 28 measurable instruments,
  best ratio 0.98); H4 cointegration (0 of 180 persist, BTC/ETH p=0.1169,
  deflated Sharpe 0.026, zero executable); H5 funding carry (8.07%/8.00% net on
  capital historically, decayed ~85% to 1.94% in 2026).
- **Two in flight, both awaiting data only, neither needing new access or
  capital:** H6 thin-perp spread capture (closes in ~a week at zero cost on the
  10 perps subscribed 2026-08-03) and H7 cross-venue divergence (needs months of
  simultaneous three-venue overlap; recorders together only since 2026-08-01).
- **Cross-cutting section records what would be lost if filed under one
  hypothesis:** the recurring cost-exceeds-edge diagnosis across H1–H3 and the
  fact that **H4 refuted it as a general explanation** — removing cost entirely
  (break-even 300–550 bps vs a 3 bps venue) revealed no edge underneath; the
  measured venue cost landscape with its per-contract CME notional effect
  (0.41 bps MNQ to 101.76 bps MET on the same $2 ticket); and the four
  engineering lessons that generalise, including that **the most dangerous
  defects are success-shaped** — C.10's look-ahead produced the highest-ranked
  result in the study.
- **Linked, not duplicated.** `CLAUDE.md` §"Read these first" now points at
  `HYPOTHESES.md` with one line on when to consult it. No register content was
  copied into CLAUDE.md or progress.md — one authoritative location.
- **Closing summary written without spin in either direction.** Five tests, no
  deployable strategy; two produced measurable effects correctly judged
  insufficient; the infrastructure is genuinely good and the strategy pipeline
  has genuinely produced nothing deployable, and both are true at once. Five
  closures is evidence about five hypotheses, not about the sixth.
- `make lint`, `make typecheck`, `make test` clean — **256 tests**, unchanged
  (this stage adds no code). All three recorders alive, undisturbed.

## 2026-08-05 — Stage C.14: pre-registered bars (written BEFORE any result)

**This entry is the pre-registration commit required by the C.14 prompt: "A bar
chosen after seeing the numbers is not a bar." Nothing in C.14 has been
computed at the time of writing.** What I have read is the *existing* Phase B
and C.8 output already in report.md — the numbers this stage is diagnosing, not
the numbers it will produce. Stage C.13 is in flight concurrently (its universe
download is still running), so its results section will land in this log after
this pre-registration and before C.14's results. That ordering is chronological
and deliberate.

The figures being diagnosed, restated so the bars below are legible:

| run | horizon | AUC | gross capture | round-trip cost | net EV |
|---|---|---|---|---|---|
| Kraken BTC/USD, 2026-07-31 | 100 ms | **0.941** | **~0.03 bps** | 80.00 | −79.97 |
| Coinbase BTC-USD, 2026-07-31 | 100 ms | 0.886 | ~0.01 bps | 80.00 | −80.00 |
| Coinbase BTC-USD, 2026-07-31 | 900 s | 0.596 | **3.31 bps** | 80.00 | −76.69 |
| CME MBT, 53 days | 100 ms | 0.664 | +0.005 bps | 5.33 | −5.32 |
| CME MBT, 53 days | 900 s | **0.501** | +0.215 bps | 5.33 | −5.11 |

### Task 1 — confidence versus magnitude

Confidence is `|p − 0.5|`. Magnitude is realised `|move|` in bps over the
horizon. Correlation is **Spearman**, on ranks, because the magnitude
distribution is heavy-tailed and a Pearson coefficient would report the tail
rather than the relationship.

- **CONFIRMS CLOSURE** — `|rho| < 0.05` at every horizon **and** gross capture
  in the top-confidence decile `< 2x` the all-sample gross capture at the same
  horizon. Reported as: the model calls the sign of moves too small to pay, and
  AUC 0.941 is magnitude-blind rather than informative.
- **FILTER EXISTS (weak)** — `rho >= 0.10` at one or more horizons **and**
  top-decile gross capture `>= 2x` all-sample at that horizon.
- **FILTER IS ECONOMIC (strong)** — top-decile gross capture `>= 80.0 bps` on
  Kraken/Coinbase spot, i.e. net EV at maker `>= 0`. This is the only outcome
  that would reopen H1 on evidence rather than on cost.
- Anything between weak and confirms-closure is reported as **inconclusive**,
  named as such, not rounded toward either.
- **Calibration** — pass is `|mean predicted − mean realised| <= 0.02` in every
  decile bin of predicted probability, plus a reported Brier score. Failing
  calibration while passing AUC is itself a finding: rank-ordered but not
  accurate.

### Task 2 — sample stability

Per-day, per-venue, per-horizon AUC across every validated day.

- **STABLE** — `max(AUC) − min(AUC) <= 0.05` at each horizon, **and** the sign
  of gross capture at the best horizon is the same on every day.
- **MATERIALLY UNSTABLE** — range `> 0.10` at any horizon, **or** any day
  flipping the sign of gross capture at the best horizon.
- Between 0.05 and 0.10 is reported as **mildly unstable** with the range given.
- Per-day tables are reported even where pooled figures exist. A pooled number
  that hides a range is not permitted to stand alone.

### Task 3 — cross-venue feature delta

Same pipeline, same days, same folds, cross-venue features on versus off.

- **MATERIAL** — `dAUC >= +0.010` at half or more of the horizons, **or**
  `dgross capture >= +0.50 bps` at the best horizon.
- **IMMATERIAL** — `dAUC < +0.005` at every horizon.
- Between is **marginal**, reported with the deltas.
- Availability is read from the capability matrix per venue and per contract.
  Every skip is reported with its reason; a feature that is 100% NaN is
  reported as absent, never as zero.

### Task 4 — deep learning, bar stated before training

Baseline is the existing LightGBM under identical purged K-fold and embargo, on
the identical expanded sample and feature set. Two architectures only: an MLP
and one sequential model. No hyperparameter search beyond what is needed to
train stably.

**Stated horizon: 900 s** (where H1's best gross capture sits and where H2's one
apparent positive appeared). Secondary reporting at 1000 ms.

To pass, a deep model must clear **both** at 900 s, out of sample:

- **AUC** `>= baseline + 0.020` absolute, and
- **gross capture** `>= baseline + 1.00 bps`.

**Both are required. An improvement on AUC without gross capture is a FAILURE**,
and is the specific outcome this stage expects given Task 1's premise that
classification metrics are magnitude-blind.

- Any improvement that fails the leakage suite — including the planted-future-
  value test and prefix invariance — **is treated as a leak, not a discovery**,
  and is reported as a leak regardless of its size.
- Clearing this bar settles that **capacity** was the constraint on H2. It does
  **not** reopen H1, which is cost-bound: +1.00 bps on a 3.31 bps capture
  against 80 bps of fees changes nothing economic, and no C.14 outcome can
  change that. Said now so it cannot be quietly forgotten later.

### What no result in C.14 is permitted to do

Reopen a closed hypothesis on a metric other than the one that closed it. H1
closed on **cost** and reopens only below ~3 bps round trip. H2 closed on
**absent signal** and reopens only on measurable AUC — which Task 4 is the test
of. A better AUC on H1's data does not reopen H1, and a better cost on H2's
venue does not reopen H2.

## 2026-08-05 — Stage C.13: cross-sectional funding carry

**Closed as H8. Funding income is real and large; the price term cancels it
almost exactly. Net +0.11%/yr on capital against a 4% risk-free rate.**

- **Task 1 — universe, survivorship-free by construction.** Hyperliquid
  addresses perps by their **index in the `meta` array**, so a delisted asset
  cannot be removed without renumbering every asset after it — it is flagged in
  place and kept, and the funding and candle endpoints keep serving its full
  history. **232 considered, 231 usable, 55 delisted, 55 dying inside the
  sample**, 4,411,046 funding rows, 1,182 days, zero fetch failures. FTT is
  still addressable with candles ending 2026-05-25. Cross-section grew **21 →
  190** instruments; membership is per day, from the venue's own record.
- **A C.11 constraint turned out to be false at a different resolution.** C.11
  reconstructed perp prices as `spot × (1 + premium)` because the candle
  endpoint "cannot cover the sample" — true at hourly (5,000 bars = 208 days),
  **false at daily** (5,000 bars = 13.7 years). Both legs are now priced from
  Hyperliquid's own book in one request per coin, and HYPE and MERL — which
  C.11 could not model at all — are priced here.
- **Task 2 — the gate. Dispersion has decayed, and the composition control is
  what shows it.** All instruments: decile spread 380.58% (2023) → 156.32% →
  164.52% → 167.54%, which reads as a 57% fall and then a plateau. **Fixed
  cohort (38 names live at 2023-08-10): 241.50% → 163.61% → 55.80% → 53.45%, a
  77% fall with no plateau.** The apparent flatness is the venue listing wilder
  coins, not the spread persisting — two measures of the same market differ by
  **3×** on composition alone. IQR falls faster than stdev (−68% vs −39%), so
  what remains has retreated into a few extreme names.
- **Task 3/4 — the three terms, kept apart (ADR-036).** Funding **+43.68%**,
  price **−42.91%**, cost −0.66%, **net +0.11%** on deployed capital. The
  funding income is real; the hedge it is wrapped in destroys it.
- **This is not a carry trade, and the numbers say so directly.** Price daily
  vol **1.81%** against funding daily vol **0.166%** — **10.9× wider**.
  Long/short basket price correlation **−0.718**. Beta to BTC −0.157, R² 0.044,
  so dollar neutrality did buy market neutrality — and nothing against the
  cross-section. **Negative funding is compensation for holding assets that
  keep falling**, not free income.
- **Task 5 — capital and drawdown.** Deployed capital **1.18× gross notional**,
  materially better than C.11's 1.6–3.0× because both legs are margined on one
  venue. Max drawdown **−75.85%**; worst 30 days −41.49%, worst 90 days
  −48.05%; 20 forced exits on delisting. A −75.85% drawdown for +0.11% a year
  is not a trade-off worth taking.
- **Cost is nearly binding, unlike H4.** Break-even **1.76 bps a side against
  1.5 modelled** at **51.7× annual turnover**. H4 had 300–550 bps against 3 —
  a 100–180× margin. Here the margin is 17%, and a fee change or a taker fill
  closes it.
- **The parameter surface is noise.** Net swings from −10.15% to +51.61% across
  the sweep with no stable optimum (3-day +21.51%, 7-day +0.11%, 14-day
  −8.62%). The best cell — 3 names a side, +51.61% — carries a **−124.43%
  drawdown**, i.e. equity fell further than the capital behind it. A result
  that moves 60 points on the choice of rebalance interval is fitted.
- **Regimes absent:** the venue launched after the 2022 drawdown, so **no bear
  market is inside this history**, and a dollar-neutral book's price term is
  exactly what an untested regime moves.
- **Two defects fixed rather than worked around.** The archive page key omitted
  `interval`, so a `1d` candle fetch would have **overwritten an archived `1h`
  page** (ADR-037); and a held instrument with a missing print was
  indistinguishable from a delisting, now counted separately (measured: 0 gaps,
  20 real delistings).
- **Nothing purchased.** All 232 perps from the free unauthenticated info
  endpoint, every page with source, URL, sha256 and retrieval date.
- ADR-036 (dollar-neutral ≠ delta-neutral; terms reported separately) and
  ADR-037 (a cache key names every varying request parameter) appended.
- `make lint`, `make typecheck`, `make test` clean — **290 tests**, 22 new
  (`tests/test_cross.py`). All three recorders alive throughout.

## 2026-08-05 — Stage C.14: diagnosing the directional prediction failure

**Diagnostic, not a rescue. Both closures confirmed with better explanations,
and H1 is now on firmer ground than the number that originally closed it. All
bars were committed in a2d7466 BEFORE any figure was computed.**

- **Scope actually run, stated rather than omitted.** Six validated days
  (2026-07-30 → 2026-08-04) on Kraken BTC/USD and Coinbase BTC-USD at **stride
  3** (ADR-025 — coarsens the bar, does not bias which moments are sampled).
  **The ETH pair was not run**: the full four-symbol stride-1 sweep is ~5 hours
  of LightGBM fits.
- **Task 1 — the priority. AUC is magnitude-blind, and the correlation is not
  zero but strongly NEGATIVE.** Spearman confidence-vs-|move| = **−0.3175**
  (Kraken) and **−0.3665** (Coinbase) at 100 ms, staying negative out to 5 s.
  **The model is surest exactly where there is least to win**, at precisely the
  horizons where AUC looks best (Kraken 0.9432 @100 ms with 0.0291 bps capture).
  This is a **third world the pre-registration did not anticipate** — it imagined
  rho≈0 or rho>0 — and it supports the closure more firmly than the
  uncorrelated case would have.
- **A correction to my own instrument, recorded because it matters.** The
  registered text gates the filter branch on `rho >= 0.10` SIGNED, meaning
  "concentrates in LARGER moves"; the code tested `max|rho|`, which a large
  negative value would satisfy while asserting the opposite. **Fixed the code to
  match the registered text, not the reverse** (5430eba), with a regression
  test. Outcome by the bar as written: **INCONCLUSIVE** on both venues. The bar
  was mis-specified for the world that occurred; the finding is not ambiguous.
- **No usable filter.** Top-confidence deciles capture 2–24× the all-sample
  mean, but via **accuracy, not magnitude**. The best decile in the study
  captures **5.00 bps against an 80 bps round trip** — the economic bar missed
  by **16×**. Calibration is poor: worst gap **0.6086** (Kraken @300 s), mean
  Brier 0.163. Rank-ordered, not accurate.
- **Task 2 — MATERIALLY UNSTABLE, and H1's headline number does not reproduce.**
  Two degraded days named rather than averaged in: 07-30 has 56 samples, and
  **08-01 is missing hours 02–06 on both venues** — a host outage with no
  feed-gap record, since the recorder was down rather than disconnected — 1,204
  valid samples against ~30,000 on neighbours. On the **four full days**: short
  horizons are remarkably stable (Kraken AUC @100 ms varies **0.0044**), long
  horizons do not reproduce at all. **Coinbase 900 s gross capture ranges
  −2.4378 to +3.0497 bps.** Phase B's **3.31 bps at 900 s was 2026-07-31**,
  the +3.05 day. **The number that defined H1 is a single-day draw from a
  distribution centred near zero** — which closes H1 harder, not softer.
- **Task 3 — cross-venue features are IMMATERIAL where they can be computed.**
  Coverage 67–100% (vs 100% NaN in C.8). Max **ΔAUC +0.0044** (Kraken),
  **+0.0037** (Coinbase); max Δcapture +0.04 bps. The best-scoring feature class
  in Phase B importance is worth four ten-thousandths of AUC. **Feature
  importance measured what the model leaned on, not what it gained.** This
  closes the loose end on H2: C.8's failure was not caused by their absence.
- **Task 4 — deep learning FAILS the pre-registered bar, and by more than the
  margin.** Bar: at 900 s, AUC ≥ baseline +0.020 **AND** capture ≥ baseline
  +1.00 bps, both required. Baseline LightGBM AUC 0.5301 / +0.0843 bps. **MLP
  0.4949 / −0.2894. GRU 0.4908 / −0.3018.** Both deep models are *worse than
  the tree on both metrics at both horizons* — at 900 s both post AUC under
  0.50 and negative capture. No search; 2-layer MLP and 1-layer GRU over 16
  bars, 64 hidden, 6 epochs.
- **The leakage suite passed, and the canary proves that means something.**
  window causality 0 offenders; **planted-future canary AUC 0.9714** (≥0.90);
  label-shift control **0.5268** (≤0.55). The first run's canary could not fire
  at production training settings — it would have certified the path while
  blind — so probes now train harder than the models they police (ADR-040).
- **Verdict.** H1 stays closed as cost-bound, with the mechanism now named and
  its headline number withdrawn as a single-day artefact. H2 stays closed as
  signal-absent, with both escape routes — the missing feature class and
  insufficient capacity — measured and eliminated.
- **What this did NOT establish:** six days is not six regimes; the ETH pair was
  not run; CME was not re-run, because Task 3 could not have rescued it and
  Task 4 was tested where signal is strongest rather than weakest.
- ADR-039 (classification metrics ship beside a capture figure) and ADR-040 (a
  leakage probe must be shown capable of firing) appended. `.venv-dl` holds
  CPU-only torch so the recorders' `.venv` is never mutated (ADR-038).
- `make lint`, `make typecheck`, `make test` clean. All three recorders alive
  throughout; the 08-01 outage predates this stage and was not caused by it.

## 2026-08-05 — Stage C.16: pre-registered bars (written BEFORE any result)

**Nothing in C.16 has been computed at the time of writing. What has been read
is C.10's existing output — its universe cache, its exclusion machinery, its
deflated-Sharpe estimator — because reuse is the instruction. Expect this to
fail: momentum is among the most published anomalies in finance, crypto results
have been poor since 2021, and the value here is closing a family cheaply.**

### The strategy, fixed before running

Time-series momentum, classic form: at each rebalance, each live asset is
scored by its own trailing L-day return; **long if positive, short if
negative**, equal weight 1/N of gross, gross notional 1.0. Net exposure floats
with the fraction of assets trending up — that float is exactly why the beta
control exists. No skip window, no volatility targeting, no cross-sectional
ranking: each added refinement is a free parameter this registration refuses.

### The grid, registered in full

Lookbacks **{14, 30, 90, 180} days** × holding periods **{7, 30, 90} days** =
**12 specifications**, all reported, none dropped. **Primary specification:
lookback 90, hold 30** — the closest small-sample analogue of the literature's
12-month/1-month convention, named now so no cell can be promoted after the
fact. The deflated Sharpe uses C.10's estimator (`research.pairs.validation`,
Bailey & López de Prado) with **n_trials = 12** and the cross-specification
Sharpe dispersion, computed on **net-of-3bps** daily returns.

### Bars

All Sharpes are excess of a **4%/yr risk-free rate**, strategy and BTC alike,
annualised √365. Benchmark window is identical to the strategy's scored window.

- **PASS** — all four, on the primary spec: (1) net-of-3bps Sharpe **≥
  buy-and-hold BTC Sharpe** on the identical window; (2) deflated Sharpe
  probability **≥ 0.95**; (3) alpha vs BTC (daily OLS, annualised) **> 0 with
  t ≥ 2**; (4) consistency: **≥ 8 of 12** specs post positive net-of-3bps
  Sharpe. An anomaly at one lookback only is a fitting artifact regardless of
  its own numbers.
- **WEAK** — beats BTC risk-adjusted with deflated Sharpe in (0.5, 0.95);
  reported as suggestive, not as a pass, and closes the hypothesis anyway.
- **BETA IN DISGUISE** — beats zero but not BTC risk-adjusted, or alpha ≤ 0
  with beta ≥ 0.5. Reported in exactly those words.
- **FAIL** — everything else. The prompt's literal criterion — "beats
  buy-and-hold BTC on risk-adjusted terms with a deflated Sharpe above zero"
  (probability > 0.5) — is reported alongside whichever verdict lands.

### Controls and costs, fixed now

- Beta/alpha vs BTC from daily OLS on the scored window; up/down split by the
  sign of BTC's trailing 30-day return (the C.11 convention).
- Universe is **C.10's cached construction reused verbatim** — top 60 by
  2021-08 quote volume from 291 listed, spliced series excluded by the same
  detector. Rebuilding from today's listings would reintroduce the bias C.10
  removed, so a missing cache is an error, never a rebuild.
- Costs: 1.5 bps/side (Hyperliquid maker) and 40 bps/side (Kraken spot,
  pessimistic bound; longs only there, and only BTC/ETH are configured).
  Break-even cost per spec = gross P&L / notional traded, per side, as C.10
  ranked. Executable subset = universe members with a live Hyperliquid perp
  today; the statistical result and the executable one are reported separately.

## 2026-08-06 — Stage C.16: time-series momentum on the daily archive

**Closed as H9: FAIL against the pre-registered bars (commit 88b69d8). The
seventh straight closure, bought for zero new data.**

- **Task 1 — universe reused, not rebuilt.** C.10's cache loaded verbatim: 60
  members, 58 in matrix, **identical exclusions reproduced** (LUNAUSDT splice,
  BTTUSDT 170 < 200 obs), **12 deaths in-sample**, each a charged forced exit.
  Universe 60 → 48 live over 2021-08 → 2026-07. A missing cache is an error,
  never a rebuild — momentum shorts past losers, and dead coins are past
  losers, so survivorship bias flatters exactly this strategy.
- **Task 2 — the grid, whole.** 12 registered specs, all reported. Consistency
  **7/12 positive net Sharpe, median 0.167**, sign flipping with both
  parameters. The three specs beating BTC with DSR > 0.5 (L14/H7, L30/H7,
  L90/H7) sit **all at the 7-day hold** — the registered artifact pattern. Best
  cell L30/H7 net Sharpe 0.647 → **DSR 0.732** after 12 trials. Primary
  L90/H30: net 0.302 vs BTC 0.183, **DSR 0.446, alpha t 1.01**.
- **Task 3 — the control caught the opposite disguise.** Expected long-beta;
  measured **negative beta in every cell** (−0.03..−0.43), mean net exposure
  **−0.275**, returns **+56.9%/yr in down-trends vs −14.7% in up**. The book is
  a short-alt-decline position whose income requires an alt bear market. Not
  beta in disguise — anti-beta, and still insignificant.
- **Task 4 — cost irrelevant, as predicted.** 1.9–19 round trips/yr;
  break-even **66–265 bps/side** vs 1.5 modelled. The H4 pattern: cost removed,
  no significant edge underneath. **Executable subset: 27 of 58** have a live
  Hyperliquid perp; primary on them collapses to **Sharpe 0.013** — the effect
  lives in the untradeable tail. Kraken adds nothing (BTC/ETH spot, no shorts).
- **Verdict, stated plainly:** no specification beats buy-and-hold BTC
  risk-adjusted with deflated Sharpe ≥ 0.95; the literal-criterion trio
  deflates to noise and cannot be executed. H9 reopens only on ≥ half the grid
  clearing DSR ≥ 0.95 vs BTC **on the executable subset** with a full bear
  regime in sample — never on fees.
- ADR-041 (grids registered whole; benchmark is the dominant beta, not zero).
- `make lint`, `make typecheck`, `make test` clean — **300 tests**, 10 new. All
  three recorders alive throughout; nothing bought.

## 2026-08-06 — Stage C.15: liquidation aftermath — the data does not exist

**Closed as H10 at Task 1, per the stage's own stopping rule. Zero identifiable
liquidations in the recorded data; no proxy permitted or used.**

- **Checked bytes, not documentation** (the C.1 discipline). Full recorded
  week swept: **2,639,510 trade fills, 116 hour files, 2026-08-01 → 08-06, 12
  instruments.**
- **Four facts, each independently fatal:** (1) every fill shares ONE key-set —
  `(coin, hash, px, side, sz, tid, time, users)` — no liquidation field; (2)
  zero occurrences of any `liquidat` string in ANY channel all week; (3) the
  one anomalous value, all-zeros hash at **18.0%** of fills, ground-truths via
  `userFillsByTime` to **TWAP fills** (`twapId`, `dir='Close Short'`, no
  `liquidation` key) — prevalence alone had already ruled out liquidations; (4)
  no public global history: three plausible info-endpoint types → HTTP 422, and
  the venue's per-user `liquidation` label requires already knowing the
  liquidated address — the enumeration query the public API does not offer.
- **Sample size stated before any conclusion: zero identifiable events.** Not
  "low hundreds" — the events are presumably in the data and carry no mark.
- **Task 2's bar was never registered** because Task 2 was never reachable;
  registering a bar for an impossible comparison would be ceremony. The full
  matched-control design is pre-specified in H10's reopening condition instead:
  ≥ **300 labeled liquidations**, size/instrument/time-of-day matching, mid
  moves at 1/10/60/300 s, 95% CI, economics vs spread-at-event + 3 bps.
- **A third closure kind enters the register:** unidentifiable-in-available-
  data, distinct from cost-bound and signal-absent. The reversion may exist;
  nothing reachable can measure it, and large-trade proxies would erase the
  mechanical/informed distinction that IS the hypothesis.
- Seven single-shot probes to the free info endpoint; nothing bought, no new
  code, no new tests needed (the stage produced a finding, not a pipeline).
- `make lint`, `make typecheck`, `make test` clean — 301 tests unchanged. All
  three recorders alive and writing at the current second throughout.

## 2026-08-06 — Stage C.17: pre-registered bars (written BEFORE touching any data)

**Nothing in C.17 has been probed, fetched, or computed at the time of writing.
This registration is the stage's first commit, per its own Task 1.**

**The end condition, agreed in advance and binding: if this stage fails its
registered bars, the alpha search of this project ends by decision.** That
sentence is recorded here, before any result exists, so the conclusion is a
choice made ahead of the evidence rather than a reaction to it.

### Candidate feature classes (Task 2 may drop, never add)

(A) **stablecoin flows** — net supply changes and flow proxies; (B) **exchange
netflows** — genuine flow data only, dropped C.15-style if no free source at
usable history/granularity exists, never proxied; (C) **funding-regime state**
— level, trailing percentile, 30-day slope, from the C.11 archive on disk;
(D) **basis state** — trailing Hyperliquid perp premium, from the same archive;
(E) **combined** — all surviving classes together, included only if ≥ 2
survive.

### The grid, fixed now

Surviving classes (+ E) × horizons **{1, 2, 4, 8} weeks** × variants
**{long-only, long-short}**, **weekly rebalance**, universe **BTC and ETH**
(extendable only where a class's data natively covers more; none is expected
to). **n_trials for deflation = the full registered cell count** — every cell
computed counts, and no cell may be dropped from the denominator.

Model, fixed to kill the search dimension: per cell, **ridge regression
(λ = 1.0, no search)** of the h-week forward return on the class's features,
**walk-forward expanding window** with minimum 52 training weeks, purged, with
**embargo ≥ the cell's horizon**. Position = sign of the current prediction,
equal weight across assets; long-only clips negatives to zero (in cash).
No threshold search, no feature selection, no second model.

### Publication-lag discipline, registered per source

A metric dated day T is not knowable during day T. `usable_at = metric_date +
lag`; a decision at the close of week-end t may use only features with
`usable_at ≤ t`. Registered lags: **unknown-lag daily sources +1 day beyond
the metric date** (the conservative default); Coin Metrics community **+1 day**;
DefiLlama stablecoin supplies **+1 day**; funding and basis from this project's
own archive **+0 days** (exchange-published at interval end). Revision
behaviour recorded per source in the report. The planted-future canary and
prefix-invariance probes run against this pipeline at daily cadence, and any
improvement failing them is a leak, not a discovery.

### The six bars — ALL required for PASS, anything short is FAIL

1. **Net Sharpe at Hyperliquid cost ≥ buy-and-hold BTC** on the identical
   scored window (Sharpes excess of 4%/yr, both sides, √52 annualisation on
   weekly returns).
2. **Alpha vs BTC > 0 with t ≥ 2** (weekly OLS).
3. **Deflated Sharpe ≥ 0.95** over the full registered trial count, C.10's
   estimator, computed on net-of-HL-cost returns.
4. **Net annualised return > 4.5%** — the cash-and-staking floor.
5. **Present in the executable subset**: the winning cell must execute as
   specced — long-only as Kraken/Coinbase spot, long-short shorts on
   Hyperliquid — with no leg on an unreachable venue.
6. **Consistency: positive net Sharpe in ≥ 2/3 of the winning class's
   registered cells.**

### Fitting-artifact patterns, named in advance (the C.16 lesson)

An effect at **only one horizon**; an effect in **only one variant**; a
long-only effect with **beta ≥ 0.5** in a net-rising sample (that is beta, and
will be named as beta); an effect earning in **only one trend direction**
(reported plainly, whichever direction); the **combined class passing while
every component fails** (that is the grid finding a lucky rotation, not a
signal).

### Costs, registered

Hyperliquid legs 1.5 bps/side (venues.yaml, verified 2026-08-01). Spot legs
reported at **both 40 bps/side** (venues.yaml base tier, the pessimistic bound)
**and 25 bps/side** (the commonly cited current base maker tier the audit
flagged as ~2× apart) — the operator's actual account tier cannot be read from
here by design (no account API in Stage 1), so reconciliation is recorded as an
operator action and both columns ship. At weekly rebalance the cost column
should be nearly irrelevant; if it is not, turnover exceeds design and that is
itself reportable.

## 2026-08-06 — Stage C.17: the final research door — FAIL, and the search ends by decision

**0 of 40 registered cells pass the six bars (370ba41). Under the end condition
agreed before any data was touched, the alpha search of this project concluded
by decision on 2026-08-06.**

- **Task 2 — audit, C.15 style.** Coin Metrics community: genuine
  `FlowInEx*/FlowOutEx*/SplyEx*` exist free for BTC/ETH to genesis — class B
  survives — **but the snapshot ends 2026-05-23: a measured 75-day staleness**,
  and the registered measured-beats-documented rule sent it into the grid at
  **+75 days**. DefiLlama stablecoins: daily 2017-11→today, +1d. CryptoQuant:
  401 even free-tier. Blockchain.com: no flow series. CoinGecko: not needed.
  No exchange publishes flows free. Both new sources declared in venues.yaml
  (kind archive), every retrieval a dated immutable snapshot with sha256.
- **Task 3 — lag discipline central.** `usable_at = metric_date + lag`; lags
  A +1d, B +75d, C 0d, D 0d, recorded per feature. Planted-future canary and
  prefix-invariance green at weekly cadence (`tests/test_medium.py`, 10 tests).
- **Tasks 4–6 — the grid in full.** 40/40 cells scored, weekly 2020-08 →
  2026-07, ridge λ=1 walk-forward, purge+embargo ≥ horizon, n_trials=40.
  **Best DSR 0.499 vs 0.95; best alpha t 1.35 vs 2.** Class A negative 8/8
  under honest lags. B and C: the pre-named beta artifact — LO beta 0.43–0.56,
  alpha t ≤ 0.95, LS collapses. **D (basis): Sharpe to 1.62 on 45–59 weeks of
  pure bull-compression where BTC's own Sharpe was 1.16–2.06** — beta to 0.96,
  one trend direction, three pre-named artifacts at once. E diluted D. Costs
  decided nothing: BE 22–1,059 bps/side vs 1.5; turnover 1.5–16.8 RT/yr —
  the one prediction that held. Two cells hit 4/6, failing exactly the two
  evidence bars.
- **Task 7 — the consequence, executed as written.** Register updated: **H11
  closed (FAIL)** with data-threshold reopening (free flow source ≤2d lag ≥3y
  history, or basis at DSR ≥0.95 / t ≥2 over ≥156 weeks incl. a bear); **H7
  closed by decision**, design preserved; header and closing summary record
  the search's end, dated, with **the census (H6) as the sole remaining open
  item** and the infrastructure as the durable output.
- ADR-042 (publication lag: measured beats documented; living snapshots dated)
  and ADR-043 (a terminal stage binds its consequence in advance).
- **Kraken tier note shipped as registered:** LO cells carry both 25 and 40
  bps/side columns; actual tier reconciliation is an operator action (no
  account API in Stage 1 by design). Changed no verdict.
- Nothing purchased. `make lint`, `make typecheck`, `make test` clean — **311
  tests**, 10 new. All three recorders alive and writing throughout.

## 2026-08-06 — Stage C.18: thin-perp census bars, registered before the data exists

**This registration is the stage's first commit, written before any C.18 code.
The scored window has not yet closed; the ten thin instruments have not been
read and stay untouched until the census runs. The 2026-08-10 answer will be
read against these bars, which predate it — the C.16/C.17 discipline applied
to the sole remaining open register entry, H6.**

### Scored window

**2026-08-04T00:00Z → 2026-08-11T00:00Z**, validated coverage only. The window
is never extended to chase significance; "not significant in this window" is an
outcome, not a reason for a longer window.

### Per-instrument economics bar

**Time-weighted captured spread at trade-time spread state, minus the signed
adverse mid move after aggressor trades at 1 s, 5 s, and 60 s, minus 3.0 bps
round trip** (Hyperliquid base-tier maker, `config/venues.yaml`, verified
2026-08-01) — with the **95% confidence interval lower bound above zero at the
worst of the three horizons**. An instrument passes on its worst horizon or
not at all.

### Multiplicity, sample floor, robustness, capacity

- **Benjamini–Hochberg across the ten thin instruments at q = 0.10.** Expected
  false positives ≤ 0.1 × (number of discoveries); at the maximum ten
  discoveries that is **one expected false positive**, stated now so a single
  survivor is read with that number beside it.
- **Sample floor: ≥ 300 aggressor trades** per instrument in the window for
  the adverse estimate. Below the floor the instrument is declared **too thin
  by prior declaration** — never stretched, never pooled.
- **Robustness: the effect must hold in both halves of the window
  independently** (each half's point estimate positive at the worst horizon).
  Thin-perp income is episodic; one spike is not an edge.
- **Capacity tier for any survivor: ≥ 150 trades/day AND ≥ 100,000 USD median
  daily volume** to count as tradeable capacity. Otherwise it lands in the
  **positive-but-rare** bucket, whatever its per-trade economics.

**The whole measure is an upper bound**, stated plainly: every quote is
credited with a fill it has not earned. Queue position, fill probability and
the adverse conditioning of *which* quotes fill are all unmodelled here and
all point the same direction — down.

### Outcome-to-action map, fixed now

| outcome | action |
|---|---|
| all ten instruments fail | **H6 closes**; the register's closing summary updates to **zero open items** |
| survivors below the capacity tier | report the fill-frequency arithmetic and **stop** |
| survivors within noise of zero | **extend recording 30 days and re-run under these same bars** — no building |
| survivors clearing everything | the result becomes the **input to a D.1 fill-simulation decision, not a strategy** |

### Machinery rule for this stage

**Compute nothing from the thin-tail instruments.** The census pipeline is
validated exclusively on BTC and ETH — whose answer C.9 already closed — by
reproducing C.9's net figures (**BTC −3.05, ETH −2.75 bps**) on C.9's own
window (2026-08-01 → 08-03) to within **0.5 bps**. A pipeline that cannot
reproduce the closed answer does not get to produce the open one. The planted
canary and prefix-invariance disciplines apply to this pipeline as to every
other (ADR-040).

## 2026-08-06 — Stage C.18 complete: machinery validated, thin tail untouched

- **Registration landed first** (6025f5c, above) — bars, floor, multiplicity,
  halves, capacity, upper-bound statement and outcome map all predate the data.
- **Known-answer reproduction:** the pipeline reproduces C.9's closed nets on
  C.9's own window through the same reader — **BTC −3.0510 vs −3.05 (Δ −0.001
  bps), ETH −2.7533 vs −2.75 (Δ −0.0033 bps)**, tolerance 0.5, on 491,950 /
  278,805 resolved trades — with thin coins excluded by allowlist at the parse
  level (`run_census(coins=...)`).
- **The scored population stays unread.** `run_registered_census` raises before
  2026-08-11T00:00Z (tested to the nanosecond); every test is synthetic; the
  adverse canary fires in BOTH directions so the census verdict will mean
  something (ADR-040).
- H6's register entry now carries the registration commit. 8 new tests
  (`tests/test_registered_census.py`); `make lint`, `make typecheck`,
  `make test` clean — **319 tests**. Recorders alive; nothing bought; the ten
  thin perps untouched.

## 2026-08-06 — Stage C.19: rug-detection audit bars, registered before probing

**Nothing has been probed at the time of writing. This is a detection-track
stage, not an alpha stage — the C.17 decision stands and is not reopened.**

### The go bar, fixed before any source is touched

**GO requires ≥ 5,000 labeled tokens obtainable free, with pre-event feature
coverage.** Below that the finding is **too thin by prior declaration**, in the
C.15 pattern. The floor is stated now so it cannot move after the counts exist.

### The known-answer bar for heuristic labels

A heuristic label set (mint authority, freeze authority, LP burn/lock, holder
concentration, liquidity-removal events) must be spot-checked against ~10
publicly documented Solana rug pulls with well-attested on-chain histories,
**from pre-event chain state alone**. The hit count is reported plainly as a
sanity count, not a detection result. **A heuristic scheme that misses
documented rugs fails the audit regardless of how many tokens it can label**;
a 5,000-token dataset built from labels that cannot recover ground truth does
not clear the go bar. Cases whose public documentation is too vague to fix the
on-chain facts are dropped, never forced.

### The economics caveat, unhedged, to lead the report

The detection layer has standalone value as a safety scorer. The profit arms
mostly re-enter measured territory: launch-speed competition and 50–200 bps
AMM round trips were both documented in the week-one report; the scam-adjacent
base rate among pump.fun tokens runs near **98.7% per Solidus Labs**; and
memecoins have no borrow, so **no short side exists**. The unclosed profit
mechanisms are **avoidance and exit-timing for positions otherwise held, and
the tool itself**. The report says exactly that rather than implying a trading
strategy is waiting at the end.

### Standing disciplines applied from the first probe

Survivorship: a source that prunes dead tokens is close to useless here —
**dead tokens are the positive class**. Leakage: labels are defined by future
events, so every feature is strictly pre-event, and the planted-future canary
and prefix-invariance disciplines apply from the first feature ever computed.
Measured beats documented (C.1): rate limits recorded as observed, not as
published. Everything retrieved is snapshotted immutable with the C.10
manifest; new sources are declared per the C.9.1 scheme. Buy nothing.

## 2026-08-06 — Stage C.19 complete: rug-detection availability audit — GO

**Verdict: GO against the pre-registered floor (35e3466) — the hard-rug class
alone yields ~76,000 labeled pools free, 15× the 5,000 floor.** Detection
track only; the C.17 decision stands (ADR-044).

- **Inventory, measured:** SolRPDS alive and snapshotted whole (116,308 pools
  2021→Nov-2024, 4 CSVs, keyless; labels are end-of-life aggregates — label
  side only). RugCheck keyless at ~0.85 s/report, zero 429s in a burst — but
  its `rugged` flag recovered **0 of 4 documented rugs** and is disqualified
  as ground truth. DexScreener **retains dead pairs** (LIBRA/HAWK/kid-QUANT
  resolve with launch timestamps). GoPlus covers the honeypot axis keyless.
  Public RPC = current state only. pump.fun API **HTTP 530 in practice**;
  Bitquery/Dune/Birdeye 401 (keyed); Helius free-key-required; **MELT paper
  live but no public data link — availability unverified**, recorded rather
  than designed around.
- **Known-answer spot-check: hit 1 (LIBRA — Meteora LP locked 0%, pre-event
  knowable), indeterminate 3 (HAWK, kid-QUANT, M3M3 — concentration-mechanism
  rugs whose launch-time holdings need historical indexing), missed 0.**
  Further candidates with vague documentation were dropped, not forced. The
  binding constraint is named: pre-event features for concentration classes
  need a free Helius key or SolRPDS-style parsing.
- **Taxonomy:** no source distinguishes all four mechanisms; recommended
  construction is a four-class label (hard rug ← SolRPDS liquidity removal,
  honeypot ← GoPlus freeze/transfer fields, soft/slow rug ← launch-window
  holder flows, unlabeled today). Base rate stated plainly: at ~98.7%
  scam-adjacent, accuracy is worthless and the scorer is judged on
  honest-minority precision.
- **Leakage trap named:** labels are future events; LIBRA's current 98.2%
  top-5 concentration is post-dump residue, not a feature. Canary + prefix
  disciplines apply from the first feature (ADR-040/042).
- 14 artifacts snapshotted with sha256 + retrieval date; six sources declared
  in venues.yaml. **Buy-nothing held: zero spent, zero keys created.**
  Economics caveat led the report, unhedged, per the registration. ADR-044.
- `make lint`, `make typecheck`, `make test` clean — 319 tests (config-only
  changes). All three recorders alive throughout.

## 2026-08-06 — Stage C.20: baselines and the first-model bar, registered before any model exists

**No model exists on this track. These numbers and this bar predate all of
them, in the C.16/C.17 pattern.**

**Measured label distribution** (SolRPDS 116,308 pools, keyless labels v0):
hard_rug **75,996**, honest_candidate **34,791** (29.91% — an upper bound on
honesty, contaminated from above by unlabeled soft/slow rugs),
unlabeled_residual **5,521**. The honest minority is what every later
evaluation turns on.

**Registered trivial baselines, minority (honest) class:**

| baseline | honest precision | honest recall |
|---|---|---|
| always-rug | **undefined** (0/0 — reported as such, never 0 or 1) | 0.000 |
| always-honest | 0.2991 (measured) / 0.013 (external 98.7% base rate) | 1.000 |
| random at base rate | 0.2991 / 0.013 | 0.2991 / 0.013 |

**The bar the first model must clear, fixed now:** on a time-split holdout
(train ≤ 2023, test Jan–Nov 2024), using only features classified
**pre-event** under ADR-045, with the planted-future canary and
prefix-invariance suite green: **honest-candidate precision ≥ 0.60 at recall
≥ 0.50** — at least 2× the always-honest baseline on the measured
distribution — reported beside the external-base-rate framing. Anything short
is FAIL; a model that beats the bar only with post-event or
indexer-dependent features has not cleared it.

## 2026-08-06 — Stage C.20 complete: viability confirmed, labels built, bar registered

- **Task 1, the gate: avoidance is viable.** Hard-rug lifetime (removal
  proxied by last pool activity, proxy reasoning recorded): Q25 2.6 h, median
  **2.55 days**, Q75 35.8 d; **0.51% within 60 s, 3.93% within 5 min**, 58.5%
  beyond 24 h. ~96% of the class outlives score-and-act latency. Scope limit
  stated: SolRPDS is the post-graduation stratum; bonding-curve instant
  deaths live outside it. **Helius-key value: HIGH** — there is time to act,
  and the key unlocks the concentration mechanisms for that population.
- **Task 2, labels_v0 (116,308 pools):** hard_rug 75,996 / honest_candidate
  **34,791** (29.9%, upper bound, the minority everything turns on) /
  unlabeled_residual 5,521 explicit. Honeypot from GoPlus: 5/44 flagged in a
  stratified 60-mint sample, 16 unresolved kept as **None** never benign;
  full sweep ~42 h free. RugCheck `rugged` discarded per C.19.
- **Task 3, provenance:** 9 usable pre-event fields keyless; honeypot class
  fully supported, hard-rug partially, soft/slow unsupported without an
  indexer. Monotonic-authority inference codified and tested
  (`authority_pre_event`): present-now ⇒ present-at-launch, one direction
  only. ADR-045.
- **Task 4, registered at 902d2e6 before any model:** baselines (always-rug
  precision undefined — reported as such; always-honest 0.2991 measured /
  0.013 external) and the bar: honest precision ≥ 0.60 at recall ≥ 0.50,
  time-split holdout, pre-event features only, leakage suites green.
- `research/detection/` + 7 tests; labels_v0.csv regenerable from immutable
  snapshots; GoPlus sample snapshotted with sha256. `make lint`,
  `make typecheck`, `make test` clean — **326 tests**. Zero keys, zero spend,
  recorders alive throughout.

## 2026-08-06 — Stage C.21: gate built, pipeline leakage-wired, key absent

- **The finding: `MLCE_HELIUS_API_KEY` does not exist** — not in `.env`
  (56 B, mtime 2026-08-02) and not in the environment; verified by count,
  value never printed. Credit accounting: **0 estimated, 0 spent, 0 sent**.
  The registered bar (902d2e6) was **not attempted** — distinct from not
  cleared.
- **Task 1 complete:** `helius_api_key` SecretStr + `require_helius_key()`
  (raises naming the variable — verified live), `.env.example` line, `.env`
  ignored/untracked. Credit gate with cap 30,000 (dated, weights {rpc:1,
  enhanced:10} marked UNVERIFIED, method = request-count derivation since no
  keyless usage endpoint), append-only ledger surviving restart, refusal that
  writes nothing — all under test.
- **Task 2 registered (ADR-047):** 540-token class×year stratified sample
  (240 train-era, 300 test-era), cost formula against a 12-mint measured
  probe, proceed only ≤ 50% of remaining cap, shrink-and-report otherwise.
- **Tasks 3/4 wired first (ADR-048):** 1,800 s window justified from C.20
  lifetimes; `WindowLeakError` refuses event-inside-window pools (never
  clamps); six indexer features replayed from tx records; decontamination at
  70%/72 h/30 d with boundary tests; prefix + canary suites green on
  synthetic **before any real feature exists**.
- **Task 5 blocked** on the key; the run order for the moment it lands is
  written in the report. ADR-046/047/048 appended.
- `make lint`, `make typecheck`, `make test` clean — **333 tests**, 7 new.
  Recorders alive; census window closes 2026-08-11 untouched.

## 2026-08-07 — C.21 executed with the key: pipeline proven, bar not cleared

- Key landed; probe 67 req (670 weighted); sweep stopped by the gate at
  **14,740/14,665 budget, 178/200 tokens** — refuse-and-report worked live.
- **98/178 truncated** before T0 (12-page cap): pagination-to-launch is the
  real cost driver. **80 modeled pools**; 0 window-leak exclusions.
- Decontamination measured: **2/18 honest reclassified** (1 soft, 1 slow).
- **Bar (902d2e6) attempted and NOT CLEARED** on either label version: test
  fold held 5 honest; model predicted none (precision 0/0, recall 0.0).
  Limitation named: **feature coverage/sample size**, not absent signal (top
  features pre-event and directionally sensible) and not label quality.
- Next requires: deeper-per-token fetch on fewer tokens, T0-forward
  pagination, or a paid tier — operator decision, priced by this run.
- Ledger 15,410/30,000; snapshots manifested; recorders alive; census window
  (2026-08-11) untouched. Tests 333 green.

## 2026-08-07 — Stage C.22: T0 pagination fixed; bar attempted at scale, not cleared

- **Method fix proven (ADR-049):** sig-walk to T0 (RPC 1k/page, weight 1) +
  capped enhanced detail on the window slice. **T0 reached 81% (171/210) vs
  C.21's ~45%** — feature coverage roughly doubled. Correctness checked:
  window tx sets match where both methods reached. Probe JSON was lost to a
  timeout before write; the sweep is the authoritative measurement, stated.
- **Cap 30k→60k, dated, AFTER method proof** (C.7 pattern); self-imposed, not
  the Helius limit. Sweep estimate 12,600 checked before fetch; **actual 9,865**,
  ledger 27,601/60,000.
- **Bar (902d2e6) NOT CLEARED, both label versions:** v0 precision 0.411 /
  recall 0.639; decon 0.294 / 0.500 — recall clears, precision short of 0.60.
  Decontam reclassified 7/80 honest→soft (9%), lowering precision honestly.
- **Limiting factor moved:** with n=171 / 36 test honest, no longer sample
  size — it's **feature signal strength**. `top5_concentration_wend` now
  dominant; **`creator_allocation_t0` collapsed 147→0**, vindicating C.21's
  n=80 artifact call. Next lever = pre-launch funding-graph depth, not pools.
- Snapshots manifested; recorders alive; census window untouched. 333 tests.
- **CLAUDE.md:** added the standing rule to give a measured ETA for every prompt.

## 2026-08-07 — Stage C.23 complete: honest bar reachable but not cleared; creator history does not move it

- **Reachability (the gate):** on a proper 2024 test fold (n=194), the honest
  bar is reachable as machinery, not cleared as signal. Decontaminated honest
  precision **0.574 @ recall≥0.5** at a 50% base rate — +0.07 above chance. Raw
  v0 "clears" at 0.984, but that is hard-rug detection, the easy case (v0 honest
  still contains the soft/slow rugs).
- **The control that isolates the cause:** same fold, same n, same train — v0
  separates at 0.98, decon sits at base rate with a flat PR curve (max precision
  at recall 1.0). A small train would sink v0 too; it does not. So **signal, not
  sample.**
- **Creator history (the C.22 lever), built and measured:** coverage **42.7%**
  (120/281), far above the feared "tiny" — the class is populated. Yet decon
  precision moves **0.574 → 0.570 (inert)** and v0 *drops* 0.984 → 0.648 (Brier
  +0.067) — `creator_prior_launches` overfits the 2023→2024 split. It adds a
  rank-2 train-fit; **`top5_concentration_wend` stays the sole carrier.**
- **SolRPDS has no creator field** (verified across CSV+JSON) — creator derived
  from the Helius fetch; strict T0-prefix leakage guard wired first (ADR-050),
  4 tests green before any real creator feature was computed.
- **Limiting factor, named:** not threshold, not sample, not unbuilt features —
  **absent signal at the honest/soft-slow boundary.** Pre-event on-chain state
  at T0+30min flags blatant hard rugs, not honest-vs-slow-rug. The avoidance
  framing on pre-event on-chain features alone is answered negatively; any
  continuation leaves that feature space (post-launch trajectory / off-chain
  provenance).
- **Sweep:** 360 designed, T0 reached 281 (78.1%, holds C.22's 81% at 1.7× the
  size); 18,370 credits actual vs 16,920 est (+8.6%); ledger 45,971 / 60,000,
  **cap not raised.** Feature matrix persisted to `features_c23.csv` (closes
  C.22's non-persistence gap), regenerable from immutable snapshots.
- Recorders untouched; census window (2026-08-11) not read. 337 tests
  (+4 creator), ruff + mypy clean. ADR-050 appended; report.md §C.23 written.

## 2026-08-07 — Stage C.24 complete: post-launch behaviour is a qualified positive at 6h+; hard-rug scorer shipped

- **The result inverts the pre-registration.** C.24 expected the honest boundary
  absent post-launch too; instead behavioural features **clear the bar at 6h**
  (decon precision 0.654 @ recall 0.53 vs 0.557 base, lift +0.097) and 24h
  (0.731), beating launch state at matched population. **The registered end
  condition's negative branch does NOT fire** — a cutoff cleared above the noise
  floor, so the boundary is not recorded as absent.
- **Qualified, and the qualifications are the finding:** the absolute clear is
  base-rate-inflated by survivor conditioning (24h base 0.630 > 0.60 bar), so the
  defensible signal is the **~+0.10 lift** — marginal (~1.8 SE), only modestly
  above C.23's +0.074 launch lift; and the sample is conservatively biased toward
  faded-honest pools (from-now pagination can't afford thriving survivors).
  Behaviour **displaces** launch concentration (behavioural-only ≥ launch+beh).
- **Task 1 cost probe, two premise corrections:** `getSignaturesForAddress`
  carries **no signer** (signer features need ~100x-dearer detail → signature
  level only); the from-now walk is O(full history), so **cost correlates with
  the label** (hard rugs shallow, survivors deep) — a measured reachability wall.
- **Task 5 deliverable, direction corrected:** the "0.984/0.538" is honest
  **CLEARANCE**, not a hard-rug alarm (0.464). Ships as a clearance scorer
  (`scorer.py` + `train_scorer.py`), persisted + regenerable + scope-documented.
- **Leakage-first (Task 3):** `behavior.py` + canary/prefix/no-activity-after-X
  green before the first real feature; strict `< cutoff` bound (a planted burst
  at exactly the cutoff caught the inclusive bound).
- **Register:** HYPOTHESES gains a Detection-track section — **D1** hard-rug
  clearance (shipped), **D2** honest boundary (absent at T0, qualified positive
  post-launch, open for confirmation). Census H6 remains the sole open alpha item.
- **Robustness:** the first monolithic sweep was killed holding all pools' sigs
  in memory; refactored to a **streaming, resumable** walker (checkpoint per pool,
  sigs discarded) — the 14 GiB-box rule. Also fixed 5 pre-existing ambiguous-minus
  / pairwise lint violations (C.9/C.17 files) so `make lint` is repo-green.
- **Budget:** 11,008 / 60,000 remaining, cap **NOT** raised (second-raise rule
  held). `behavior_c24.csv` + `hard_rug_scorer.txt` persisted, regenerable.
  Recorders alive; census window not read. ADR-051/052 appended. **347 tests**
  (+10: behaviour + scorer); make lint / typecheck / test all green.
