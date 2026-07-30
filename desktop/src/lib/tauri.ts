/** Thin, safe layer over the Tauri IPC.
 *
 * Reads use `call`: outside the desktop shell (plain browser dev) or on error
 * they resolve to null and the UI shows its designed empty state — never mock
 * data. Actions use `callStrict` so failures surface to the user as toasts.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export const inTauri: boolean =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function call<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T | null> {
  if (!inTauri) return null;
  try {
    return await invoke<T>(cmd, args);
  } catch (error) {
    console.warn(`[mlce] ${cmd} failed:`, error);
    return null;
  }
}

export async function callStrict<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!inTauri) {
    throw new Error("Not running inside the desktop shell.");
  }
  try {
    return await invoke<T>(cmd, args);
  } catch (error) {
    throw new Error(typeof error === "string" ? error : String(error));
  }
}

export async function onEvent<T>(
  name: string,
  handler: (payload: T) => void,
): Promise<UnlistenFn | null> {
  if (!inTauri) return null;
  return listen<T>(name, (event) => handler(event.payload));
}
