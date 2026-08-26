// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

/**
 * Web replacement for `@tauri-apps/api/core`, aliased in vite.web.config.ts.
 *
 * The desktop app's `invoke("<command>")` calls a Rust command in the Tauri
 * shell. There is no shell in a browser, so this answers the handful of
 * commands components still call directly (useWS.ts and UpdatePrompt.tsx are
 * swapped out wholesale for web and never reach this file at all — see
 * vite.web.config.ts's alias table).
 */
export async function invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (cmd === "notify_high_score_lead") {
    // Real behavior, not a stub: the browser Notification API is the direct
    // web equivalent of the desktop OS notification useLeads.ts asks for.
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(String(args?.title ?? ""), { body: String(args?.body ?? "") });
    }
    return undefined as T;
  }
  // Any other native-only command (sidecar plumbing, updater status, …) has
  // no web equivalent — resolve to a harmless default instead of throwing,
  // so a caller with a `.catch(() => {})` (every current call site) degrades
  // silently rather than logging noise on every render.
  return undefined as T;
}
