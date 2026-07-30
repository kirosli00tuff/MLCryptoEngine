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
