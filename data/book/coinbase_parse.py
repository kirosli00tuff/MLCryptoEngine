"""Parse raw Coinbase Advanced Trade messages into normalized book events."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from data.book.types import BookEvent, Level

VENUE = "coinbase"


def envelope_sequence(message: dict[str, Any]) -> int | None:
    """The connection-wide sequence number carried by every Advanced Trade message."""
    seq = message.get("sequence_num")
    return seq if isinstance(seq, int) else None


def parse_coinbase(message: dict[str, Any], recv_ns: int) -> list[BookEvent]:
    """Book events in a raw l2_data message; empty for other channels.

    Coinbase sends price and quantity as strings, so Decimal conversion is
    exact. Side "offer" maps to ask; ``new_quantity`` of 0 removes the level.
    """
    if message.get("channel") != "l2_data":
        return []
    seq = envelope_sequence(message)
    events: list[BookEvent] = []
    raw_events = message.get("events")
    if not isinstance(raw_events, list):
        return []
    for item in raw_events:
        if not isinstance(item, dict) or "product_id" not in item:
            continue
        bids: list[Level] = []
        asks: list[Level] = []
        updates = item.get("updates")
        if isinstance(updates, list):
            for update in updates:
                if not isinstance(update, dict):
                    continue
                try:
                    level = Level(
                        Decimal(str(update["price_level"])),
                        Decimal(str(update["new_quantity"])),
                    )
                except (KeyError, ArithmeticError):
                    continue
                if update.get("side") == "bid":
                    bids.append(level)
                else:
                    asks.append(level)
        events.append(
            BookEvent(
                venue=VENUE,
                symbol=str(item["product_id"]),
                recv_ns=recv_ns,
                is_snapshot=item.get("type") == "snapshot",
                bids=tuple(bids),
                asks=tuple(asks),
                seq=seq,
                checksum=None,
            )
        )
    return events
