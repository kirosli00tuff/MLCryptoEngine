"""Normalized order book event types shared by parsers and the builder."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Side(StrEnum):
    BID = "bid"
    ASK = "ask"


@dataclass(frozen=True, slots=True)
class Level:
    """One price level. Decimal end to end: exchanges quote discrete ticks."""

    price: Decimal
    qty: Decimal


@dataclass(frozen=True, slots=True)
class BookEvent:
    """A venue book message normalized to snapshot-or-delta form."""

    venue: str
    symbol: str
    recv_ns: int
    is_snapshot: bool
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]
    seq: int | None = None
    checksum: int | None = None
