import { fmtMs } from "../lib/format";
import { useAppData } from "../state/AppData";
import EmptyState from "./EmptyState";
import { ActivityIcon } from "./icons";

function PercentileChip({ label, value }: { label: string; value: number }) {
  return (
    <span className="num rounded bg-panel2 px-1.5 py-0.5 text-[10px] text-ink-dim">
      {label} <span className="text-ink">{fmtMs(value)}</span>
    </span>
  );
}

export default function LatencyNowTile() {
  const { telemetry } = useAppData();
  const venues = telemetry ? Object.entries(telemetry.venues) : [];

  return (
    <section className="panel flex flex-col gap-3 p-4" aria-label="Current venue latency">
      <span className="panel-title">Latency now</span>
      {venues.length === 0 ? (
        <EmptyState
          icon={<ActivityIcon className="h-5 w-5" />}
          title="No latency samples yet"
          hint="Start telemetry to measure round trips to each venue's public endpoint."
        />
      ) : (
        <div className="flex flex-col gap-2.5">
          {venues.map(([venue, v]) => (
            <div key={venue} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-[11.5px] capitalize text-ink">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${v.ok ? "bg-bid" : "bg-ask"}`}
                  title={v.ok ? "last probe ok" : (v.error ?? "last probe failed")}
                />
                {venue}
              </span>
              <div className="flex gap-1">
                <PercentileChip label="p50" value={v.p50_ms} />
                <PercentileChip label="p95" value={v.p95_ms} />
                <PercentileChip label="p99" value={v.p99_ms} />
              </div>
            </div>
          ))}
          <div className="border-t border-hairline pt-2 text-[10px] leading-snug text-ink-faint">
            Rolling window over the venue's public REST endpoint. Backtests consume the
            full measured distribution, never a constant.
          </div>
        </div>
      )}
    </section>
  );
}
