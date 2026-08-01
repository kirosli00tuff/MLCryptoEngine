"""PerformanceReport: the contract every strategy evaluation must emit.

``mode`` is required and has **no default**. A report that cannot state
whether it came from a simulation, paper trading, or real money is not a
valid report — and any interface that displays these must keep simulated and
live results visually unmistakable (CLAUDE.md).

Timestamps are epoch nanoseconds on the recorder's local clock, consistent
with the entire pipeline. Money values are in quote currency; per-trade and
aggregate P&L are reported gross and net because the difference — fees and
slippage — is exactly where single-digit-bps strategies die.

This schema is the single source of truth: JSON Schema and the TypeScript
types under ``desktop/src/lib/generated/`` are generated from it (``make
types``) and never edited by hand; a test fails on drift.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Mode(StrEnum):
    """Where the numbers came from. Required everywhere, defaulted nowhere."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class CostAssumption(BaseModel):
    """The fee/spread assumption the evaluation was run under."""

    mode: Literal["maker", "taker"]
    fee_bps_per_leg: float = Field(ge=0)
    includes_spread: bool


class EquityPoint(BaseModel):
    ts_ns: int
    gross: float
    net: float


class DrawdownPoint(BaseModel):
    ts_ns: int
    drawdown_pct: float = Field(le=0)


class TradeRecord(BaseModel):
    entry_ns: int
    exit_ns: int
    side: Literal["long", "short"]
    size: float = Field(gt=0)
    gross_pnl: float
    fees: float = Field(ge=0)
    net_pnl: float


class SlippageStats(BaseModel):
    """Realized fill quality against what the simulation assumed."""

    expected_bps: float
    realized_bps: float


class LatencyPercentiles(BaseModel):
    """Round-trip latency distribution for the run (measured, never assumed)."""

    p50_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)
    p99_ms: float = Field(ge=0)


class PerformanceReport(BaseModel):
    """One strategy evaluation, self-describing enough to be trusted alone."""

    run_id: str
    mode: Mode  # required, no default — see module docstring
    venue: str
    symbol: str
    data_start_ns: int
    data_end_ns: int
    cost: CostAssumption
    equity_curve: list[EquityPoint]
    drawdown: list[DrawdownPoint]
    trades: list[TradeRecord]
    # Expectancy per trade net of fees is the primary number; hit rate is a
    # secondary diagnostic (high hit rate with skewed losses still loses).
    expectancy_bps_net: float
    hit_rate: float | None = Field(default=None, ge=0, le=1)
    slippage: SlippageStats
    latency: LatencyPercentiles
