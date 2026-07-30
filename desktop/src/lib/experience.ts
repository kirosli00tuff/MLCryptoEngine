/** Experience model behind the cortex visualization.
 *
 * The net grows from real, on-disk evidence only: raw bytes recorded,
 * validated days, days that passed Phase A criteria, and latency samples.
 * No data → a small seed net. Every unit here is observable in the repo.
 */

import type { Inventory, TelemetryLatest, ValidationSummary } from "./types";

export type CortexStage = "seed" | "forming" | "connecting" | "patterning" | "deep";

export interface Experience {
  points: number;
  rawMB: number;
  validatedDays: number;
  passedDays: number;
  telemetrySamples: number;
  nodeTarget: number;
  stage: CortexStage;
}

const MIN_NODES = 6;
const MAX_NODES = 140;

export function computeExperience(
  inventory: Inventory | null,
  validation: ValidationSummary | null,
  telemetry: TelemetryLatest | null,
): Experience {
  const rawMB = inventory ? inventory.raw_total_bytes / 1_000_000 : 0;

  const runs = validation?.runs ?? [];
  const validatedKeys = new Set(runs.map((run) => `${run.venue}|${run.date}`));
  const passedKeys = new Set(
    runs.filter((run) => run.passed).map((run) => `${run.venue}|${run.date}`),
  );

  const telemetrySamples = telemetry
    ? Object.values(telemetry.venues).reduce((sum, v) => sum + v.samples, 0)
    : 0;

  const points =
    rawMB + validatedKeys.size * 40 + passedKeys.size * 120 + telemetrySamples / 50;

  const nodeTarget = Math.max(
    MIN_NODES,
    Math.min(MAX_NODES, MIN_NODES + Math.floor(Math.pow(points, 0.45))),
  );

  let stage: CortexStage = "seed";
  if (points >= 1000) stage = "deep";
  else if (points >= 250) stage = "patterning";
  else if (points >= 50) stage = "connecting";
  else if (points >= 5) stage = "forming";

  return {
    points: Math.round(points),
    rawMB,
    validatedDays: validatedKeys.size,
    passedDays: passedKeys.size,
    telemetrySamples,
    nodeTarget,
    stage,
  };
}
