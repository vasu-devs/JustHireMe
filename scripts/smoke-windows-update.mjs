import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const updateSmokeEnabled = process.env.JHM_WINDOWS_UPDATE_SMOKE === "1";
const installerSmokeEnabled = process.env.JHM_WINDOWS_INSTALLER_SMOKE === "1";
const timeoutMs = Number(process.env.JHM_WINDOWS_UPDATE_TIMEOUT_MS || 120_000);

function fail(message) {
  throw new Error(message);
}

function staticChecks() {
  const hooksPath = join(repoRoot, "src-tauri", "windows", "nsis-hooks.nsh");
  const hooks = readFileSync(hooksPath, "utf8");
  for (const required of ["jhm-sidecar-next.exe", "backend.exe", "$INSTDIR\\_internal", "taskkill.exe"]) {
    if (!hooks.includes(required)) {
      fail(`NSIS preinstall hook is missing ${required}`);
    }
  }
  const tauriConfigPath = join(repoRoot, "src-tauri", "tauri.conf.json");
  const tauriConfig = JSON.parse(readFileSync(tauriConfigPath, "utf8"));
  const installMode = tauriConfig.plugins?.updater?.windows?.installMode;
  if (installMode !== "quiet") {
    fail(`Windows updater installMode must stay quiet; found ${installMode || "missing"}.`);
  }
  console.log("Windows update static smoke passed.");
  console.log("Set JHM_WINDOWS_INSTALLER_SMOKE=1 with JHM_NEW_INSTALLER for installed package smoke.");
  console.log("Set JHM_WINDOWS_UPDATE_SMOKE=1 with JHM_OLD_INSTALLER and JHM_NEW_INSTALLER for installer-over-existing smoke.");
}

function localVectorRuntimeArchive() {
  return join(repoRoot, "release-assets", "JustHireMe-vector-runtime-windows.zip");
}

function localVectorRuntimeUrl() {
  return pathToFileURL(localVectorRuntimeArchive()).href;
}

function resolveInstaller(envName) {
  const raw = process.env[envName] || "";
  if (!raw) fail(`${envName} is required.`);
  const installer = resolve(raw);
  if (!existsSync(installer)) fail(`${envName} not found: ${installer}`);
  return installer;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    windowsHide: true,
    ...options,
  });
  if (result.status !== 0) {
    fail(`${command} ${args.join(" ")} exited with ${result.status}`);
  }
}

function killImage(name) {
  if (process.platform !== "win32") return;
  spawnSync("taskkill", ["/IM", name, "/T", "/F"], { stdio: "ignore", windowsHide: true });
}

function killProcessTree(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
  } else {
    child.kill("SIGTERM");
  }
}

function remove(path) {
  rmSync(path, {
    recursive: true,
    force: true,
    maxRetries: 20,
    retryDelay: 750,
  });
}

function isRetryableRemoveError(error) {
  return ["EBUSY", "EPERM", "ENOTEMPTY", "EACCES"].includes(error?.code);
}

async function removeWithRetry(path, options = {}) {
  let lastError = null;
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    try {
      remove(path);
      return true;
    } catch (error) {
      lastError = error;
      if (!isRetryableRemoveError(error)) break;
      await sleep(Math.min(500 * attempt, 2500));
    }
  }
  if (options.allowFailure) {
    console.warn(`Cleanup warning for ${options.label || path}: ${lastError?.message || lastError}`);
    return false;
  }
  throw lastError;
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

function waitForChildClose(child, ms) {
  if (!child || child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve(true);
  }
  return new Promise((resolveWait) => {
    const timer = setTimeout(() => {
      child.off("close", onClose);
      child.off("exit", onClose);
      resolveWait(false);
    }, ms);
    function onClose() {
      clearTimeout(timer);
      resolveWait(true);
    }
    child.once("close", onClose);
    child.once("exit", onClose);
  });
}

