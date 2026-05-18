import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const enabled = process.env.JHM_WINDOWS_UPDATE_SMOKE === "1";
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
  console.log("Windows update static smoke passed.");
  console.log("Set JHM_WINDOWS_UPDATE_SMOKE=1 with JHM_OLD_INSTALLER and JHM_NEW_INSTALLER for installer-over-existing smoke.");
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
  spawnSync("taskkill", ["/IM", name, "/T", "/F"], { stdio: "ignore", windowsHide: true });
}

function remove(path) {
  rmSync(path, { recursive: true, force: true });
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
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

async function smokeInstalledSidecar(installDir, appDataDir) {
  const sidecar = join(installDir, "jhm-sidecar-next.exe");
  const runtime = join(installDir, "_internal");
  if (!existsSync(sidecar)) fail(`Missing installed sidecar: ${sidecar}`);
  if (!existsSync(join(runtime, "python313.dll"))) fail(`Missing installed runtime DLL: ${join(runtime, "python313.dll")}`);
  if (!existsSync(join(runtime, "base_library.zip"))) fail(`Missing installed Python library: ${join(runtime, "base_library.zip")}`);

  remove(appDataDir);
  mkdirSync(appDataDir, { recursive: true });
  const stdoutLines = [];
  const stderrLines = [];
  const child = spawn(sidecar, ["--no-services"], {
    cwd: installDir,
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
    const components = health.components || health.checks || {};
    if (components.sqlite?.status !== "ok") fail(`SQLite health is ${components.sqlite?.status || "missing"}`);
    if (components.graph?.status !== "ok") fail(`Graph health is ${components.graph?.status || "missing"}`);
    if (!["ok", "disabled"].includes(components.vector?.status)) fail(`Vector health is ${components.vector?.status || "missing"}`);
  } finally {
    if (child.exitCode === null) {
      spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
    }
  }
}

async function installerSmoke() {
  if (process.platform !== "win32") {
    fail("Installer-over-existing smoke must run on Windows.");
  }
  const oldInstallerRaw = process.env.JHM_OLD_INSTALLER || "";
  const newInstallerRaw = process.env.JHM_NEW_INSTALLER || "";
  if (!oldInstallerRaw) fail("JHM_OLD_INSTALLER is required when JHM_WINDOWS_UPDATE_SMOKE=1.");
  if (!newInstallerRaw) fail("JHM_NEW_INSTALLER is required when JHM_WINDOWS_UPDATE_SMOKE=1.");
  const oldInstaller = resolve(oldInstallerRaw);
  const newInstaller = resolve(newInstallerRaw);
  if (!existsSync(oldInstaller)) fail(`JHM_OLD_INSTALLER not found: ${oldInstaller}`);
  if (!existsSync(newInstaller)) fail(`JHM_NEW_INSTALLER not found: ${newInstaller}`);

  const root = join(repoRoot, ".codex-temp-sidecar", `windows-update-smoke-${Date.now()}-${process.pid}`);
  const installDir = join(root, "install");
  const appDataDir = join(root, "appdata");
  remove(root);
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
      spawnSync("taskkill", ["/PID", String(appProcess.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
    }
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    await smokeInstalledSidecar(installDir, appDataDir);
    console.log(`Windows installer-over-existing smoke passed: ${installDir}`);
  } finally {
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    killImage("backend.exe");
    remove(root);
  }
}

if (!enabled) {
  staticChecks();
} else {
  await installerSmoke();
}
