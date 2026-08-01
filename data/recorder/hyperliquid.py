"""Hyperliquid perps connector: l2Book + bbo + trades + activeAssetCtx.

Feed characteristics that constrain everything downstream:

- ``l2Book`` is a FULL-SNAPSHOT stream pushed per block, with a minimum
  interval of roughly 0.5 s — not incremental updates. Observed BTC
  inter-snapshot intervals of 0.37-5.4 s (2026-08-01 capture). Order flow,
  queue dynamics, and depth deltas are NOT recoverable at meaningful
  resolution from snapshot differences; the feature capability matrix
  (research/features/capabilities.py) rules them out for this venue.
- ``bbo`` sends only when the best bid or offer changes and carries no depth
  beyond the touch (px/sz/n per side).
- ``trades`` carries executed fills with the taker side ("B" buy / "A" sell).
- ``activeAssetCtx`` carries funding, open interest, mark/oracle/mid prices.
- The feed provides neither sequence numbers nor checksums; validation
  scores this venue on snapshot cadence instead (both integrity checks
  render "n/a", never 0 — the Stage 1.6 rule).

Reconnects use the base class's backoff and gap logging unchanged. On
resubscribe the acknowledgement is immediately followed by a fresh l2Book
snapshot — that snapshot IS the recovery of anything missed during the
disconnect, so no separate snapshot request is made (none exists on the WS
API) and downstream book state rebuilds from it exactly as it does from any
other snapshot in the stream.

Coin names come from config; they were discovered from the info endpoint
({"type": "meta"}), not assumed — see venues.yaml.
"""

from __future__ import annotations

from typing import Any

import orjson

from data.recorder.base import VenueRecorder

CHANNELS = ("l2Book", "bbo", "trades", "activeAssetCtx")


class HyperliquidRecorder(VenueRecorder):
    """Subscribes every configured coin to all four public channels."""

    venue_key = "hyperliquid"

    def subscribe_messages(self) -> list[str]:
        return [
            orjson.dumps(
                {"method": "subscribe", "subscription": {"type": channel, "coin": coin}}
            ).decode()
            for coin in self.venue_cfg.symbols
            for channel in CHANNELS
        ]

    def sequence_of(self, message: dict[str, Any]) -> int | None:
        # Hyperliquid public channels carry no sequence number.
        return None
