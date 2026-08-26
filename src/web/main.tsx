// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

/**
 * The web entry point. Mounts the REAL desktop app (src/App.tsx) — same
 * components, same src/index.css — not a separate lookalike implementation.
 * The only thing this file does beyond src/main.tsx is nothing: the
 * Tauri-vs-browser split happens entirely in vite.web.config.ts's alias
 * table, which swaps each Tauri-only module for a browser shim before this
 * ever imports App. See src/web/shims/*.ts for what each shim does.
 *
 * CSS entry chain — this is NOT a Tailwind content-detection problem (verified:
 * `npx vite build` / `--config vite.web.config.ts` both emit identical utility
 * rules, e.g. `.gap-2{gap:8px}`, `.row{display:flex}`). The real gap: the app
 * shell's foundational layout rule (`.product-app { display: grid;
 * grid-template-columns: ...; }` and the global `.product-app svg { width/
 * height: 17px }` icon default) lives in src/demo/product.css — a "demo mode"
 * stylesheet — because src/main.tsx unconditionally imports DemoApp (for its
 * `?demo=1` route), which pulls in product.css + 8 sibling demo skins as an
 * import side effect. production-journal.css was written assuming that chain
 * is always present (see its "BUGFIX: the global icon sizing rule" and
 * "demo layers (board/diary css) load later" comments) — the real app has
 * quietly depended on demo-mode CSS for its base grid shell ever since. This
 * entry doesn't mount DemoApp, so it never got that chain. Importing the demo
 * stylesheets directly (not the DemoApp component — no JS side effects wanted)
 * reproduces the exact cascade the desktop build gets, in the same order.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import App from "../App";
import ErrorBoundary from "../shared/components/ErrorBoundary";
import { initTheme } from "../shared/lib/theme";
import "../index.css";
import "../demo/product.css";
import "../demo/handdrawn.css";
import "../demo/polish.css";
import "../demo/diary.css";
import "../demo/board.css";
import "../demo/glass-board.css";
import "../demo/clarity.css";
import "../demo/theme.css";
import "../demo/atelier.css";
import "../production-journal.css";
import "./web-extra.css";

initTheme();

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root mount node");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ErrorBoundary label="JustHireMe">
      <App showReport />
    </ErrorBoundary>
  </React.StrictMode>,
);
