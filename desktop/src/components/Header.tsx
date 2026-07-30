import { useEffect, useState } from "react";

import { fmtUptime, fmtUtcClock } from "../lib/format";
import type { ProcKind } from "../lib/types";
import { useAppData } from "../state/AppData";
import { PlayIcon, StopIcon } from "./icons";
import type { Page } from "./Sidebar";

const PAGE_TITLES: Record<Page, string> = {
  dashboard: "Dashboard",
  settings: "Settings",
};

function ProcessControl({ kind, label }: { kind: ProcKind; label: string }) {
  const { status, pending, startProcess, stopProcess, inTauri } = useAppData();
  const entry = status?.find((s) => s.kind === kind) ?? null;
  const running = entry?.running ?? false;
  const busy = pending[kind] ?? false;

  return (
    <div className="flex items-center gap-2 rounded-md border border-hairline bg-panel px-2.5 py-1.5">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          running ? "bg-bid shadow-[0_0_6px_var(--color-bid)]" : "bg-ink-faint"
        }`}
        aria-hidden
      />
      <div className="leading-none">
        <div className="text-[11px] text-ink">{label}</div>
        <div className="num mt-0.5 text-[9px] text-ink-dim">
          {running ? `up ${fmtUptime(entry?.uptime_s)}` : "stopped"}
        </div>
      </div>
      <button
        type="button"
        disabled={busy || !inTauri}
        onClick={() => (running ? void stopProcess(kind) : void startProcess(kind))}
        className={`ml-1 flex items-center gap-1 rounded px-2 py-1 text-[10.5px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
          running
            ? "text-ask hover:bg-ask/10"
            : "text-bid hover:bg-bid/10"
        }`}
      >
        {busy ? (
          <span className="h-3 w-3 animate-spin rounded-full border border-ink-dim border-t-transparent" />
        ) : running ? (
          <StopIcon />
        ) : (
          <PlayIcon />
        )}
        {running ? "Stop" : "Start"}
      </button>
    </div>
  );
}

export default function Header({ page }: { page: Page }) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-hairline bg-void px-5">
      <div className="flex items-baseline gap-3">
        <h1 className="text-[15px] font-semibold text-ink">{PAGE_TITLES[page]}</h1>
        <span className="num text-[11px] text-ink-dim" title="Coordinated Universal Time">
          {fmtUtcClock(now)} UTC
        </span>
      </div>
      <div className="flex items-center gap-2">
        <ProcessControl kind="recorder" label="Recorder" />
        <ProcessControl kind="telemetry" label="Telemetry" />
      </div>
    </header>
  );
}
