import { fmtBytes, fmtNum } from "../lib/format";
import { useAppData } from "../state/AppData";
import Sparkline from "./Sparkline";

const STALE_AFTER_MS = 30_000;

interface VenueStatusCardProps {
  venue: string;
  displayName: string;
}

type FeedState = "live" | "reconnecting" | "stale" | "offline";

export default function VenueStatusCard({ venue, displayName }: VenueStatusCardProps) {
  const { heartbeats, sparklines, inventory, status } = useAppData();
  const beat = heartbeats[venue] ?? null;
  const recorderRunning = status?.find((s) => s.kind === "recorder")?.running ?? false;
  const raw = inventory?.raw.find((v) => v.venue === venue) ?? null;

  let state: FeedState = "offline";
  if (beat) {
    const fresh = Date.now() - beat.seen_at_ms < STALE_AFTER_MS;
    if (fresh && beat.connected) state = "live";
    else if (fresh) state = "reconnecting";
    else state = recorderRunning ? "stale" : "offline";
  } else if (recorderRunning) {
    state = "stale";
  }

  const stateStyle: Record<FeedState, { dot: string; label: string; text: string }> = {
    live: { dot: "bg-bid shadow-[0_0_6px_var(--color-bid)]", label: "live", text: "text-bid" },
    reconnecting: { dot: "bg-amberx animate-pulse", label: "reconnecting", text: "text-amberx" },
    stale: { dot: "bg-amberx", label: "waiting for heartbeat", text: "text-amberx" },
    offline: { dot: "bg-ink-faint", label: "offline", text: "text-ink-faint" },
  };
  const s = stateStyle[state];

  return (
    <section className="panel flex flex-col gap-3 p-4" aria-label={`${displayName} recorder status`}>
      <div className="flex items-center justify-between">
        <span className="panel-title">{displayName}</span>
        <span className={`flex items-center gap-1.5 text-[10px] ${s.text}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
          {s.label}
        </span>
      </div>

      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="num text-2xl font-semibold leading-none text-ink">
            {beat ? fmtNum(beat.msgs_per_s) : "—"}
          </div>
          <div className="mt-1 text-[10px] text-ink-dim">msgs / sec</div>
        </div>
        <Sparkline
          values={sparklines[venue] ?? []}
          width={110}
          height={30}
          stroke={state === "live" ? "var(--color-bid)" : "var(--color-ink-faint)"}
        />
      </div>

      <dl className="num grid grid-cols-2 gap-x-3 gap-y-1 border-t border-hairline pt-2.5 text-[10.5px]">
        <div className="flex justify-between">
          <dt className="text-ink-faint">total msgs</dt>
          <dd className="text-ink-dim">{beat ? fmtNum(beat.msgs_total) : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-faint">this hour</dt>
          <dd className="text-ink-dim">{beat ? fmtBytes(beat.bytes_on_disk_hour) : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-faint">on disk</dt>
          <dd className="text-ink-dim">{raw ? fmtBytes(raw.total_bytes) : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-faint">feed gaps</dt>
          <dd className={raw && raw.gap_events > 0 ? "text-amberx" : "text-ink-dim"}>
            {raw ? fmtNum(raw.gap_events) : "—"}
          </dd>
        </div>
      </dl>
    </section>
  );
}