function waitForHandshake(child, stdoutLines, stderrLines) {
  const handshake = { token: "", port: 0 };
  let stdoutRemainder = "";
  let stderrRemainder = "";
  return new Promise((resolveWait, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Sidecar handshake timed out.\nstdout:\n${stdoutLines.join("\n")}\nstderr:\n${stderrLines.join("\n")}`));
    }, timeoutMs);

    child.stdout.on("data", (chunk) => {
      stdoutRemainder += chunk.toString();
      const lines = stdoutRemainder.split(/\r?\n/);
      stdoutRemainder = lines.pop() || "";
      for (const line of lines) {
        stdoutLines.push(line);
        const trimmed = line.trim();
        if (trimmed.startsWith("JHM_TOKEN=")) handshake.token = trimmed.slice("JHM_TOKEN=".length);
        if (trimmed.startsWith("PORT:")) handshake.port = Number(trimmed.slice("PORT:".length));
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
      stderrLines.push(...lines);
    });

    child.on("exit", (code, signal) => {
      if (!handshake.token || !handshake.port) {
        clearTimeout(timer);
        reject(new Error(`Sidecar exited before handshake: code=${code} signal=${signal}`));
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
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    } catch (error) {
      lastError = error;
      await sleep(500);
    }
  }
  throw lastError || new Error("health timeout");
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

async function requestShutdown(port, token) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/v1/shutdown`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      console.warn(`/api/v1/shutdown returned HTTP ${response.status}: ${await response.text()}`);
    }
  } catch (error) {
    console.warn(`Could not request graceful sidecar shutdown: ${error.message}`);
  }
}

async function stopSidecar(child, handshake) {
  if (handshake?.port && handshake?.token) {
    await requestShutdown(handshake.port, handshake.token);
  }
  const closedCleanly = await waitForChildClose(child, 15_000);
  if (!closedCleanly) {
    killProcessTree(child);
    await waitForChildClose(child, 5_000);
  }
  await sleep(1000);
}

function requireHealth(health, options = {}) {
  const components = health.components || health.checks || {};
  const rawApp = components.app?.status || health.status;
  if (!["ok", "alive"].includes(rawApp)) fail(`App health is ${rawApp || "missing"}`);
  if (components.sqlite?.status !== "ok") fail(`SQLite health is ${components.sqlite?.status || "missing"}`);
  if (components.graph?.status !== "ok") fail(`Graph health is ${components.graph?.status || "missing"}`);
  if (options.vectorRequired && components.vector?.status !== "ok") fail(`Vector health is ${components.vector?.status || "missing"}`);
  return {
    app: rawApp === "alive" ? "ok" : rawApp,
    sqlite: components.sqlite.status,
    graph: components.graph.status,
    vector: components.vector.status,
  };
}

async function ensureVectorRuntime(port, token) {
  const archive = localVectorRuntimeArchive();
  const initial = await readApi(port, token, "/api/v1/runtime/vector");
  if (initial.ready) return initial;
  if (!existsSync(archive)) {
    console.warn(`Vector runtime archive not found at ${archive}; installed package semantic OTA smoke skipped.`);
    return initial;
  }
  const installed = await readApi(port, token, "/api/v1/runtime/vector/install", { method: "POST" });
  if (!installed.ready) fail(`Vector runtime install did not become ready: ${JSON.stringify(installed)}`);
  return installed;
}

