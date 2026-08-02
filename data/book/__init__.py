"""Order book reconstruction: replay raw feeds into a maintained L2 book."""

from data.book.builder import ApplyResult, BookBuilder, SequenceTracker
from data.book.coinbase_parse import parse_coinbase
from data.book.emit import SnapshotEmitter, bbo_row
from data.book.hyperliquid_parse import (
    EMITTED_CHANNELS as HYPERLIQUID_CHANNELS,
)
from data.book.hyperliquid_parse import (
    parse_hyperliquid,
    parse_hyperliquid_bbo,
)
from data.book.kraken_parse import parse_kraken
from data.book.types import BboEvent, BookEvent, Level, Side

# Which channels each venue's parser actually turns into stream events. The
# capability matrix checks a venue's REQUIRED_CHANNELS against this, so a
# feature can never be credited to a venue whose parser does not emit the
# channel that feature needs (see research/features/capabilities.py).
PARSER_CHANNELS: dict[str, frozenset[str]] = {
    "kraken": frozenset({"book"}),
    "coinbase": frozenset({"l2_data"}),
    "hyperliquid": HYPERLIQUID_CHANNELS,
    "cme": frozenset({"mbp-10"}),
}


def emitted_channels(venue: str) -> frozenset[str]:
    """Channels this venue's parser emits into the event stream."""
    return PARSER_CHANNELS.get(venue, frozenset())


__all__ = [
    "PARSER_CHANNELS",
    "ApplyResult",
    "BboEvent",
    "BookBuilder",
    "BookEvent",
    "Level",
    "SequenceTracker",
    "Side",
    "SnapshotEmitter",
    "bbo_row",
    "emitted_channels",
    "parse_coinbase",
    "parse_hyperliquid",
    "parse_hyperliquid_bbo",
    "parse_kraken",
]
