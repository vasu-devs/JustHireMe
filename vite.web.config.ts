import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * The web shell — the second entrypoint of "one data layer, two shells"
 * (WEB_MIGRATION_LLD Workstream F.2). Its own config so the Tauri build in
 * vite.config.ts is untouched: that one ships to ~2,200 desktop installs.
 *
 * This build serves the REAL desktop app (src/App.tsx, real screens, real
 * src/index.css) in a browser — not a lookalike. The only difference from the
 * desktop build is the alias table below, which swaps each Tauri-only module
 * for a browser equivalent (src/web/shims/*). Everything else — components,
 * styles, API modules — is the exact same source the desktop build ships.
 */
const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

const backendPort = process.env.JHM_BACKEND_PORT || "8787";
const backendToken = process.env.JHM_TOKEN || "";

/**
 * Serve the web app at `/`.
 *
 * Without this, `/` falls through to index.html — the DESKTOP entry, which
 * expects Tauri and renders broken in a plain browser. Nobody types
 * `/web.html`, so the root has to be the app.
 */
function serveWebAtRoot(): Plugin {
  return {
    name: "jhm-web-root",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url === "/" || req.url?.startsWith("/?")) {
          req.url = "/web.html" + (req.url.slice(1) || "");
        }
        next();
      });
    },
  };
}

export default defineConfig({
  // tailwindcss() matters here: src/index.css uses Tailwind v4's CSS-first
  // @theme/@tailwind directives (all the design tokens -- --paper, --ink,
  // --accent, ...), which only resolve into real CSS through this plugin.
  // Without it the whole app renders unstyled (confirmed: every screen lost
  // its layout, colors, and card backgrounds until this was added) even
  // though vite.config.ts (the desktop build) already had it.
  plugins: [react(), tailwindcss(), serveWebAtRoot()],
  root: ".",
  publicDir: false,
  resolve: {
    // NOTE: `find` matches the import specifier text exactly as written in the
    // source file (Vite's alias resolver runs before path resolution) — NOT
    // the file it resolves to. So these have to be the literal strings App.tsx
    // (and, for "./client", every src/api/*.ts module) actually import, not an
    // absolute path to the same file reached a different way.
    alias: [
      // Tauri plugins -> browser equivalents (window.open, page reload, no-op invoke).
      { find: "@tauri-apps/plugin-opener", replacement: r("./src/web/shims/tauri-opener.ts") },
      { find: "@tauri-apps/plugin-process", replacement: r("./src/web/shims/tauri-process.ts") },
      { find: "@tauri-apps/api/core", replacement: r("./src/web/shims/tauri-core.ts") },
      // Sidecar plumbing -> REST status polling (see shims/useWS.ts's docstring).
      // Only App.tsx imports this, as "./shared/hooks/useWS".
      { find: "./shared/hooks/useWS", replacement: r("./src/web/shims/useWS.ts") },
      // Native auto-updater -> nothing to render (reload always serves latest).
      // Only App.tsx imports this, as "./shared/components/UpdatePrompt".
      { find: "./shared/components/UpdatePrompt", replacement: r("./src/web/shims/UpdatePrompt.tsx") },
      // Absolute-URL + real-token fetch -> relative fetch through the dev proxy
      // below. Every src/api/*.ts module imports this the same way, as
      // "./client" (they're all siblings in src/api/), so one alias covers them.
      { find: "./client", replacement: r("./src/web/shims/api-client.ts") },
    ],
  },
  build: {
    outDir: "dist-web",
    emptyOutDir: true,
    rollupOptions: { input: "web.html" },
  },
  server: {
    port: 5273,
    strictPort: true,
    open: true,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        // The dev proxy attaches the sidecar's bearer token server-side, so the
        // browser never handles one. `npm run web` discovers it from the
        // backend's startup output. Stage 3 replaces this with real cookies.
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            if (backendToken) proxyReq.setHeader("Authorization", `Bearer ${backendToken}`);
          });
        },
      },
      "/health": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            if (backendToken) proxyReq.setHeader("Authorization", `Bearer ${backendToken}`);
          });
        },
      },
    },
  },
});
