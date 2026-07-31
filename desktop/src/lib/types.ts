/** TypeScript mirrors of every payload the Rust backend and Python services emit. */

export type ProcKind = "recorder" | "telemetry";

export interface ProcessStatus {
  kind: ProcKind;
  running: boolean;
  pid: number | null;
  uptime_s: number | null;
}

export interface RawDate {
  date: string;
  hours: number;
  bytes: number;
}

export interface VenueRaw {
  venue: string;
  total_bytes: number;
  gap_events: number;
  dates: RawDate[];
}

export interface ProcessedPartition {
  dataset: string;
  venue: string;
  symbol: string | null;
  date: string;
  files: number;
  bytes: number;
}

export interface Inventory {
  raw: VenueRaw[];
  processed: ProcessedPartition[];
  raw_total_bytes: number;
  processed_total_bytes: number;
}

export interface TelemetrySample {
  ts_ns: number;
  rtt_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  ok: boolean;
}

export interface TelemetryVenue {
  last_ms: number;
  ok: boolean;
  error: string | null;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  samples: number;
  history: TelemetrySample[];
}

export interface TelemetryLatest {
  generated_at: string;
  venues: Record<string, TelemetryVenue>;
}

export interface ArrivalStats {
  bounds_ms: number[];
  counts: number[];
  count: number;
  max_ms: number;
  p50_ms: number;
  p90_ms: number;
  p99_ms: number;
}

/**
 * Which integrity mechanism scored a venue-day. Kraken WS v2 has no sequence
 * numbers and Coinbase provides no checksums, so a `null` count means "this
 * feed provides none" and must render as n/a — never as zero, which would read
 * as a clean check that never ran.
 */
export interface IntegrityReport {
  mechanism: string;
  sequence_checks: number | null;
  checksum_checks: number | null;
}

export interface SymbolReport {
  symbol: string;
  events_applied: number;
  snapshots: number;
  /** null when the venue's feed carries no sequence numbers. */
  seq_gaps: number | null;
  seq_gaps_unexplained: number | null;
  /** null when the venue's feed carries no book checksums. */
  checksum_failures: number | null;
  checksum_failures_unexplained: number | null;
  checksums_verified: number | null;
  crossed_total: number;
  crossed_unexplained: number;
  locked_total: number;
  valid_coverage_day_pct: number;
  valid_coverage_excl_gaps_pct: number;
  snapshot_compares: number;
  snapshot_mismatches: number;
  rows_written: number;
  last_mid: number | null;
  last_spread: number | null;
  last_bid_levels: number;
  last_ask_levels: number;
}

export interface DayReport {
  venue: string;
  date: string;
  msgs_total: number;
  channel_counts: Record<string, number>;
  first_ns: number | null;
  last_ns: number | null;
  feed_gaps: number;
  /** Unioned gap time intersected with the recorded span — never full window durations. */
  feed_gap_ms: number;
  gaps_partially_outside_span: number;
  gap_ms_clipped_outside_span: number;
  gaps_outside_span: number;
  gap_ms_outside_span: number;
  arrival: ArrivalStats;
  integrity: IntegrityReport;
  symbols: SymbolReport[];
  passed: boolean;
  failure_reasons: string[];
}

export interface ValidationSummary {
  generated_at: string;
  runs: DayReport[];
}

export interface Settings {
  repo_root: string | null;
  record_kraken: boolean;
  record_coinbase: boolean;
}

export interface RepoInfo {
  repo_root: string;
  logs_dir: string;
  data_dir: string;
}

/** One heartbeat log line from the recorder, plus when we saw it. */
export interface VenueHeartbeat {
  venue: string;
  connected: boolean;
  msgs_total: number;
  msgs_per_s: number;
  raw_bytes_total: number;
  bytes_on_disk_hour: number;
  last_seq: number | null;
  seen_at_ms: number;
}

export interface LogEntry {
  id: number;
  source: "recorder" | "telemetry";
  time: string;
  level: string;
  event: string;
  detail: string;
  raw: string;
}
