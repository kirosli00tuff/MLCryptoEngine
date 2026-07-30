import { useEffect, useMemo, useRef, useState } from "react";

import { fmtLogTime } from "../lib/format";
import { useAppData } from "../state/AppData";
import EmptyState from "./EmptyState";
import { ActivityIcon } from "./icons";

type SourceFilter = "all" | "recorder" | "telemetry";
type LevelFilter = "all" | "info" | "warning" | "error";

const LEVEL_STYLES: Record<string, string> = {
  info: "text-ink-faint",
  warning: "text-amberx",
  error: "text-ask",
  critical: "text-ask",
};

export default function LogStream() {
  const { logs } = useAppData();
  const [source, setSource] = useState<SourceFilter>("all");
  const [level, setLevel] = useState<LevelFilter>("all");
  const [query, setQuery] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return logs.filter((entry) => {
      if (source !== "all" && entry.source !== source) return false;
      if (level !== "all" && entry.level !== level) return false;
      if (q && !entry.raw.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [logs, source, level, query]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && autoScroll) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered, autoScroll]);

  const selectClass =
    "rounded border border-hairline bg-panel2 px-1.5 py-1 text-[10.5px] text-ink-dim focus:text-ink";

  return (
    <section className="panel flex h-72 flex-col" aria-label="Live log stream">
      <div className="flex items-center gap-2 border-b border-hairline px-4 py-2.5">
        <span className="panel-title mr-auto">Log stream</span>
        <select
          aria-label="Filter by source"
          value={source}
          onChange={(e) => setSource(e.target.value as SourceFilter)}
          className={selectClass}
        >
          <option value="all">all sources</option>
          <option value="recorder">recorder</option>
          <option value="telemetry">telemetry</option>
        </select>
        <select
          aria-label="Filter by level"
          value={level}
          onChange={(e) => setLevel(e.target.value as LevelFilter)}
          className={selectClass}
        >
          <option value="all">all levels</option>
          <option value="info">info</option>
          <option value="warning">warning</option>
          <option value="error">error</option>
        </select>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter text…"
          aria-label="Filter log text"
          className="w-40 rounded border border-hairline bg-panel2 px-2 py-1 text-[10.5px] text-ink placeholder:text-ink-faint"
        />
        <label className="flex cursor-pointer items-center gap-1.5 text-[10px] text-ink-dim">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-[var(--color-cortex)]"
          />
          follow
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className="flex-1 p-4">
          <EmptyState
            icon={<ActivityIcon className="h-5 w-5" />}
            title={logs.length === 0 ? "No log lines yet" : "Nothing matches the filter"}
            hint={
              logs.length === 0
                ? "Structured logs stream here live once the recorder or telemetry is running."
                : "Loosen the source, level, or text filter to see more."
            }
          />
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="num min-h-0 flex-1 select-text overflow-y-auto px-4 py-2 text-[10.5px] leading-[1.7]"
        >
          {filtered.map((entry) => (
            <div key={entry.id} className="flex gap-2 whitespace-nowrap">
              <span className="shrink-0 text-ink-faint">{fmtLogTime(entry.time)}</span>
              <span className={`w-14 shrink-0 ${LEVEL_STYLES[entry.level] ?? "text-ink-faint"}`}>
                {entry.level}
              </span>
              <span
                className={`w-16 shrink-0 ${
                  entry.source === "recorder" ? "text-cortex/80" : "text-bid/80"
                }`}
              >
                {entry.source}
              </span>
              <span className="shrink-0 font-medium text-ink">{entry.event}</span>
              <span className="truncate text-ink-dim" title={entry.detail}>
                {entry.detail}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
