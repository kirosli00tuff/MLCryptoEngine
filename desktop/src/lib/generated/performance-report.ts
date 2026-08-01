// GENERATED FILE — do not edit by hand.
// Source of truth: backtest/reporting/schema.py · regenerate with `make types`.

export type Mode = "backtest" | "paper" | "live";

export interface CostAssumption {
  mode: "maker" | "taker";
  fee_bps_per_leg: number;
  includes_spread: boolean;
}

export interface EquityPoint {
  ts_ns: number;
  gross: number;
  net: number;
}

export interface DrawdownPoint {
  ts_ns: number;
  drawdown_pct: number;
}

export interface TradeRecord {
  entry_ns: number;
  exit_ns: number;
  side: "long" | "short";
  size: number;
  gross_pnl: number;
  fees: number;
  net_pnl: number;
}

export interface SlippageStats {
  expected_bps: number;
  realized_bps: number;
}

export interface LatencyPercentiles {
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

export interface PerformanceReport {
  run_id: string;
  mode: Mode;
  venue: string;
  symbol: string;
  data_start_ns: number;
  data_end_ns: number;
  cost: CostAssumption;
  equity_curve: EquityPoint[];
  drawdown: DrawdownPoint[];
  trades: TradeRecord[];
  expectancy_bps_net: number;
  hit_rate: number | null;
  slippage: SlippageStats;
  latency: LatencyPercentiles;
}
