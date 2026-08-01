"""Strategy evaluation reporting contract (schema + generated-type exporters)."""

from backtest.reporting.schema import (
    CostAssumption,
    DrawdownPoint,
    EquityPoint,
    LatencyPercentiles,
    Mode,
    PerformanceReport,
    SlippageStats,
    TradeRecord,
)
from backtest.reporting.ts_export import write_generated

__all__ = [
    "CostAssumption",
    "DrawdownPoint",
    "EquityPoint",
    "LatencyPercentiles",
    "Mode",
    "PerformanceReport",
    "SlippageStats",
    "TradeRecord",
    "write_generated",
]
