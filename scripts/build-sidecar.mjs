import { spawn } from "node:child_process";
import { chmodSync, copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";
import { computeRuntimePackContentVersion } from "./runtime-pack-version.mjs";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = join(repoRoot, "backend");
const resourcesDir = join(repoRoot, "src-tauri", "resources");
const sidecarDir = join(resourcesDir, "backend");
const sidecarInternalDir = join(resourcesDir, "sidecar-internal");
const distDir = join(repoRoot, ".codex-temp-sidecar");
const builtSidecarDir = join(distDir, "backend");
const workPath = join(backendDir, "build_cache");
const pyinstallerConfigDir = join(backendDir, ".pyinstaller-cache");
const python = process.platform === "win32"
  ? join(backendDir, ".venv", "Scripts", "python.exe")
  : join(backendDir, ".venv", "bin", "python");

function run(command, args, options = {}) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd || repoRoot,
      env: {
        ...process.env,
        UV_CACHE_DIR: join(backendDir, ".uv-cache"),
        PYTHONNOUSERSITE: "1",
        PYINSTALLER_CONFIG_DIR: pyinstallerConfigDir,
        HF_HOME: join(backendDir, ".hf-cache"),
      },
      shell: true,
      stdio: "inherit",
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolveRun();
      } else {
        reject(new Error(`${command} ${args.join(" ")} exited with code ${code}`));
      }
    });
  });
}

function capture(command, args, options = {}) {
  return new Promise((resolveCapture, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd || repoRoot,
      env: {
        ...process.env,
        PYTHONNOUSERSITE: "1",
      },
      shell: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let output = "";
    let errorOutput = "";
    child.stdout.on("data", (chunk) => {
      output += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      errorOutput += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolveCapture(output.trim() || errorOutput.trim());
      } else {
        reject(new Error(`${command} ${args.join(" ")} exited with code ${code}: ${errorOutput.trim()}`));
      }
    });
  });
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function readTomlVersion(path) {
  const match = readFileSync(path, "utf8").match(/^version\s*=\s*"([^"]+)"/m);
  return match?.[1] || "unknown";
}

function bytes(path) {
  if (!existsSync(path)) return 0;
  const stat = statSync(path);
  if (stat.isFile()) return stat.size;
  if (!stat.isDirectory()) return 0;
  return readdirSync(path).reduce((total, entry) => total + bytes(join(path, entry)), 0);
}

function formatMb(value) {
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function rmWithRetries(path, options = {}, attempts = 6) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      rmSync(path, options);
      return;
    } catch (error) {
      const retryable = ["EBUSY", "EPERM", "ENOTEMPTY"].includes(error?.code);
      if (!retryable || attempt === attempts) {
        throw error;
      }
      await sleep(750 * attempt);
    }
  }
}

async function getRustTriple() {
  return new Promise((resolveTriple, reject) => {
    const child = spawn("rustc", ["-vV"], {
      cwd: repoRoot,
      shell: true,
      stdio: ["ignore", "pipe", "inherit"],
    });

    let output = "";
    child.stdout.on("data", (chunk) => {
      output += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`rustc -vV exited with code ${code}`));
        return;
      }
      const host = output.match(/^host:\s*(.+)$/m)?.[1]?.trim();
      if (!host) {
        reject(new Error("Could not read host triple from rustc -vV"));
        return;
      }
      resolveTriple(host);
    });
  });
}

const pyinstallerArgs = [
  "-m",
  "PyInstaller",
  "backend.spec",
  "--noconfirm",
  "--distpath",
  distDir,
  "--workpath",
  workPath,
];

if (!existsSync(python)) {
  throw new Error(`Python virtual environment not found: ${python}`);
}

await rmWithRetries(distDir, { recursive: true, force: true });
await rmWithRetries(join(workPath, "backend"), { recursive: true, force: true });
mkdirSync(distDir, { recursive: true });
await run(python, pyinstallerArgs, { cwd: backendDir });

const triple = await getRustTriple();
const extension = process.platform === "win32" ? ".exe" : "";
const onefileSource = join(distDir, `backend${extension}`);
const onedirSource = join(builtSidecarDir, `backend${extension}`);
const source = existsSync(onefileSource) && statSync(onefileSource).isFile()
  ? onefileSource
  : onedirSource;
const sidecarName = "jhm-sidecar-next";
const target = join(sidecarDir, `${sidecarName}-${triple}${extension}`);
const internalSource = join(builtSidecarDir, "_internal");
const manifestTarget = join(sidecarDir, "sidecar-manifest.json");
const sidecarLayout = existsSync(internalSource) ? "onedir" : "onefile";

if (!existsSync(source)) {
  throw new Error(`Expected PyInstaller sidecar was not created: ${source}`);
}
if (sidecarLayout !== "onefile") {
  throw new Error("Release sidecars must be PyInstaller onefile builds; bundled _internal runtimes make installers too large.");
}

await rmWithRetries(sidecarDir, { recursive: true, force: true });
mkdirSync(sidecarDir, { recursive: true });
await rmWithRetries(sidecarInternalDir, { recursive: true, force: true });
mkdirSync(sidecarInternalDir, { recursive: true });
writeFileSync(join(sidecarInternalDir, ".onefile-sidecar"), "PyInstaller onefile sidecar has no external runtime directory.\n", "utf8");
copyFileSync(source, target);
if (process.platform !== "win32") {
  chmodSync(target, 0o755);
}

const packageJson = readJson(join(repoRoot, "package.json"));
const backendVersion = readTomlVersion(join(backendDir, "pyproject.toml"));
const pythonVersion = await capture(python, ["--version"], { cwd: backendDir });
const { version: runtimePackVersion } = computeRuntimePackContentVersion(repoRoot);
const manifest = {
  appVersion: packageJson.version,
  backendVersion,
  platformTriple: triple,
  pythonVersion,
  builtAt: new Date().toISOString(),
  sidecarBinary: `${sidecarName}-${triple}${extension}`,
  sidecarBinaryBytes: bytes(target),
  sidecarInternalBytes: bytes(sidecarInternalDir),
  sidecarLayout,
  // Content version of the runtime pack this build expects. lib.rs forwards it
  // to the sidecar as JHM_RUNTIME_PACK_VERSION so app updates reuse a cached
  // pack instead of re-downloading it. See scripts/runtime-pack-version.mjs.
  runtimePackVersion,
};

writeFileSync(manifestTarget, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

console.log(`Sidecar ready: ${target}`);
console.log(`Sidecar binary size: ${formatMb(manifest.sidecarBinaryBytes)}`);
console.log(`Sidecar runtime size: ${formatMb(manifest.sidecarInternalBytes)}`);
console.log(`Sidecar layout: ${manifest.sidecarLayout}`);
console.log(`Sidecar manifest: ${manifestTarget}`);
