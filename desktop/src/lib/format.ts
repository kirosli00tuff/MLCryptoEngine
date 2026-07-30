/** Formatting helpers shared by every panel. All output is display-only. */

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"];

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return "—";
  if (bytes === 0) return "0 B";
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${BYTE_UNITS[unit]}`;
}

export function fmtNum(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 10_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toLocaleString("en-US");
}

export function fmtMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value >= 100 ? `${value.toFixed(0)}ms` : `${value.toFixed(1)}ms`;
}

export function fmtUptime(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function fmtUtcClock(date: Date): string {
  return date.toISOString().slice(11, 19);
}

export function fmtPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(value >= 99.995 ? 0 : 2)}%`;
}

/** "14:03:22" from an ISO timestamp, UTC. */
export function fmtLogTime(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso.slice(11, 19) || iso;
  return new Date(t).toISOString().slice(11, 19);
}
