// One-time (idempotent) local dev runtime setup.
//
// `npm run tauri dev` runs the backend from your venv but does NOT auto-download
// the heavy runtime pack (that only happens on first launch of the *packaged*
// app). So in dev the embedding model is missing (falls back to hashing) and the
// Playwright browser may be absent (portfolio crawl / web scout can't launch).
//
// This script fetches both into the exact locations the dev sidecar reads:
//   1. the ONNX embedding model (all-MiniLM-L6-v2, ~90 MB) -> the Tauri app-data
//      dir's models/ folder (JHM_APP_DATA_DIR = app_data_dir() in dev).
//   2. the Playwright Chromium browser -> the default ms-playwright cache.
//
// Safe to re-run: each step skips work that's already present.
//
//   npm run setup:local      # run once; then `npm run tauri dev` has everything
//   npm run dev:local        # setup + tauri dev in one command

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const backendDir = join(repoRoot, "backend");

function tauriIdentifier() {
  const conf = JSON.parse(readFileSync(join(repoRoot, "src-tauri", "tauri.conf.json"), "utf8"));
  return conf.identifier || "com.vasudev-siddh.justhireme";
}

// Mirror Tauri's app_data_dir() per-OS so the model lands where the dev sidecar looks.
function appDataDir(identifier) {
  if (process.platform === "win32") {
    return join(process.env.APPDATA || join(homedir(), "AppData", "Roaming"), identifier);
  }
  if (process.platform === "darwin") {
    return join(homedir(), "Library", "Application Support", identifier);
  }
  return join(process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"), identifier);
}

function run(label, cmd, args, extraEnv = {}) {
  console.log(`\n=== ${label} ===`);
  const result = spawnSync(cmd, args, {
    cwd: backendDir,
    stdio: "inherit",
    shell: true,
    env: { ...process.env, ...extraEnv },
  });
  if (result.status !== 0) {
    console.error(`\n[setup:local] ${label} FAILED (exit ${result.status}).`);
    process.exit(result.status ?? 1);
  }
}

// Run a multi-line Python snippet via stdin (`python -`) rather than `-c`, so the
// shell never re-parses semicolons/quotes, and the code runs with backendDir on
// sys.path (cwd) so it can import the backend packages.
function runPython(label, pyCode, extraEnv = {}) {
  console.log(`\n=== ${label} ===`);
  const result = spawnSync("uv", ["run", "python", "-"], {
    cwd: backendDir,
    input: pyCode,
    stdio: ["pipe", "inherit", "inherit"],
    shell: true,
    env: { ...process.env, ...extraEnv },
  });
  if (result.status !== 0) {
    console.error(`\n[setup:local] ${label} FAILED (exit ${result.status}).`);
    process.exit(result.status ?? 1);
  }
}

const identifier = tauriIdentifier();
const dataDir = appDataDir(identifier);
console.log(`[setup:local] app-data dir for the dev sidecar: ${dataDir}`);

// 1) ONNX embedding model -> <app-data>/models/all-MiniLM-L6-v2 (skips if present).
runPython(
  "Download ONNX embedding model (semantic search)",
  // download_onnx_model() catches its own errors and RETURNS {status:"error"} rather
  // than raising, so assert the status and exit non-zero on failure — otherwise a
  // failed/partial download prints an error dict but exits 0 and setup:local falsely
  // reports success while the dev sidecar silently degrades to the hash fallback.
  "import json, sys\nfrom data.vector.embeddings import download_onnx_model\nr = download_onnx_model()\nprint(json.dumps(r))\nsys.exit(0 if r.get('status') in ('ok', 'exists') else 1)\n",
  { JHM_APP_DATA_DIR: dataDir },
);

// 2) Playwright Chromium -> default ms-playwright cache (playwright skips if present).
run(
  "Install Playwright Chromium (portfolio crawl / web scout)",
  "uv",
  ["run", "python", "-m", "playwright", "install", "chromium"],
);

console.log("\n[setup:local] Done. `npm run tauri dev` now has the full runtime — semantic embeddings + browser. No first-run download needed.");