async function smokeInstalledSidecar(installDir, appDataDir) {
  const sidecar = join(installDir, "jhm-sidecar-next.exe");
  const runtime = join(installDir, "_internal");
  if (!existsSync(sidecar)) fail(`Missing installed sidecar: ${sidecar}`);
  if (!existsSync(join(runtime, "python313.dll"))) fail(`Missing installed runtime DLL: ${join(runtime, "python313.dll")}`);
  if (!existsSync(join(runtime, "base_library.zip"))) fail(`Missing installed Python library: ${join(runtime, "base_library.zip")}`);

  await removeWithRetry(appDataDir);
  mkdirSync(appDataDir, { recursive: true });
  const stdoutLines = [];
  const stderrLines = [];
  const child = spawn(sidecar, ["--no-services"], {
    cwd: installDir,
    env: {
      ...process.env,
      JHM_APP_DATA_DIR: appDataDir,
      JHM_VECTOR_RUNTIME_DIR: join(appDataDir, "vector-runtime"),
      JHM_VECTOR_RUNTIME_URL: localVectorRuntimeUrl(),
      LOCALAPPDATA: appDataDir,
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  let handshake = null;
  try {
    handshake = await waitForHandshake(child, stdoutLines, stderrLines);
    const health = await readHealth(handshake.port, handshake.token);
    const summary = requireHealth(health);
    const runtime = await ensureVectorRuntime(handshake.port, handshake.token);
    const runtimeHealth = await readHealth(handshake.port, handshake.token);
    const runtimeSummary = requireHealth(runtimeHealth, { vectorRequired: runtime.ready });
    console.log(`Installed sidecar health passed: app=${summary.app}, sqlite=${summary.sqlite}, graph=${summary.graph}, vector=${runtimeSummary.vector || summary.vector}`);
  } finally {
    await stopSidecar(child, handshake);
  }
}

function newSmokeRoot(prefix) {
  return join(repoRoot, ".codex-temp-sidecar", `${prefix}-${Date.now()}-${process.pid}`);
}

async function freshInstallerSmoke() {
  if (process.platform !== "win32") {
    fail("Installed Windows package smoke must run on Windows.");
  }
  const newInstaller = resolveInstaller("JHM_NEW_INSTALLER");

  const root = newSmokeRoot("windows-installer-smoke");
  const installDir = join(root, "install");
  const appDataDir = join(root, "appdata");
  await removeWithRetry(root);
  mkdirSync(installDir, { recursive: true });
  mkdirSync(appDataDir, { recursive: true });

  try {
    run(newInstaller, ["/S", `/D=${installDir}`]);
    await smokeInstalledSidecar(installDir, appDataDir);
    console.log(`Windows installed package smoke passed: ${installDir}`);
  } finally {
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    killImage("backend.exe");
    await removeWithRetry(root, { allowFailure: true, label: "Windows installed package smoke temp dir" });
  }
}

async function updateInstallerSmoke() {
  if (process.platform !== "win32") {
    fail("Installer-over-existing smoke must run on Windows.");
  }
  const oldInstaller = resolveInstaller("JHM_OLD_INSTALLER");
  const newInstaller = resolveInstaller("JHM_NEW_INSTALLER");

  const root = newSmokeRoot("windows-update-smoke");
  const installDir = join(root, "install");
  const appDataDir = join(root, "appdata");
  await removeWithRetry(root);
  mkdirSync(installDir, { recursive: true });
  mkdirSync(appDataDir, { recursive: true });

  try {
    run(oldInstaller, ["/S", `/D=${installDir}`]);
    const app = join(installDir, "justhireme.exe");
    let appProcess = null;
    if (existsSync(app)) {
      appProcess = spawn(app, [], {
        cwd: installDir,
        env: { ...process.env, JHM_APP_DATA_DIR: appDataDir, LOCALAPPDATA: appDataDir },
        stdio: "ignore",
        windowsHide: true,
      });
      await sleep(5000);
    }

    run(newInstaller, ["/S", `/D=${installDir}`]);
    if (appProcess && appProcess.exitCode === null) {
      killProcessTree(appProcess);
      await waitForChildClose(appProcess, 5_000);
    }
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    await smokeInstalledSidecar(installDir, appDataDir);
    console.log(`Windows installer-over-existing smoke passed: ${installDir}`);
  } finally {
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    killImage("backend.exe");
    await removeWithRetry(root, { allowFailure: true, label: "Windows update smoke temp dir" });
  }
}

if (updateSmokeEnabled) {
  await updateInstallerSmoke();
} else if (installerSmokeEnabled) {
  await freshInstallerSmoke();
} else {
  staticChecks();
}
