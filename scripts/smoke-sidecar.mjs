import { spawn, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
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

function remove(path, options = {}) {
  try {
    rmSync(path, {
      recursive: true,
      force: true,
      maxRetries: 10,
      retryDelay: 500,
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

function requireHealth(health) {
  const components = health.components || health.checks || {};
  const sqlite = components.sqlite?.status;
  const graph = components.graph?.status;
  const vector = components.vector?.status;

  if (sqlite !== "ok") {
    fail(`SQLite health must be ok, got ${sqlite || "(missing)"}`);
  }
  if (graph !== "ok") {
    fail(`Graph health must be ok, got ${graph || "(missing)"}`);
  }
  if (!["ok", "disabled"].includes(vector)) {
    fail(`Vector health must be ok or disabled, got ${vector || "(missing)"}`);
  }

  return { sqlite, graph, vector, app: health.status };
}

const explicitSidecar = resolveExplicitSidecar();

if (!explicitSidecar && !existsSync(manifestPath)) {
  fail(`Sidecar manifest not found at ${manifestPath}. Run npm run build:sidecar first.`);
}

const manifest = explicitSidecar ? {} : readJson(manifestPath);
const { sidecar, cwd, cleanupDir } = explicitSidecar || resolveSidecar(manifest);
const stdoutLines = [];
const stderrLines = [];
let passed = false;

remove(appDataDir);
mkdirSync(appDataDir, { recursive: true });
mkdirSync(cwd, { recursive: true });

const child = spawn(sidecar, ["--no-services"], {
  cwd,
  env: {
    ...process.env,
    JHM_APP_DATA_DIR: appDataDir,
    LOCALAPPDATA: appDataDir,
    PYTHONUNBUFFERED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});

try {
  const handshake = await waitForHandshake(child, stdoutLines, stderrLines);
  const health = await readHealth(handshake.port, handshake.token);
  const summary = requireHealth(health);

  console.log(`Sidecar smoke passed: ${sidecar}`);
  console.log(`- port: ${handshake.port}`);
  console.log(`- app: ${summary.app}`);
  console.log(`- sqlite: ${summary.sqlite}`);
  console.log(`- graph: ${summary.graph}`);
  console.log(`- vector: ${summary.vector}`);
  passed = true;
} finally {
  killProcessTree(child);
  await sleep(500);
  remove(appDataDir, { allowFailure: true });
  if (cleanupDir) {
    remove(cleanupDir, { allowFailure: true });
  }
}

if (passed) {
  process.exit(0);
}
