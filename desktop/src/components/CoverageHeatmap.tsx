import { useMemo } from "react";

import { fmtBytes } from "../lib/format";
import { useAppData } from "../state/AppData";
import EmptyState from "./EmptyState";
import { DatabaseIcon } from "./icons";

const DAYS_SHOWN = 56;

interface DayCell {
  date: string;
  recordedBytes: number;
  hours: number;
  coverage: number | null;
  passed: boolean | null;
}

function lastNDates(n: number): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i -= 1) {
    const d = new Date(now.getTime() - i * 86_400_000);
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

function cellStyle(cell: DayCell): { className: string; style?: React.CSSProperties } {
  if (cell.recordedBytes === 0 && cell.coverage === null) {
    return { className: "bg-panel2/70" };
  }
  if (cell.coverage === null) {
    // Recorded but not yet validated.
    return { className: "bg-amberx/35" };
  }
  if (cell.passed) {
    return { className: "bg-bid" };
  }
  const alpha = 0.18 + Math.min(1, cell.coverage / 100) * 0.62;
  return { className: "", style: { backgroundColor: `rgba(45, 212, 167, ${alpha})` } };
}

export default function CoverageHeatmap() {
  const { inventory, validation } = useAppData();

  const venues = useMemo(() => {
    const names = new Set<string>();
    for (const v of inventory?.raw ?? []) names.add(v.venue);
    for (const r of validation?.runs ?? []) names.add(r.venue);
    return [...names].sort();
  }, [inventory, validation]);

  const dates = useMemo(() => lastNDates(DAYS_SHOWN), []);

  const grid = useMemo(() => {
    const map = new Map<string, DayCell>();
    for (const venue of venues) {
      for (const date of dates) {
        map.set(`${venue}|${date}`, {
          date,
          recordedBytes: 0,
          hours: 0,
          coverage: null,
          passed: null,
        });
      }
    }
    for (const v of inventory?.raw ?? []) {
      for (const d of v.dates) {
        const cell = map.get(`${v.venue}|${d.date}`);
        if (cell) {
          cell.recordedBytes = d.bytes;
          cell.hours = d.hours;
        }
      }
    }
    for (const run of validation?.runs ?? []) {
      const cell = map.get(`${run.venue}|${run.date}`);
      if (cell) {
        const best = run.symbols.reduce(
          (max, s) => Math.max(max, s.valid_coverage_excl_gaps_pct),
          0,
        );
        cell.coverage = Math.max(cell.coverage ?? 0, best);
        cell.passed = (cell.passed ?? true) && run.passed;
      }
    }
    return map;
  }, [venues, dates, inventory, validation]);

  const monthTicks = useMemo(() => {
    const ticks: { index: number; label: string }[] = [];
    dates.forEach((date, index) => {
      if (date.endsWith("-01") || index === 0) {
        ticks.push({
          index,
          label: new Date(`${date}T00:00:00Z`).toLocaleString("en-US", {
            month: "short",
            timeZone: "UTC",
          }),
        });
      }
    });
    return ticks;
  }, [dates]);

  const hasAnything = venues.length > 0;

  return (
    <section className="panel flex flex-col gap-3 p-4" aria-label="Recording coverage calendar">
      <span className="panel-title">Coverage — last 8 weeks</span>

      {!hasAnything ? (
        <EmptyState
          icon={<DatabaseIcon className="h-5 w-5" />}
          title="No recorded days yet"
          hint="Each recorded day appears here; color deepens as validation confirms valid-book coverage."
        />
      ) : (
        <div className="flex flex-col gap-2 overflow-x-auto">
          {venues.map((venue) => (
            <div key={venue} className="flex items-center gap-2">
              <span className="w-16 shrink-0 text-[10.5px] capitalize text-ink-dim">{venue}</span>
              <div className="flex gap-[3px]">
                {dates.map((date) => {
                  const cell = grid.get(`${venue}|${date}`);
                  if (!cell) return null;
                  const { className, style } = cellStyle(cell);
                  const parts = [`${venue} ${date}`];
                  if (cell.recordedBytes > 0) {
                    parts.push(`${fmtBytes(cell.recordedBytes)} · ${cell.hours}h recorded`);
                  } else {
                    parts.push("not recorded");
                  }
                  if (cell.coverage !== null) {
                    parts.push(
                      `coverage ${cell.coverage.toFixed(1)}% · ${cell.passed ? "PASS" : "FAIL"}`,
                    );
                  }
                  return (
                    <div
                      key={date}
                      title={parts.join(" — ")}
                      className={`h-3 w-3 rounded-[2px] ${className}`}
                      style={style}
                    />
                  );
                })}
              </div>
            </div>
          ))}
          <div className="ml-[72px] flex gap-[3px]">
            {dates.map((date, index) => {
              const tick = monthTicks.find((t) => t.index === index);
              return (
                <div key={date} className="w-3 text-[8px] text-ink-faint">
                  {tick ? tick.label : ""}
                </div>
              );
            })}
          </div>
          <div className="mt-1 flex items-center gap-3 border-t border-hairline pt-2 text-[9.5px] text-ink-faint">
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-[2px] bg-panel2/70" /> none
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-[2px] bg-amberx/35" /> recorded
            </span>
            <span className="flex items-center gap-1">
              <span
                className="h-2.5 w-2.5 rounded-[2px]"
                style={{ backgroundColor: "rgba(45, 212, 167, 0.5)" }}
              />{" "}
              validated
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-[2px] bg-bid" /> passed
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
