"""Kraken WS v2 book checksum (CRC32 over formatted top-10 levels).

Algorithm per Kraken docs: format each of the top 10 asks (ascending) then the
top 10 bids (descending) as ``price`` then ``qty``, each rendered at the
symbol's fixed decimal precision, with the decimal point removed and leading
zeros stripped; concatenate everything and take CRC32.
"""

from __future__ import annotations

import zlib
from decimal import Decimal
from functools import partial

from data.book.builder import ChecksumFn
from data.book.types import Level


def _format_value(value: Decimal, decimals: int) -> str:
    text = f"{value:.{decimals}f}".replace(".", "").lstrip("0")
    return text if text else "0"


def kraken_book_checksum(
    bids: list[Level],
    asks: list[Level],
    price_decimals: int,
    qty_decimals: int,
) -> int:
    parts: list[str] = []
    for level in asks[:10]:
        parts.append(_format_value(level.price, price_decimals))
        parts.append(_format_value(level.qty, qty_decimals))
    for level in bids[:10]:
        parts.append(_format_value(level.price, price_decimals))
        parts.append(_format_value(level.qty, qty_decimals))
    return zlib.crc32("".join(parts).encode("ascii"))


def checksum_fn_for(price_decimals: int, qty_decimals: int) -> ChecksumFn:
    """A builder-compatible checksum function bound to one symbol's precisions."""
    return partial(
        kraken_book_checksum,
        price_decimals=price_decimals,
        qty_decimals=qty_decimals,
    )
