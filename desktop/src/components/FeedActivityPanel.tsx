/** Feed activity: a live picture of what the pipeline is ingesting right now.
 *
 * Everything drawn here derives from real, current quantities: per-venue
 * message throughput from recorder heartbeats (node population and pulse
 * rate), connection state (hub color), and bytes flowing to disk. No learning
 * is implied because none is happening yet.
 *
 * Phase B destination: this panel becomes the model instrument — streaming
 * feature values, order flow imbalance as a signed waveform, the model output
 * distribution, and feature importance drift across retrains. Until that
 * exists, this shows feed activity and says so.
 */

import { useEffect, useMemo, useRef } from "react";

import { fmtBytes, fmtNum } from "../lib/format";
import type { VenueHeartbeat } from "../lib/types";
import { useAppData } from "../state/AppData";

const GOLDEN_ANGLE = 2.399963229728653;
const STALE_AFTER_MS = 30_000;
const PULSE_DURATION_MS = 700;
const MAX_PULSES = 24;
const NODE_EASE_MS = 250;

const VENUES: { key: string; label: string; hub: [number, number]; color: string }[] = [
  { key: "kraken", label: "Kraken", hub: [0.28, 0.5], color: "#9a8cff" },
  { key: "coinbase", label: "Coinbase", hub: [0.72, 0.5], color: "#2dd4a7" },
];

const IDLE_COLOR = "#454e5d";

interface Pulse {
  venue: number;
  node: number;
  startMs: number;
}

interface LiveVenue {
  rate: number;
  connected: boolean;
  fresh: boolean;
}

function liveState(beat: VenueHeartbeat | undefined): LiveVenue {
  if (!beat) return { rate: 0, connected: false, fresh: false };
  const fresh = Date.now() - beat.seen_at_ms < STALE_AFTER_MS;
  return { rate: fresh ? beat.msgs_per_s : 0, connected: fresh && beat.connected, fresh };
}

/** Node population for a venue: 0 when silent, log-scaled with throughput. */
function nodeTarget(rate: number): number {
  if (rate <= 0) return 0;
  return Math.min(26, 4 + Math.round(8 * Math.log10(1 + rate)));
}

function nodePosition(
  hub: [number, number],
  index: number,
  tMs: number,
  drift: boolean,
): [number, number] {
  const angle = index * GOLDEN_ANGLE + (drift ? Math.sin(tMs / 1400 + index * 1.7) * 0.06 : 0);
  const radius = 0.09 + 0.14 * Math.sqrt((index + 1) / 26);
  return [hub[0] + radius * Math.cos(angle) * 0.85, hub[1] + radius * Math.sin(angle) * 1.25];
}

