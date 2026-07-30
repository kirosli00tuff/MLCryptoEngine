/** Phase A progress and last-validated book state — every number here comes
 * from `make validate` output (validation_summary.json) or the inventory scan;
 * nothing is projected or fabricated.
 */

import { useMemo } from "react";

import { fmtBytes, fmtMs, fmtNum } from "../lib/format";
import { useAppData } from "../state/AppData";

const REQUIREMENTS = [
  { venue: "kraken", label: "Kraken: one full day passes validation" },
  { venue: "coinbase", label: "Coinbase: one full day passes validation" },
] as const;

export default function PhaseProgressPanel() {
  const { validation, inventory } = useAppData();

  const runs = useMemo(() => validation?.runs ?? [], [validation]);
  const validatedDays = new Set(runs.map((r) => `${r.venue}|${r.date}`)).size;
  const passedVenues = new Set(runs.filter((r) => r.passed).map((r) => r.venue));
  const met = REQUIREMENTS.filter((r) => passedVenues.has(r.venue)).length;

  // Latest run per venue, for book state and arrival stats.
  const latestByVenue = useMemo(() => {
    const map = new Map<string, (typeof runs)[number]>();
    for (const run of runs) {
      const existing = map.get(run.venue);
      if (!existing || run.date >= existing.date) map.set(run.venue, run);
    }
    return [...map.values()].sort((a, b) => a.venue.localeCompare(b.venue));
  }, [runs]);

  return (
    <section className="panel flex flex-col p-4" aria-label="Phase progress and book state">
      <div className="flex items-center justify-between">
        <span className="panel-title">Phase A → B</span>
        <span className="num text-[10px] text-ink-dim">
          {met}/{REQUIREMENTS.length}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel2">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cortex to-bid transition-all duration-700"
          style={{ width: `${(met / REQUIREMENTS.length) * 100}%` }}
        />
      </div>
      <ul className="mt-3 space-y-1.5">
        {REQUIREMENTS.map((req) => {
          const done = passedVenues.has(req.venue);
          return (
            <li key={req.venue} className="flex items-start gap-2 text-[10.5px]">
              <span
                className={`mt-0.5 flex h-3 w-3 shrink-0 items-center justify-center rounded-full border text-[8px] ${
                  done ? "border-bid bg-bid/20 text-bid" : "border-hairline text-transparent"
                }`}
              >
                ✓
              </span>
              <span className={done ? "text-ink" : "text-ink-dim"}>{req.label}</span>
            </li>
          );
        })}
      </ul>

      <div className="num mt-3 flex justify-between border-t border-hairline pt-2.5 text-[10.5px]">
        <span className="text-ink-faint">validated venue-days</span>
        <span className="text-ink-dim">{fmtNum(validatedDays)}</span>
      </div>
      <div className="num flex justify-between pt-1 text-[10.5px]">
        <span className="text-ink-faint">raw data on disk</span>
        <span className="text-ink-dim">
          {inventory ? fmtBytes(inventory.raw_total_bytes) : "—"}
        </span>
      </div>

      {latestByVenue.length > 0 ? (
        <div className="mt-3 border-t border-hairline pt-2.5">
          <span className="panel-title">Book state — as of last validation</span>
          <div className="mt-2 space-y-2">
            {latestByVenue.map((run) => (
              <div key={run.venue}>
                <div className="text-[10px] capitalize text-ink-dim">
                  {run.venue} · {run.date} · arrival p50 {fmtMs(run.arrival.p50_ms)} / p99{" "}
                  {fmtMs(run.arrival.p99_ms)}
                </div>
                {run.symbols.map((s) => (
                  <div
                    key={s.symbol}
                    className="num mt-1 flex items-center justify-between text-[10.5px]"
                  >
                    <span className="text-ink">{s.symbol}</span>
                    <span className="text-ink-dim">
                      {s.last_mid !== null ? `mid ${fmtNum(s.last_mid)}` : "book not valid"}
                      {s.last_spread !== null ? ` · spr ${s.last_spread}` : ""}
                      {s.last_bid_levels > 0
                        ? ` · ${s.last_bid_levels}b/${s.last_ask_levels}a`
                        : ""}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="mt-3 border-t border-hairline pt-2.5 text-[10px] leading-snug text-ink-faint">
          No validation runs yet. Record data, then `make validate` fills this panel.
        </p>
      )}

      <p className="mt-auto border-t border-hairline pt-2.5 text-[9.5px] leading-snug text-ink-faint">
        Phase A is accepted only when full recorded days reconstruct with zero
        unexplained crossed books.
      </p>
    </section>
  );
}
