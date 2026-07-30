"""Parse raw Kraken WS v2 messages into normalized book events."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from data.book.types import BookEvent, Level

VENUE = "kraken"


def _levels(entries: Any) -> tuple[Level, ...]:
    if not isinstance(entries, list):
        return ()
    return tuple(
        Level(Decimal(str(e["price"])), Decimal(str(e["qty"])))
        for e in entries
        if isinstance(e, dict) and "price" in e and "qty" in e
    )


def parse_kraken(message: dict[str, Any], recv_ns: int) -> list[BookEvent]:
    """Book events in a raw Kraken message; empty for non-book messages.

    Kraken floats are stringified before Decimal conversion; exactness is
    recovered downstream by formatting at the symbol's fixed precision.
    """
    if message.get("channel") != "book":
        return []
    is_snapshot = message.get("type") == "snapshot"
    events: list[BookEvent] = []
    data = message.get("data")
    if not isinstance(data, list):
        return []
    for item in data:
        if not isinstance(item, dict) or "symbol" not in item:
            continue
        checksum = item.get("checksum")
        events.append(
            BookEvent(
                venue=VENUE,
                symbol=str(item["symbol"]),
                recv_ns=recv_ns,
                is_snapshot=is_snapshot,
                bids=_levels(item.get("bids")),
                asks=_levels(item.get("asks")),
                seq=None,
                checksum=checksum if isinstance(checksum, int) else None,
            )
        )
    return events
