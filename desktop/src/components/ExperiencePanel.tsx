import { useMemo } from "react";

import { computeExperience } from "../lib/experience";
import { fmtBytes, fmtNum } from "../lib/format";
import { useAppData } from "../state/AppData";

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-[11px] text-ink-dim">{label}</span>
      <span className="num text-[12px] text-ink">{value}</span>
    </div>
  );
}

export default function ExperiencePanel() {
  const { inventory, validation, telemetry } = useAppData();
  const exp = useMemo(
    () => computeExperience(inventory, validation, telemetry),
    [inventory, validation, telemetry],
  );

  const passedVenues = useMemo(
    () => new Set((validation?.runs ?? []).filter((r) => r.passed).map((r) => r.venue)),
    [validation],
  );

  const requirements = [
    { venue: "kraken", label: "Kraken: one full day passes validation" },
    { venue: "coinbase", label: "Coinbase: one full day passes validation" },
  ];
  const met = requirements.filter((r) => passedVenues.has(r.venue)).length;
  const progressPct = (met / requirements.length) * 100;

  return (
    <section className="panel flex flex-col p-4" aria-label="Experience and phase progress">
      <span className="panel-title">Experience</span>

      <div className="mt-3">
        <div className="num text-3xl font-semibold leading-none text-cortex">
          {fmtNum(exp.points)}
        </div>
        <div className="mt-1 text-[10px] text-ink-dim">experience points</div>
      </div>

      <div className="mt-3 divide-y divide-hairline border-t border-hairline">
        <MetricRow label="Raw data recorded" value={fmtBytes(exp.rawMB * 1_000_000)} />
        <MetricRow
          label="Validated venue-days"
          value={`${fmtNum(exp.validatedDays)} (${fmtNum(exp.passedDays)} passed)`}
        />
        <MetricRow label="Latency samples" value={fmtNum(exp.telemetrySamples)} />
      </div>

      <div className="mt-auto pt-4">
        <div className="flex items-center justify-between">
          <span className="panel-title">Phase A → B</span>
          <span className="num text-[10px] text-ink-dim">
            {met}/{requirements.length}
          </span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel2">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cortex to-bid transition-all duration-700"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <ul className="mt-3 space-y-1.5">
          {requirements.map((req) => {
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
        <p className="mt-3 border-t border-hairline pt-2.5 text-[9.5px] leading-snug text-ink-faint">
          Phase A is accepted only when full recorded days reconstruct with zero
          unexplained crossed books. Run `make validate` after recording.
        </p>
      </div>
    </section>
  );
}
