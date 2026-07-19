import { spawn, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const resourcesDir = join(repoRoot, "src-tauri", "resources");
const targetReleaseDir = join(repoRoot, "src-tauri", "target", "release");
const manifestPath = join(resourcesDir, "backend", "sidecar-manifest.json");
const appDataDir = join(repoRoot, ".codex-temp-sidecar", `runtime-smoke-${Date.now()}-${process.pid}`);
const timeoutMs = Number(process.env.JHM_SIDECAR_SMOKE_TIMEOUT_MS || 90_000);
const executableExtension = process.platform === "win32" ? ".exe" : "";

function fail(message) {
  throw new Error(message);
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function bytes(path) {
  if (!existsSync(path)) return 0;
  const stat = statSync(path);
  if (stat.isFile()) return stat.size;
  return 0;
}

function vectorRuntimeAssetName() {
  if (process.platform === "win32") return "JustHireMe-vector-runtime-windows.zip";
  if (process.platform === "darwin") return "JustHireMe-vector-runtime-macos.zip";
  return "JustHireMe-vector-runtime-linux.zip";
}

function runtimePackAssetName() {
  if (process.platform === "win32") return "JustHireMe-runtime-pack-windows.zip";
  if (process.platform === "darwin") return "JustHireMe-runtime-pack-macos.zip";
  return "JustHireMe-runtime-pack-linux.zip";
}

function localRuntimePackArchive() {
  return process.env.JHM_SMOKE_RUNTIME_PACK_ARCHIVE || join(repoRoot, "release-assets", runtimePackAssetName());
}

function localVectorRuntimeArchive() {
  return existsSync(localRuntimePackArchive())
    ? localRuntimePackArchive()
    : join(repoRoot, "release-assets", vectorRuntimeAssetName());
}

function localRuntimePackUrl() {
  return pathToFileURL(localVectorRuntimeArchive()).href;
}

function remove(path, options = {}) {
  try {
    rmSync(path, {
      recursive: true,
      force: true,
      maxRetries: 20,
      retryDelay: 750,
    });
  } catch (error) {
    if (options.allowFailure) {
      console.warn(`Could not remove ${path}: ${error.message}`);
      return;
    }
    throw error;
  }
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

function targetSidecarPath() {
  return join(targetReleaseDir, `jhm-sidecar-next${executableExtension}`);
}

function resourceSidecarPath(manifest) {
  return join(resourcesDir, "backend", manifest.sidecarBinary);
}

function prepareFallbackSidecar(manifest) {
  const runDir = join(repoRoot, ".codex-temp-sidecar", `runtime-smoke-sidecar-${Date.now()}-${process.pid}`);
  const source = resourceSidecarPath(manifest);
  const target = join(runDir, `jhm-sidecar-next${executableExtension}`);
  const internalSource = join(resourcesDir, "sidecar-internal");

  if (!existsSync(source)) {
    fail(`Packaged sidecar not found at ${source}`);
  }

  remove(runDir);
  mkdirSync(runDir, { recursive: true });
  cpSync(source, target);

  if (manifest.sidecarLayout === "onedir") {
    if (!existsSync(internalSource)) {
      fail(`Sidecar runtime directory not found at ${internalSource}`);
    }
    cpSync(internalSource, join(runDir, "_internal"), { recursive: true });
  }

  return { sidecar: target, cwd: runDir, cleanupDir: runDir };
}

function resolveExplicitSidecar() {
  const rawSidecar = process.env.JHM_SIDECAR_PATH;
  if (!rawSidecar) {
    return null;
  }
  const sidecar = resolve(rawSidecar);
  if (!existsSync(sidecar)) {
    fail(`Sidecar override not found at ${sidecar}`);
  }
  const rawCwd = process.env.JHM_SIDECAR_CWD;
  return {
    sidecar,
    cwd: rawCwd ? resolve(rawCwd) : appDataDir,
    cleanupDir: "",
  };
}

function resolveSidecar(manifest) {
  const explicit = resolveExplicitSidecar();
  if (explicit) {
    return explicit;
  }

  const sidecar = targetSidecarPath();
  const internal = join(targetReleaseDir, "_internal");

  if (existsSync(sidecar)) {
    const targetIsStale = manifest.sidecarBinaryBytes && bytes(sidecar) !== manifest.sidecarBinaryBytes;
    const targetMissingRuntime = manifest.sidecarLayout === "onedir" && !existsSync(internal);

    if (!targetIsStale && !targetMissingRuntime) {
      return { sidecar, cwd: targetReleaseDir, cleanupDir: "" };
    }

    const reason = targetIsStale
      ? `${sidecar} is ${bytes(sidecar)} bytes, expected ${manifest.sidecarBinaryBytes}`
      : `${internal} is missing`;
    console.warn(`Ignoring stale target sidecar (${reason}); using fresh resource sidecar instead.`);
  }

  return prepareFallbackSidecar(manifest);
}

function killProcessTree(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGTERM");
  }
}

function parseHandshakeLine(line, handshake) {
  const trimmed = line.trim();
  if (trimmed.startsWith("JHM_TOKEN=")) {
    handshake.token = trimmed.slice("JHM_TOKEN=".length);
  } else if (trimmed.startsWith("PORT:")) {
    const port = Number(trimmed.slice("PORT:".length));
    if (Number.isInteger(port) && port > 0) {
      handshake.port = port;
    }
  }
}

function waitForHandshake(child, stdoutLines, stderrLines) {
  const handshake = { token: "", port: 0 };
  let stdoutRemainder = "";
  let stderrRemainder = "";

  return new Promise((resolveWait, reject) => {
    const timer = setTimeout(() => {
      reject(
        new Error(
          `Sidecar did not emit JHM_TOKEN and PORT within ${timeoutMs}ms.\n` +
            `stdout:\n${stdoutLines.join("\n")}\n` +
            `stderr:\n${stderrLines.join("\n")}`
        )
      );
    }, timeoutMs);

    child.stdout.on("data", (chunk) => {
      stdoutRemainder += chunk.toString();
      const lines = stdoutRemainder.split(/\r?\n/);
      stdoutRemainder = lines.pop() || "";
      for (const line of lines) {
        stdoutLines.push(line);
        parseHandshakeLine(line, handshake);
      }
      if (handshake.token && handshake.port) {
        clearTimeout(timer);
        resolveWait(handshake);
      }
    });

    child.stderr.on("data", (chunk) => {
      stderrRemainder += chunk.toString();
      const lines = stderrRemainder.split(/\r?\n/);
      stderrRemainder = lines.pop() || "";
      for (const line of lines) {
        stderrLines.push(line);
      }
    });

    child.on("exit", (code, signal) => {
      if (!handshake.token || !handshake.port) {
        clearTimeout(timer);
        reject(
          new Error(
            `Sidecar exited before startup handshake. code=${code} signal=${signal}\n` +
              `stdout:\n${stdoutLines.join("\n")}\n` +
              `stderr:\n${stderrLines.join("\n")}`
          )
        );
      }
    });

    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
  });
}

async function readHealth(port, token) {
  const deadline = Date.now() + 30_000;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new Error(`/health returned HTTP ${response.status}: ${await response.text()}`);
      }
      return response.json();
    } catch (error) {
      lastError = error;
      await sleep(500);
    }
  }

  throw lastError || new Error("/health did not become available");
}

