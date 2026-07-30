/** The cortex: an abstract neural net that grows with recorded experience.
 *
 * Node count derives from real on-disk evidence (see lib/experience.ts).
 * Placement uses a golden-angle spiral with deterministic jitter, so the same
 * experience always produces the same net; motion is a gentle drift plus
 * synaptic pulses. Under prefers-reduced-motion the net renders as a still.
 */

import { useEffect, useMemo, useRef } from "react";

import { computeExperience } from "../lib/experience";
import { fmtNum } from "../lib/format";
import { useAppData } from "../state/AppData";

const GOLDEN_ANGLE = 2.399963229728653;
const GROW_EVERY_MS = 140;
const PULSE_EVERY_MS = 650;
const PULSE_DURATION_MS = 900;
const MAX_PULSES = 7;
const FADE_IN_MS = 900;

const COLORS = {
  cortex: "#9a8cff",
  bid: "#2dd4a7",
  ink: "#c9d1dd",
} as const;

const EDGE_COLOR = "rgba(154, 140, 255, 0.16)";

interface NetNode {
  bx: number;
  by: number;
  phase: number;
  speed: number;
  amp: number;
  bornMs: number;
  kind: keyof typeof COLORS;
  r: number;
  links: number[];
}

interface Pulse {
  from: number;
  to: number;
  startMs: number;
}

function makeNode(index: number, existing: NetNode[], nowMs: number): NetNode {
  const angle = index * GOLDEN_ANGLE + Math.sin(index * 12.9898) * 0.35;
  const radius = Math.min(
    0.46,
    Math.sqrt(index + 0.6) / 13.2 + (Math.sin(index * 78.233) + 1) * 0.015,
  );
  const bx = 0.5 + radius * Math.cos(angle) * 0.95;
  const by = 0.5 + radius * Math.sin(angle) * 0.82;
  const nearest = existing
    .map((node, i) => ({ i, d: (node.bx - bx) ** 2 + (node.by - by) ** 2 }))
    .sort((a, b) => a.d - b.d)
    .slice(0, Math.min(2, existing.length))
    .map((entry) => entry.i);
  const kind: keyof typeof COLORS =
    index % 7 === 3 ? "bid" : index % 11 === 5 ? "ink" : "cortex";
  return {
    bx,
    by,
    phase: index * 1.7,
    speed: 0.35 + ((index * 37) % 10) / 16,
    amp: 0.005 + ((index * 13) % 7) / 1100,
    bornMs: nowMs,
    kind,
    r: 1.7 + ((index * 29) % 10) / 4.5,
    links: nearest,
  };
}

