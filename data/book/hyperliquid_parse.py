"""Parse raw Hyperliquid messages into normalized book and BBO events.

Two channels produce events, kept structurally distinct (ADR-013):

- ``l2Book`` → :class:`BookEvent`, a complete 20-level snapshot that
  replaces the book. Measured cadence is p50 5,387 ms, so it carries depth
  but nothing short-horizon.
- ``bbo`` → :class:`BboEvent`, both touches with size and resting order
  count, at p50 123 ms. This is the only channel on this venue fast enough
  for sub-5-second features, which is why it is plumbed separately rather
  than merged into book state: a BBO update is not a one-level book, and
  feeding it through the book builder would fabricate depth that isn't
  there.

``trades`` is handled by :mod:`data.trades.parse`; ``activeAssetCtx``
(funding / open interest / mark price) is captured raw and not parsed here.

The feed provides no sequence numbers and no checksums, so events carry
``seq=None, checksum=None`` and validation scores this venue on snapshot
cadence.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from data.book.types import BboEvent, BookEvent, Level

VENUE = "hyperliquid"
# Channels this parser turns into stream events. The capability matrix's
# REQUIRED_CHANNELS check is satisfied from this set, so adding or removing
# a channel here is what flips a venue's features on or off — not a docstring.
EMITTED_CHANNELS = frozenset({"l2Book", "bbo"})


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


def parse_hyperliquid_bbo(message: dict[str, Any], recv_ns: int) -> list[BboEvent]:
    """BBO events in a raw bbo message; empty for every other channel.

    The payload is ``{"bbo": [<bid>, <ask>]}`` where each side is
    ``{"px", "sz", "n"}``. A side can be null in principle (empty book), in
    which case no event is emitted rather than a half-populated one — a
    missing touch is not a touch at price zero.
    """
    if message.get("channel") != "bbo":
        return []
    data = message.get("data")
    if not isinstance(data, dict) or "coin" not in data:
        return []
    pair = data.get("bbo")
    if not isinstance(pair, list) or len(pair) != 2:
        return []
    bid, ask = pair
    if not isinstance(bid, dict) or not isinstance(ask, dict):
        return []
    try:
        bid_price = Decimal(str(bid["px"]))
        bid_qty = Decimal(str(bid["sz"]))
        ask_price = Decimal(str(ask["px"]))
        ask_qty = Decimal(str(ask["sz"]))
    except (KeyError, InvalidOperation):
        return []
    bid_n = bid.get("n")
    ask_n = ask.get("n")
    return [
        BboEvent(
            venue=VENUE,
            symbol=str(data["coin"]),
            recv_ns=recv_ns,
            bid_price=bid_price,
            bid_qty=bid_qty,
            ask_price=ask_price,
            ask_qty=ask_qty,
            bid_n=int(bid_n) if isinstance(bid_n, int) else None,
            ask_n=int(ask_n) if isinstance(ask_n, int) else None,
        )
    ]
