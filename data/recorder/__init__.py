"""Asyncio WebSocket recorders that write raw exchange-native messages losslessly."""

from data.recorder.base import DryRunLimiter, VenueRecorder
from data.recorder.coinbase import CoinbaseRecorder
from data.recorder.hyperliquid import HyperliquidRecorder
from data.recorder.kraken import KrakenRecorder

RECORDER_TYPES: dict[str, type[VenueRecorder]] = {
    KrakenRecorder.venue_key: KrakenRecorder,
    CoinbaseRecorder.venue_key: CoinbaseRecorder,
    HyperliquidRecorder.venue_key: HyperliquidRecorder,
}

__all__ = [
    "RECORDER_TYPES",
    "CoinbaseRecorder",
    "DryRunLimiter",
    "HyperliquidRecorder",
    "KrakenRecorder",
    "VenueRecorder",
]
