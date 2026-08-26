// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

/**
 * Web replacement for shared/components/UpdatePrompt.tsx, aliased in
 * vite.web.config.ts.
 *
 * The desktop banner walks the Tauri auto-updater's download/install/relaunch
 * flow — there is no installed binary to update in a browser tab; reloading
 * the page always serves the latest deployed build. Degrades to nothing
 * rendered, rather than a broken banner stuck on "Checking…" forever.
 */
export function UpdatePrompt() {
  return null;
}