async function readApi(port, token, path, options = {}) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`${path} returned HTTP ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

async function smokeCoreApi(port, token) {
  const [settings, leads, profile, diagnostics] = await Promise.all([
    readApi(port, token, "/api/v1/settings"),
    readApi(port, token, "/api/v1/leads"),
    readApi(port, token, "/api/v1/profile"),
    readApi(port, token, "/api/v1/diagnostics"),
  ]);
  if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
    fail("/api/v1/settings must return an object");
  }
  if (!Array.isArray(leads)) {
    fail("/api/v1/leads must return an array");
  }
  if (!profile || typeof profile !== "object" || Array.isArray(profile)) {
    fail("/api/v1/profile must return an object");
  }
  if (!diagnostics || typeof diagnostics !== "object" || !Array.isArray(diagnostics.top_errors)) {
    fail("/api/v1/diagnostics must return a diagnostics object");
  }
}

// Every parameterless GET the app exposes must at least not 500 in the FROZEN
// build. A handler whose module the bundler dropped only explodes when the
// route runs (the learning router shipped broken this way: startup fine,
// endpoint 500 ModuleNotFoundError) — so smoke ALL of them, discovered from
// the app's own OpenAPI schema rather than a hand-maintained list.
async function smokeEveryParameterlessGet(port, token) {
  const response = await fetch(`http://127.0.0.1:${port}/openapi.json`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    fail(`/openapi.json returned HTTP ${response.status}`);
  }
  const schema = await response.json();
  const targets = Object.entries(schema.paths || {})
    .filter(([path, methods]) => methods.get && !path.includes("{"))
    .map(([path]) => path);
  if (targets.length < 5) {
    fail(`OpenAPI sweep found only ${targets.length} parameterless GET routes — schema looks broken`);
  }
  const failures = [];
  for (const path of targets) {
    const res = await fetch(`http://127.0.0.1:${port}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status >= 500) {
      failures.push(`${path} -> HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
    }
  }
  if (failures.length) {
    fail(`Frozen-build GET sweep found server errors:\n${failures.join("\n")}`);
  }
  return targets.length;
}

function requireHealth(health, options = {}) {
  const components = health.components || health.checks || {};
  const sqlite = components.sqlite?.status;
  const graph = components.graph?.status;
  const vector = components.vector?.status;

  if (sqlite !== "ok") {
    fail(`SQLite health must be ok, got ${sqlite || "(missing)"}: ${JSON.stringify(components.sqlite || {})}`);
  }
  if (graph !== "ok") {
    fail(`Graph health must be ok, got ${graph || "(missing)"}: ${JSON.stringify(components.graph || {})}`);
  }
  if (options.vectorRequired && vector !== "ok") {
    fail(`Vector health must be ok in release sidecars, got ${vector || "(missing)"}`);
  }

  return { sqlite, graph, vector, app: health.status };
}

