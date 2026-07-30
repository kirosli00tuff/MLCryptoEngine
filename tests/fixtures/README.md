# Test fixtures

Real exchange messages recorded live from public WebSocket feeds on 2026-07-30
by `data/recorder` (no synthetic data).

- `kraken_messages.ndjson` — Kraken WS v2, byte-exact raw messages: status,
  subscribe acks, two trades, one BTC/USD book snapshot (depth 100) and the 60
  consecutive book updates that followed it. Because no update is skipped, the
  CRC32 checksum chain is intact: replaying this file through `BookBuilder`
  with checksum verification must produce zero failures.
- `coinbase_messages.ndjson` — Coinbase Advanced Trade, the first 40 messages
  of a session in original order (`sequence_num` contiguous from 0):
  subscriptions acks, l2_data snapshot + updates, market_trades, heartbeats.
  The only modification: each snapshot event's `updates` array is truncated to
  the top 40 bids + 40 offers (full-depth snapshots exceed 1 MB); all other
  messages are byte-exact. Coinbase provides no checksum, so truncation does
  not affect any validated invariant.

Regenerate by recording briefly (`make record`, Ctrl-C) and rerunning the
extraction snippet in the repo history (commit that added these files).
