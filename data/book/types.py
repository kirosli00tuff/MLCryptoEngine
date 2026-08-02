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


@dataclass(frozen=True, slots=True)
class BboEvent:
    """A top-of-book update: both touches only, with resting order counts.

    Deliberately a separate type from :class:`BookEvent` rather than a
    one-level book (ADR-013): a BBO update says nothing about depth beyond
    the touch, and feeding it through the book builder would fabricate a
    book that looks one level deep and is not. Consumers that need depth
    read book events; consumers that need a fast, accurate touch read these.

    ``bid_n``/``ask_n`` are the number of resting orders at each touch where
    the venue reports it (Hyperliquid does), else ``None``.
    """

    venue: str
    symbol: str
    recv_ns: int
    bid_price: Decimal
    bid_qty: Decimal
    ask_price: Decimal
    ask_qty: Decimal
    bid_n: int | None = None
    ask_n: int | None = None
