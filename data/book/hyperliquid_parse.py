"""Parse raw Hyperliquid messages into normalized book events.

Only ``l2Book`` produces book events: each message is a complete snapshot
(``is_snapshot=True``) that replaces the book. ``bbo`` is deliberately NOT
mapped into book events — merging touch-only updates into a snapshot-stream
book would fabricate pseudo-incremental depth that downstream code could
mistake for real order flow, exactly what the capability matrix exists to
prevent. ``trades`` is handled by :mod:`data.trades.parse`;
``activeAssetCtx`` (funding / open interest / mark price) is captured raw
and not parsed at this stage.

The feed provides no sequence numbers and no checksums, so events carry
``seq=None, checksum=None`` and validation scores this venue on snapshot
cadence.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from data.book.types import BookEvent, Level

VENUE = "hyperliquid"


def _levels(entries: Any) -> tuple[Level, ...] | None:
    if not isinstance(entries, list):
        return None
    out: list[Level] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        try:
            out.append(Level(Decimal(str(entry["px"])), Decimal(str(entry["sz"]))))
        except (KeyError, InvalidOperation):
            return None
    return tuple(out)


def parse_hyperliquid(message: dict[str, Any], recv_ns: int) -> list[BookEvent]:
    """Book events in a raw l2Book message; empty for every other channel."""
    if message.get("channel") != "l2Book":
        return []
    data = message.get("data")
    if not isinstance(data, dict) or "coin" not in data:
        return []
    levels = data.get("levels")
    if not isinstance(levels, list) or len(levels) != 2:
        return []
    bids = _levels(levels[0])
    asks = _levels(levels[1])
    if bids is None or asks is None:
        return []
    return [
        BookEvent(
            venue=VENUE,
            symbol=str(data["coin"]),
            recv_ns=recv_ns,
            is_snapshot=True,
            bids=bids,
            asks=asks,
            seq=None,
            checksum=None,
        )
    ]
