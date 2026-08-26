// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

/**
 * Web replacement for `@tauri-apps/plugin-process`, aliased in vite.web.config.ts.
 *
 * Desktop calls `relaunch()` to restart the app after an update or runtime
 * install. A web build has no separate process to relaunch — reloading the
 * page IS the equivalent (it re-fetches the latest deployed bundle), so this
 * is a real behavior, not a stub.
 */
export async function relaunch(): Promise<void> {
  window.location.reload();
}