async function ensureVectorRuntime(port, token) {
  const archive = localVectorRuntimeArchive();
  const initial = await readApi(port, token, "/api/v1/runtime/vector");
  if (initial.ready) {
    return initial;
  }
  if (!existsSync(archive)) {
    const message = `Runtime pack archive not found at ${archive}; OTA install smoke skipped.`;
    if (process.env.JHM_VECTOR_RUNTIME_REQUIRED === "1") fail(message);
    console.warn(message);
    return initial;
  }
  await readApi(port, token, "/api/v1/runtime/vector/install", { method: "POST" });
  const deadline = Date.now() + 90_000;
  let last = initial;
  while (Date.now() < deadline) {
    last = await readApi(port, token, "/api/v1/runtime/vector");
    if (last.ready) {
      return last;
    }
    if (last.progress?.status === "error") {
      fail(`Runtime pack install failed: ${JSON.stringify(last)}`);
    }
    await sleep(500);
  }
  fail(`Runtime pack install did not become ready: ${JSON.stringify(last)}`);
}

const explicitSidecar = resolveExplicitSidecar();

if (!explicitSidecar && !existsSync(manifestPath)) {
  fail(`Sidecar manifest not found at ${manifestPath}. Run npm run build:sidecar first.`);
}

const manifest = explicitSidecar ? {} : readJson(manifestPath);
if (!explicitSidecar && manifest.sidecarLayout !== "onefile") {
  fail(`Release sidecar must be onefile; got ${manifest.sidecarLayout || "missing"} in ${manifestPath}`);
}
const { sidecar, cwd, cleanupDir } = explicitSidecar || resolveSidecar(manifest);
const stdoutLines = [];
const stderrLines = [];
let passed = false;
let handshake = null;
let childClosed = false;

remove(appDataDir);
mkdirSync(appDataDir, { recursive: true });
mkdirSync(cwd, { recursive: true });

const child = spawn(sidecar, ["--no-services"], {
  cwd,
  env: {
    ...process.env,
    JHM_APP_DATA_DIR: appDataDir,
    JHM_VECTOR_RUNTIME_DIR: join(appDataDir, "vector-runtime"),
    JHM_RUNTIME_PACK_URL: localRuntimePackUrl(),
    JHM_VECTOR_RUNTIME_URL: localRuntimePackUrl(),
    LOCALAPPDATA: appDataDir,
    PYTHONUNBUFFERED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});
child.on("close", () => {
  childClosed = true;
});

function waitForChildClose(childProcess, ms) {
  if (!childProcess || childClosed || childProcess.exitCode !== null || childProcess.signalCode !== null) {
    return Promise.resolve(true);
  }
  return new Promise((resolveWait) => {
    const timer = setTimeout(() => {
      childProcess.off("close", onClose);
      resolveWait(false);
    }, ms);
    function onClose() {
      clearTimeout(timer);
      resolveWait(true);
    }
    childProcess.once("close", onClose);
  });
}

async function requestShutdown(port, token) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/v1/shutdown`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      console.warn(`/api/v1/shutdown returned HTTP ${response.status}: ${await response.text()}`);
    }
  } catch (error) {
    console.warn(`Could not request graceful sidecar shutdown: ${error.message}`);
  }
}

try {
  handshake = await waitForHandshake(child, stdoutLines, stderrLines);
  const health = await readHealth(handshake.port, handshake.token);
  const summary = requireHealth(health);
  await smokeCoreApi(handshake.port, handshake.token);
  const sweptRoutes = await smokeEveryParameterlessGet(handshake.port, handshake.token);
  const vectorRuntime = await ensureVectorRuntime(handshake.port, handshake.token);
  const healthAfterRuntime = await readHealth(handshake.port, handshake.token);
  const summaryAfterRuntime = requireHealth(healthAfterRuntime, { vectorRequired: vectorRuntime.ready });

  console.log(`Sidecar smoke passed: ${sidecar}`);
  console.log(`- port: ${handshake.port}`);
  console.log(`- app: ${summary.app}`);
  console.log(`- sqlite: ${summary.sqlite}`);
  console.log(`- graph: ${summary.graph}`);
  console.log(`- vector: ${summaryAfterRuntime.vector || summary.vector}`);
  console.log("- api: settings, leads, profile, diagnostics");
  console.log(`- swept: ${sweptRoutes} parameterless GET routes, zero 5xx`);
  passed = true;
} finally {
  if (handshake?.port && handshake?.token) {
    await requestShutdown(handshake.port, handshake.token);
  }
  const closedCleanly = await waitForChildClose(child, 15_000);
  if (!closedCleanly) {
    killProcessTree(child);
    await waitForChildClose(child, 5_000);
  }
  await sleep(1000);
  remove(appDataDir, { allowFailure: true });
  if (cleanupDir) {
    remove(cleanupDir, { allowFailure: true });
  }
}

if (passed) {
  process.exit(0);
}
