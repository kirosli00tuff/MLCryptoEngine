"""Spread-to-cost and adverse-selection measurement (Stage C.9).

The spread-to-cost ratio is a property of an *instrument*, not a venue: fees
scale with notional and stay roughly constant in basis points, while spreads
widen sharply on thin instruments. Measuring it therefore means surveying many
instruments, not generalising from the two tightest ones available.
"""

from research.microstructure.adverse import DEFAULT_HORIZONS_MS, AdverseSelection
from research.microstructure.census import (
    AGGRESSOR_SIGN,
    CensusResult,
    InstrumentCensus,
    run_census,
)
from research.microstructure.spread import BOUNDS_BPS, REPORT_THRESHOLDS, SpreadCensus

__all__ = [
    "AGGRESSOR_SIGN",
    "BOUNDS_BPS",
    "DEFAULT_HORIZONS_MS",
    "REPORT_THRESHOLDS",
    "AdverseSelection",
    "CensusResult",
    "InstrumentCensus",
    "SpreadCensus",
    "run_census",
]
