/** Single data spine for the app.
 *
 * Everything on screen derives from real backend state: process status,
 * dataset inventory, telemetry/validation JSON files, live log events, and
 * recorder heartbeats parsed out of the structured log stream. When a source
 * has nothing yet, its value stays null and panels render designed empty
 * states — there is no mock data anywhere.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { call, callStrict, inTauri, onEvent } from "../lib/tauri";
import type {
  Inventory,
  LogEntry,
  ProcKind,
  ProcessStatus,
  RepoInfo,
  Settings,
  TelemetryLatest,
  ValidationSummary,
  VenueHeartbeat,
} from "../lib/types";

const LOG_LIMIT = 600;
const SPARK_LIMIT = 60;
const STATUS_POLL_MS = 2_000;
const FILES_POLL_MS = 5_000;
const INVENTORY_POLL_MS = 8_000;

export interface Toast {
  id: number;
  kind: "success" | "error";
  text: string;
}

interface AppData {
  inTauri: boolean;
  status: ProcessStatus[] | null;
  heartbeats: Record<string, VenueHeartbeat>;
  sparklines: Record<string, number[]>;
  inventory: Inventory | null;
  telemetry: TelemetryLatest | null;
  validation: ValidationSummary | null;
  settings: Settings | null;
  repoInfo: RepoInfo | null;
  logs: LogEntry[];
  pending: Partial<Record<ProcKind, boolean>>;
  toasts: Toast[];
  startProcess: (kind: ProcKind) => Promise<void>;
  stopProcess: (kind: ProcKind) => Promise<void>;
  saveSettings: (next: Settings) => Promise<boolean>;
  dismissToast: (id: number) => void;
}

const AppDataContext = createContext<AppData | null>(null);

function parseJsonOrNull<T>(text: string | null): T | null {
  if (!text) return null;
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

interface RawLogEvent {
  source: "recorder" | "telemetry";
  line: string;
}

let nextLogId = 1;
let nextToastId = 1;

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<ProcessStatus[] | null>(null);
  const [heartbeats, setHeartbeats] = useState<Record<string, VenueHeartbeat>>({});
  const [sparklines, setSparklines] = useState<Record<string, number[]>>({});
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryLatest | null>(null);
  const [validation, setValidation] = useState<ValidationSummary | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [repoInfo, setRepoInfo] = useState<RepoInfo | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [pending, setPending] = useState<Partial<Record<ProcKind, boolean>>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const logsRef = useRef<LogEntry[]>([]);

  const pushToast = useCallback((kind: Toast["kind"], text: string) => {
    const id = nextToastId++;
    setToasts((current) => [...current, { id, kind, text }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const refreshStatus = useCallback(async () => {
    setStatus(await call<ProcessStatus[]>("process_status"));
  }, []);

  // Process status poll.
  useEffect(() => {
    void refreshStatus();
    const timer = window.setInterval(() => void refreshStatus(), STATUS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refreshStatus]);

  // Dataset inventory poll.
  useEffect(() => {
    const load = async () => setInventory(await call<Inventory>("dataset_inventory"));
    void load();
    const timer = window.setInterval(() => void load(), INVENTORY_POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  // Telemetry + validation JSON polls.
  useEffect(() => {
    const load = async () => {
      const [telemetryText, validationText] = await Promise.all([
        call<string>("read_status_file", { name: "telemetry_latest" }),
        call<string>("read_status_file", { name: "validation_summary" }),
      ]);
      const parsedTelemetry = parseJsonOrNull<TelemetryLatest>(telemetryText);
      if (parsedTelemetry) setTelemetry(parsedTelemetry);
      const parsedValidation = parseJsonOrNull<ValidationSummary>(validationText);
      if (parsedValidation) setValidation(parsedValidation);
    };
    void load();
    const timer = window.setInterval(() => void load(), FILES_POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  // Settings + repo info, once at startup.
  useEffect(() => {
    void (async () => {
      setSettings(await call<Settings>("get_settings"));
      setRepoInfo(await call<RepoInfo>("repo_info"));
    })();
  }, []);

  // Log streams: subscribe once, then ask the backend to tail both files.
  useEffect(() => {
    let unlisten: (() => void) | null = null;
    let cancelled = false;
    void (async () => {
      const stop = await onEvent<RawLogEvent>("log-line", (payload) => {
        handleLogLine(payload);
      });
      if (cancelled) {
        stop?.();
        return;
      }
      unlisten = stop;
      await call("start_log_stream", { name: "recorder" });
      await call("start_log_stream", { name: "telemetry" });
    })();
    return () => {
      cancelled = true;
      unlisten?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleLogLine(payload: RawLogEvent) {
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = JSON.parse(payload.line) as Record<string, unknown>;
    } catch {
      parsed = null;
    }

    if (parsed && parsed["event"] === "heartbeat" && typeof parsed["venue"] === "string") {
      const venue = parsed["venue"] as string;
      const beat: VenueHeartbeat = {
        venue,
        connected: Boolean(parsed["connected"]),
        msgs_total: Number(parsed["msgs_total"] ?? 0),
        msgs_per_s: Number(parsed["msgs_per_s"] ?? 0),
        raw_bytes_total: Number(parsed["raw_bytes_total"] ?? 0),
        bytes_on_disk_hour: Number(parsed["bytes_on_disk_hour"] ?? 0),
        last_seq: parsed["last_seq"] == null ? null : Number(parsed["last_seq"]),
        seen_at_ms: Date.now(),
      };
      setHeartbeats((current) => ({ ...current, [venue]: beat }));
      setSparklines((current) => {
        const series = [...(current[venue] ?? []), beat.msgs_per_s].slice(-SPARK_LIMIT);
        return { ...current, [venue]: series };
      });
    }

    const known = new Set(["event", "level", "timestamp", "logger"]);
    const detail = parsed
      ? Object.entries(parsed)
          .filter(([k]) => !known.has(k))
          .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
          .join(" ")
      : "";

    const entry: LogEntry = {
      id: nextLogId++,
      source: payload.source,
      time: parsed ? String(parsed["timestamp"] ?? "") : "",
      level: parsed ? String(parsed["level"] ?? "info") : "info",
      event: parsed ? String(parsed["event"] ?? "") : payload.line.slice(0, 80),
      detail,
      raw: payload.line,
    };
    logsRef.current = [...logsRef.current, entry].slice(-LOG_LIMIT);
    setLogs(logsRef.current);
  }

  const startProcess = useCallback(
    async (kind: ProcKind) => {
      setPending((p) => ({ ...p, [kind]: true }));
      try {
        await callStrict<number>("start_process", { kind });
        pushToast("success", kind === "recorder" ? "Recorder started" : "Telemetry started");
      } catch (error) {
        pushToast("error", (error as Error).message);
      } finally {
        setPending((p) => ({ ...p, [kind]: false }));
        void refreshStatus();
      }
    },
    [pushToast, refreshStatus],
  );

  const stopProcess = useCallback(
    async (kind: ProcKind) => {
      setPending((p) => ({ ...p, [kind]: true }));
      try {
        await callStrict<void>("stop_process", { kind });
        pushToast("success", kind === "recorder" ? "Recorder stopped" : "Telemetry stopped");
      } catch (error) {
        pushToast("error", (error as Error).message);
      } finally {
        setPending((p) => ({ ...p, [kind]: false }));
        void refreshStatus();
      }
    },
    [pushToast, refreshStatus],
  );

  const saveSettings = useCallback(
    async (next: Settings): Promise<boolean> => {
      try {
        await callStrict<void>("set_settings", { newSettings: next });
        setSettings(next);
        setRepoInfo(await call<RepoInfo>("repo_info"));
        pushToast("success", "Settings saved");
        return true;
      } catch (error) {
        pushToast("error", (error as Error).message);
        return false;
      }
    },
    [pushToast],
  );

  const value: AppData = {
    inTauri,
    status,
    heartbeats,
    sparklines,
    inventory,
    telemetry,
    validation,
    settings,
    repoInfo,
    logs,
    pending,
    toasts,
    startProcess,
    stopProcess,
    saveSettings,
    dismissToast,
  };

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppData {
  const context = useContext(AppDataContext);
  if (!context) {
    throw new Error("useAppData must be used inside AppDataProvider");
  }
  return context;
}
