// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

/**
 * Web replacement for `@tauri-apps/plugin-opener`, aliased in vite.web.config.ts.
 *
 * The desktop app hands URLs (legal links, generated PDF blobs) to Tauri's
 * `openUrl`, which shells out to the OS. A browser already has the native
 * equivalent — `window.open` — so every call site (SettingsModal,
 * ApplyJobView, ApprovalDrawer, shared/lib/openExternal.ts) keeps working
 * unmodified once this file is swapped in for the real plugin.
 */
export async function openUrl(url: string): Promise<void> {
  window.open(url, "_blank", "noopener,noreferrer");
}
