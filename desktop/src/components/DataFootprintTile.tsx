import { fmtBytes, fmtNum } from "../lib/format";
import { useAppData } from "../state/AppData";
import EmptyState from "./EmptyState";
import { DatabaseIcon } from "./icons";

export default function DataFootprintTile() {
  const { inventory } = useAppData();

  const hasData = inventory !== null && inventory.raw.length > 0;
  const recordedDays = hasData
    ? new Set(inventory.raw.flatMap((v) => v.dates.map((d) => d.date))).size
    : 0;
  const gapEvents = hasData ? inventory.raw.reduce((sum, v) => sum + v.gap_events, 0) : 0;

  return (
    <section className="panel flex flex-col gap-3 p-4" aria-label="Dataset footprint">
      <span className="panel-title">Dataset</span>
      {!hasData ? (
        <EmptyState
          icon={<DatabaseIcon className="h-5 w-5" />}
          title="Nothing recorded yet"
          hint="Start the recorder to begin capturing raw order book and trade feeds."
        />
      ) : (
        <div className="grid grid-cols-2 gap-2.5">
          <div className="rounded-md bg-panel2/70 p-2.5">
            <div className="num text-lg font-semibold leading-none text-ink">
              {fmtBytes(inventory.raw_total_bytes)}
            </div>
            <div className="mt-1 text-[10px] text-ink-dim">raw (immutable)</div>
          </div>
          <div className="rounded-md bg-panel2/70 p-2.5">
            <div className="num text-lg font-semibold leading-none text-ink">
              {fmtBytes(inventory.processed_total_bytes)}
            </div>
            <div className="mt-1 text-[10px] text-ink-dim">processed</div>
          </div>
          <div className="rounded-md bg-panel2/70 p-2.5">
            <div className="num text-lg font-semibold leading-none text-ink">
              {fmtNum(recordedDays)}
            </div>
            <div className="mt-1 text-[10px] text-ink-dim">
              recorded {recordedDays === 1 ? "day" : "days"}
            </div>
          </div>
          <div className="rounded-md bg-panel2/70 p-2.5">
            <div
              className={`num text-lg font-semibold leading-none ${
                gapEvents > 0 ? "text-amberx" : "text-ink"
              }`}
            >
              {fmtNum(gapEvents)}
            </div>
            <div className="mt-1 text-[10px] text-ink-dim">logged gaps</div>
          </div>
        </div>
      )}
    </section>
  );
}
