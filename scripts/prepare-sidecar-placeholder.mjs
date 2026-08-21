import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sidecarDir = join(repoRoot, "src-tauri", "resources", "backend");
const rustc = spawnSync("rustc", ["-vV"], {
  cwd: repoRoot,
  shell: true,
  encoding: "utf8",
});

if (rustc.status !== 0) {
  throw new Error("rustc -vV failed while preparing sidecar placeholder");
}

const triple = rustc.stdout.match(/^host:\s*(.+)$/m)?.[1]?.trim();
if (!triple) {
  throw new Error("Could not read host triple from rustc -vV");
}

const extension = process.platform === "win32" ? ".exe" : "";
const sidecar = join(sidecarDir, `jhm-sidecar-next-${triple}${extension}`);

mkdirSync(sidecarDir, { recursive: true });
if (!existsSync(sidecar)) {
  writeFileSync(sidecar, "");
  console.log(`Created temporary sidecar placeholder: ${sidecar}`);
}

// tauri.conf.json also lists this manifest as a bundled resource, so the Tauri
// build script fails on a fresh clone without it. The app reads it leniently
// (only an optional runtimePackVersion), so an empty object is a valid stub.
const manifest = join(sidecarDir, "sidecar-manifest.json");
if (!existsSync(manifest)) {
  writeFileSync(manifest, "{}\n");
  console.log(`Created temporary sidecar manifest placeholder: ${manifest}`);
}