export default function CortexPanel() {
  const { inventory, validation, telemetry } = useAppData();
  const exp = useMemo(
    () => computeExperience(inventory, validation, telemetry),
    [inventory, validation, telemetry],
  );

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const nodesRef = useRef<NetNode[]>([]);
  const pulsesRef = useRef<Pulse[]>([]);
  const targetRef = useRef(exp.nodeTarget);
  targetRef.current = exp.nodeTarget;

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let disposed = false;
    let raf = 0;
    let lastGrowMs = 0;
    let lastPulseMs = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const { clientWidth, clientHeight } = container;
      canvas.width = Math.max(1, Math.floor(clientWidth * dpr));
      canvas.height = Math.max(1, Math.floor(clientHeight * dpr));
      canvas.style.width = `${clientWidth}px`;
      canvas.style.height = `${clientHeight}px`;
    };

    const nodePosition = (node: NetNode, tMs: number, w: number, h: number) => {
      const drift = reduceMotion ? 0 : 1;
      const t = tMs / 1000;
      const x = (node.bx + drift * Math.sin(t * node.speed + node.phase) * node.amp) * w;
      const y = (node.by + drift * Math.cos(t * node.speed * 0.9 + node.phase) * node.amp) * h;
      return { x, y };
    };

    const drawFrame = (nowMs: number) => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      const nodes = nodesRef.current;
      const positions = nodes.map((node) => nodePosition(node, nowMs, w, h));

      // Edges under everything.
      ctx.lineWidth = Math.max(1, dpr * 0.8);
      ctx.strokeStyle = EDGE_COLOR;
      ctx.beginPath();
      nodes.forEach((node, i) => {
        for (const link of node.links) {
          const a = positions[i];
          const b = positions[link];
          if (!a || !b) continue;
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
        }
      });
      ctx.stroke();

      // Synaptic pulses.
      if (!reduceMotion) {
        pulsesRef.current = pulsesRef.current.filter(
          (pulse) => nowMs - pulse.startMs < PULSE_DURATION_MS,
        );
        for (const pulse of pulsesRef.current) {
          const a = positions[pulse.from];
          const b = positions[pulse.to];
          if (!a || !b) continue;
          const t = (nowMs - pulse.startMs) / PULSE_DURATION_MS;
          const x = a.x + (b.x - a.x) * t;
          const y = a.y + (b.y - a.y) * t;
          ctx.beginPath();
          ctx.fillStyle = `rgba(200, 190, 255, ${(1 - t) * 0.9})`;
          ctx.arc(x, y, dpr * 1.6, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Nodes with fade-in and a soft glow.
      nodes.forEach((node, i) => {
        const p = positions[i];
        if (!p) return;
        const age = nowMs - node.bornMs;
        const alpha = reduceMotion ? 1 : Math.min(1, age / FADE_IN_MS);
        ctx.beginPath();
        ctx.fillStyle = COLORS[node.kind];
        ctx.globalAlpha = alpha;
        ctx.shadowColor = COLORS[node.kind];
        ctx.shadowBlur = dpr * 6;
        ctx.arc(p.x, p.y, node.r * dpr, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.globalAlpha = 1;
      });
    };

    const observer = new ResizeObserver(() => {
      resize();
      if (reduceMotion) drawFrame(performance.now());
    });
    observer.observe(container);
    resize();

    const step = (nowMs: number) => {
      if (disposed) return;
      const target = targetRef.current;
      if (nodesRef.current.length < target && nowMs - lastGrowMs > GROW_EVERY_MS) {
        nodesRef.current = [
          ...nodesRef.current,
          makeNode(nodesRef.current.length, nodesRef.current, nowMs),
        ];
        lastGrowMs = nowMs;
      }
      if (
        !reduceMotion &&
        nodesRef.current.length > 2 &&
        nowMs - lastPulseMs > PULSE_EVERY_MS &&
        pulsesRef.current.length < MAX_PULSES
      ) {
        const from = Math.floor(Math.random() * nodesRef.current.length);
        const node = nodesRef.current[from];
        if (node && node.links.length > 0) {
          const to = node.links[Math.floor(Math.random() * node.links.length)];
          if (to !== undefined) {
            pulsesRef.current = [...pulsesRef.current, { from, to, startMs: nowMs }];
            lastPulseMs = nowMs;
          }
        }
      }
      drawFrame(nowMs);
      raf = requestAnimationFrame(step);
    };

    if (reduceMotion) {
      // Grow instantly and render a still.
      const now = performance.now();
      while (nodesRef.current.length < targetRef.current) {
        nodesRef.current = [
          ...nodesRef.current,
          makeNode(nodesRef.current.length, nodesRef.current, now),
        ];
      }
      drawFrame(now);
    } else {
      raf = requestAnimationFrame(step);
    }

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [exp.nodeTarget]);

  return (
    <section className="panel relative overflow-hidden" aria-label="Engine cortex">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between p-4">
        <div>
          <span className="panel-title">Cortex</span>
          <div className="mt-1 text-[10px] text-ink-faint">grows with recorded experience</div>
        </div>
        <span className="num rounded-full border border-cortex/30 bg-cortex/10 px-2 py-0.5 text-[9.5px] tracking-wider text-cortex">
          {exp.stage.toUpperCase()}
        </span>
      </div>

      <div ref={containerRef} className="h-[340px] w-full">
        <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-end justify-between p-4">
        <div className="num text-[10.5px] text-ink-dim">
          <span className="text-ink">{fmtNum(exp.nodeTarget)}</span> nodes ·{" "}
          <span className="text-ink">{fmtNum(exp.points)}</span> experience
        </div>
        <div className="max-w-[300px] text-right text-[9.5px] leading-snug text-ink-faint">
          Abstract view of accumulated data: bytes recorded, days validated, latency
          measured. The learning model itself arrives in Phase B.
        </div>
      </div>
    </section>
  );
}
