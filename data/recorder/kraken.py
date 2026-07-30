"""Kraken spot connector: WebSocket v2 book + trade channels."""

from __future__ import annotations

from typing import Any

import orjson

from data.recorder.base import VenueRecorder


class KrakenRecorder(VenueRecorder):
    """Subscribes to the deepest public book channel plus trades.

    Kraken WS v2 pushes a full snapshot on subscribe and a CRC32 checksum on
    every book update; there is no per-message sequence number, so gap detection
    for Kraken rests on checksum verification during book reconstruction.
    """

    venue_key = "kraken"

    def subscribe_messages(self) -> list[str]:
        book_params: dict[str, Any] = {
            "channel": "book",
            "symbol": self.venue_cfg.symbols,
            "depth": self.venue_cfg.book_depth,
            "snapshot": True,
        }
        trade_params: dict[str, Any] = {
            "channel": "trade",
            "symbol": self.venue_cfg.symbols,
        }
        return [
            orjson.dumps({"method": "subscribe", "params": book_params}).decode(),
            orjson.dumps({"method": "subscribe", "params": trade_params}).decode(),
        ]

    def sequence_of(self, message: dict[str, Any]) -> int | None:
        # Kraken WS v2 public channels carry no sequence number.
        return None
