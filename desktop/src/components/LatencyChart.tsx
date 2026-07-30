import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useAppData } from "../state/AppData";
import EmptyState from "./EmptyState";
import { ActivityIcon } from "./icons";

const SERIES = [
  { dataKey: "p50", stroke: "var(--color-bid)", label: "p50" },
  { dataKey: "p95", stroke: "var(--color-amberx)", label: "p95" },
  { dataKey: "p99", stroke: "var(--color-ask)", label: "p99" },
] as const;

export default function LatencyChart() {
  const { telemetry } = useAppData();
  const venues = telemetry ? Object.keys(telemetry.venues) : [];
  const [selected, setSelected] = useState<string | null>(null);
  const venue = selected && venues.includes(selected) ? selected : (venues[0] ?? null);

  const data = useMemo(() => {
    if (!telemetry || !venue) return [];
    const entry = telemetry.venues[venue];
    if (!entry) return [];
    return entry.history.map((sample) => ({
      time: Math.floor(sample.ts_ns / 1e6),
      p50: sample.p50_ms,
      p95: sample.p95_ms,
      p99: sample.p99_ms,
    }));
  }, [telemetry, venue]);

  return (
    <section className="panel flex flex-col gap-3 p-4" aria-label="Latency percentiles over time">
      <div className="flex items-center justify-between">
        <span className="panel-title">Round-trip latency</span>
        <div className="flex gap-1">
          {venues.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setSelected(name)}
              className={`rounded px-2 py-0.5 text-[10px] capitalize transition-colors ${
                name === venue ? "bg-panel2 text-ink" : "text-ink-faint hover:text-ink-dim"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      {data.length < 2 ? (
        <EmptyState
          icon={<ActivityIcon className="h-5 w-5" />}
          title="Not enough samples for a chart"
          hint="Telemetry charts appear after a few probe cycles. Leave telemetry running alongside the recorder."
        />
      ) : (
        <>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -10 }}>
                <CartesianGrid
                  stroke="var(--color-hairline)"
                  strokeDasharray="3 3"
                  vertical={false}
                />
                <XAxis
                  dataKey="time"
                  tickFormatter={(t: number) => new Date(t).toISOString().slice(11, 16)}
                  tick={{ fill: "var(--color-ink-dim)", fontSize: 10 }}
                  tickLine={false}
                  axisLine={{ stroke: "var(--color-hairline)" }}
                  minTickGap={48}
                />
                <YAxis
                  unit="ms"
                  tick={{ fill: "var(--color-ink-dim)", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  width={56}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-panel2)",
                    border: "1px solid var(--color-hairline)",
                    borderRadius: 8,
                    fontSize: 11,
                  }}
                  labelStyle={{ color: "var(--color-ink-dim)" }}
                  labelFormatter={(t) => `${new Date(Number(t)).toISOString().slice(11, 19)} UTC`}
                  formatter={(value: number | string, name: string) => [
                    `${Number(value).toFixed(1)} ms`,
                    name,
                  ]}
                />
                {SERIES.map((series) => (
                  <Line
                    key={series.dataKey}
                    type="monotone"
                    dataKey={series.dataKey}
                    name={series.label}
                    stroke={series.stroke}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-3 text-[10px] text-ink-dim">
            {SERIES.map((series) => (
              <span key={series.dataKey} className="flex items-center gap-1.5">
                <span className="h-0.5 w-3 rounded" style={{ background: series.stroke }} />
                {series.label}
              </span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
