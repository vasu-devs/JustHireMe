// Single source of truth for the runtime pack's *content* version.
//
// The runtime pack (Chromium + vector libs + ONNX embedding model) changes far
// less often than the app itself. Keying its identity off a hash of its pinned
// contents — rather than the app version — lets a routine app update reuse an
// already-installed pack instead of re-downloading hundreds of MB every release.
//
// Both build-sidecar.mjs and package-runtime-pack.mjs compute this from the same
// inputs (the installed Playwright browser revisions + pinned vector dep
// versions + model id + a manual schema number), so they always agree without
// having to pass the value between build jobs.

import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import process from "node:process";

// Bump when the pack's layout changes in a way the content signals below do not
// capture (e.g. a directory restructure or a new component), to force clients
// to re-fetch.
const RUNTIME_PACK_SCHEMA = 1;

const ONNX_MODEL_NAME = "all-MiniLM-L6-v2";

// dist-info prefixes whose installed versions define the vector runtime payload.
// A bump to any of these changes the pack contents and must invalidate caches.
const VECTOR_DISTINFO_PREFIXES = [
  "lancedb-",
  "pyarrow-",
  "numpy-",
  "pydantic-",
  "pydantic_core-",
  "urllib3-",
];

function defaultSitePackages(repoRoot) {
  const backendDir = join(repoRoot, "backend");
  const pythonVersion = readFileSync(join(backendDir, ".python-version"), "utf8").trim();
  return process.platform === "win32"
    ? join(backendDir, ".venv", "Lib", "site-packages")
    : join(backendDir, ".venv", "lib", `python${pythonVersion}`, "site-packages");
}

function listSorted(dir, predicate) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).filter(predicate).sort();
}

/**
 * Compute the deterministic content version for the runtime pack.
 * @returns {{ version: string, signals: object }}
 */
export function computeRuntimePackContentVersion(repoRoot, options = {}) {
  const sitePackages = options.sitePackages || defaultSitePackages(repoRoot);
  const browserSource =
    options.browserSource ||
    join(repoRoot, "src-tauri", "resources", "bin", "ms-playwright");

  // chromium-<rev> and chromium_headless_shell-<rev> both start with "chromium".
  const chromium = listSorted(browserSource, (n) => n.toLowerCase().startsWith("chromium"));
  const vector = VECTOR_DISTINFO_PREFIXES.flatMap((prefix) =>
    listSorted(sitePackages, (n) => n.startsWith(prefix) && n.endsWith(".dist-info")),
  ).sort();

  const signals = {
    schema: RUNTIME_PACK_SCHEMA,
    model: ONNX_MODEL_NAME,
    chromium,
    vector,
  };
  const digest = createHash("sha256").update(JSON.stringify(signals)).digest("hex").slice(0, 12);
  return { version: `rt-${digest}`, signals };
}
