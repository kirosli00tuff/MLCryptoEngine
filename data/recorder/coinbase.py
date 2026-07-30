"""Coinbase Advanced Trade connector: level2 + market_trades + heartbeats channels."""

from __future__ import annotations

from typing import Any

import orjson

from data.recorder.base import VenueRecorder


class CoinbaseRecorder(VenueRecorder):
    """Subscribes to the full-depth level2 channel, trades, and venue heartbeats.

    Every Advanced Trade WS message carries a monotonically increasing
    ``sequence_num`` per connection; the heartbeats channel guarantees traffic
    during quiet markets so sequence continuity is always observable.
    """

    venue_key = "coinbase"

    def subscribe_messages(self) -> list[str]:
        payloads: list[str] = []
        for channel in ("level2", "market_trades"):
            sub: dict[str, Any] = {
                "type": "subscribe",
                "channel": channel,
                "product_ids": self.venue_cfg.symbols,
            }
            payloads.append(orjson.dumps(sub).decode())
        payloads.append(orjson.dumps({"type": "subscribe", "channel": "heartbeats"}).decode())
        return payloads

    def sequence_of(self, message: dict[str, Any]) -> int | None:
        seq = message.get("sequence_num")
        return seq if isinstance(seq, int) else None