export default function FeedActivityPanel() {
  const { heartbeats } = useAppData();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const liveRef = useRef<LiveVenue[]>(VENUES.map(() => liveState(undefined)));
  const shownNodesRef = useRef<number[]>(VENUES.map(() => 0));
  const pulsesRef = useRef<Pulse[]>([]);
  const lastPulseRef = useRef<number[]>(VENUES.map(() => 0));
  const lastEaseRef = useRef(0);

  const live = useMemo(
    () => VENUES.map((venue) => liveState(heartbeats[venue.key])),
    [heartbeats],
  );
  liveRef.current = live;
  const totalRate = live.reduce((sum, v) => sum + v.rate, 0);
  const anyLive = live.some((v) => v.connected);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let disposed = false;
    let raf = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(container.clientWidth * dpr));
      canvas.height = Math.max(1, Math.floor(container.clientHeight * dpr));
      canvas.style.width = `${container.clientWidth}px`;
      canvas.style.height = `${container.clientHeight}px`;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    const drawFrame = (nowMs: number) => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      const states = liveRef.current;

      VENUES.forEach((venue, vi) => {
        const state = states[vi] ?? { rate: 0, connected: false, fresh: false };
        const color = state.connected ? venue.color : IDLE_COLOR;
        const shown = shownNodesRef.current[vi] ?? 0;
        const hubX = venue.hub[0] * w;
        const hubY = venue.hub[1] * h;

        // Edges hub -> nodes.
        ctx.lineWidth = Math.max(1, dpr * 0.7);
        ctx.strokeStyle = state.connected ? `${venue.color}26` : "#454e5d20";
        ctx.beginPath();
        for (let i = 0; i < shown; i += 1) {
          const [nx, ny] = nodePosition(venue.hub, i, nowMs, !reduceMotion);
          ctx.moveTo(hubX, hubY);
          ctx.lineTo(nx * w, ny * h);
        }
        ctx.stroke();

        // Activity nodes.
        for (let i = 0; i < shown; i += 1) {
          const [nx, ny] = nodePosition(venue.hub, i, nowMs, !reduceMotion);
          ctx.beginPath();
          ctx.fillStyle = color;
          ctx.globalAlpha = 0.85;
          ctx.shadowColor = color;
          ctx.shadowBlur = dpr * 4;
          ctx.arc(nx * w, ny * h, dpr * 1.9, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
          ctx.globalAlpha = 1;
        }

        // Hub last, on top: ring colored by connection state.
        ctx.beginPath();
        ctx.fillStyle = "#10141d";
        ctx.strokeStyle = state.connected ? venue.color : state.fresh ? "#f0b45b" : IDLE_COLOR;
        ctx.lineWidth = dpr * 1.6;
        ctx.shadowColor = ctx.strokeStyle;
        ctx.shadowBlur = state.connected ? dpr * 10 : 0;
        ctx.arc(hubX, hubY, dpr * 7, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.shadowBlur = 0;
      });

      // Message pulses: one dot per spawn travelling hub -> node.
      if (!reduceMotion) {
        pulsesRef.current = pulsesRef.current.filter(
          (pulse) => nowMs - pulse.startMs < PULSE_DURATION_MS,
        );
        for (const pulse of pulsesRef.current) {
          const venue = VENUES[pulse.venue];
          if (!venue) continue;
          const shown = shownNodesRef.current[pulse.venue] ?? 0;
          if (pulse.node >= shown) continue;
          const t = (nowMs - pulse.startMs) / PULSE_DURATION_MS;
          const [nx, ny] = nodePosition(venue.hub, pulse.node, nowMs, true);
          const x = venue.hub[0] * w + (nx * w - venue.hub[0] * w) * t;
          const y = venue.hub[1] * h + (ny * h - venue.hub[1] * h) * t;
          ctx.beginPath();
          ctx.fillStyle = `rgba(220, 215, 255, ${(1 - t) * 0.9})`;
          ctx.arc(x, y, dpr * 1.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };

    const step = (nowMs: number) => {
      if (disposed) return;
      // Ease node populations toward their live targets.
      if (nowMs - lastEaseRef.current > NODE_EASE_MS) {
        lastEaseRef.current = nowMs;
        liveRef.current.forEach((state, vi) => {
          const target = nodeTarget(state.rate);
          const shown = shownNodesRef.current[vi] ?? 0;
          if (shown < target) shownNodesRef.current[vi] = shown + 1;
          else if (shown > target) shownNodesRef.current[vi] = shown - 1;
        });
      }
      // Spawn pulses at a rate proportional to live throughput.
      if (!reduceMotion) {
        liveRef.current.forEach((state, vi) => {
          const shown = shownNodesRef.current[vi] ?? 0;
          if (state.rate <= 0 || shown === 0) return;
          const intervalMs = Math.min(1500, Math.max(45, 1000 / state.rate));
          if (
            nowMs - (lastPulseRef.current[vi] ?? 0) >= intervalMs &&
            pulsesRef.current.length < MAX_PULSES
          ) {
            lastPulseRef.current[vi] = nowMs;
            pulsesRef.current.push({
              venue: vi,
              node: Math.floor(Math.random() * shown),
              startMs: nowMs,
            });
          }
        });
      }
      drawFrame(nowMs);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, []);

  return (
    <section className="panel relative overflow-hidden" aria-label="Feed activity">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between p-4">
        <div>
          <span className="panel-title">Feed activity</span>
          <div className="mt-1 text-[10px] text-ink-faint">
            live from recorder heartbeats
          </div>
        </div>
        <span
          className={`num rounded-full border px-2 py-0.5 text-[9.5px] tracking-wider ${
            anyLive
              ? "border-bid/30 bg-bid/10 text-bid"
              : "border-hairline bg-panel2 text-ink-faint"
          }`}
        >
          {anyLive ? "LIVE" : "IDLE"}
        </span>
      </div>

      <div ref={containerRef} className="h-[340px] w-full">
        <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-end justify-between p-4">
        <div className="num text-[10.5px] text-ink-dim">
          {VENUES.map((venue, vi) => {
            const state = live[vi] ?? { rate: 0, connected: false, fresh: false };
            const beat = heartbeats[venue.key];
            return (
              <span key={venue.key} className="mr-4">
                <span style={{ color: state.connected ? venue.color : undefined }}>
                  {venue.label}
                </span>{" "}
                <span className="text-ink">{fmtNum(state.rate)}</span>/s
                {beat ? (
                  <span className="text-ink-faint">
                    {" "}
                    · {fmtBytes(beat.bytes_on_disk_hour)} this hour
                  </span>
                ) : null}
              </span>
            );
          })}
          <span>
            Σ <span className="text-ink">{fmtNum(totalRate)}</span>/s
          </span>
        </div>
        <div className="max-w-[280px] text-right text-[9.5px] leading-snug text-ink-faint">
          Node count and pulse rate track live message throughput. In Phase B this
          panel becomes the model instrument.
        </div>
      </div>
    </section>
  );
}
