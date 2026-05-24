import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const updateSmokeEnabled = process.env.JHM_WINDOWS_UPDATE_SMOKE === "1";
const installerSmokeEnabled = process.env.JHM_WINDOWS_INSTALLER_SMOKE === "1";
const timeoutMs = Number(process.env.JHM_WINDOWS_UPDATE_TIMEOUT_MS || 120_000);
// Hard cap on a single silent NSIS install so a stuck installer (e.g. blocked
// on a locked binary) fails fast instead of hanging the job for hours.
const installerTimeoutMs = Number(process.env.JHM_WINDOWS_INSTALLER_TIMEOUT_MS || 480_000);
const uninstallRegistryKeySuffix = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JustHireMe";
const vendorRegistryKeySuffix = "Software\\vasudev-siddh\\JustHireMe";
const uninstallRegistryKey = `HKCU\\${uninstallRegistryKeySuffix}`;

function fail(message) {
  throw new Error(message);
}

function staticChecks() {
  const hooksPath = join(repoRoot, "src-tauri", "windows", "nsis-hooks.nsh");
  const hooks = readFileSync(hooksPath, "utf8");
  for (const required of ["jhm-sidecar-next.exe", "backend.exe", "taskkill.exe"]) {
    if (!hooks.includes(required)) {
      fail(`NSIS preinstall hook is missing ${required}`);
    }
  }
  if (!hooks.includes("$INSTDIR\\_internal")) {
    fail("NSIS preinstall hook must remove stale _internal directories from old onedir releases.");
  }
  if (!hooks.includes("NSIS_HOOK_POSTINSTALL")) {
    fail("NSIS postinstall hook must repair Windows install metadata.");
  }
  for (const required of ["CreateShortCut", "DisplayVersion", "InstallLocation", "QuietUninstallString", "User Pinned\\TaskBar"]) {
    if (!hooks.includes(required)) {
      fail(`NSIS postinstall hook is missing ${required}.`);
    }
  }
  if (!hooks.includes("SetOutPath \"$INSTDIR\"")) {
    fail("NSIS postinstall hook must set the shortcut working directory to the install dir.");
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
  if (process.env.JHM_SMOKE_RUNTIME_PACK_ARCHIVE) {
    return process.env.JHM_SMOKE_RUNTIME_PACK_ARCHIVE;
  }
  const runtimePack = join(repoRoot, "release-assets", "JustHireMe-runtime-pack-windows.zip");
  return existsSync(runtimePack)
    ? runtimePack
    : join(repoRoot, "release-assets", "JustHireMe-vector-runtime-windows.zip");
}

function localRuntimePackUrl() {
  return pathToFileURL(localVectorRuntimeArchive()).href;
}

function resolveInstaller(envName) {
  const raw = process.env[envName] || "";
  if (!raw) fail(`${envName} is required.`);
  const installer = resolve(raw);
  if (!existsSync(installer)) fail(`${envName} not found: ${installer}`);
  return installer;
}

function expectedVersionFromInstaller(installer) {
  const explicit = process.env.JHM_EXPECTED_VERSION || "";
  if (explicit) return explicit;
  return basename(installer).match(/_(\d+\.\d+\.\d+)(?:[_-]|\.exe$)/i)?.[1] || "";
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    windowsHide: true,
    ...options,
  });
  if (result.error) {
    // Includes ETIMEDOUT when a `timeout` option is hit — surface it clearly
    // rather than reporting a confusing null exit status.
    fail(`${command} ${args.join(" ")} failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    fail(`${command} ${args.join(" ")} exited with ${result.status}`);
  }
}

function runQuiet(command, args) {
  return spawnSync(command, args, {
    stdio: "ignore",
    windowsHide: true,
  });
}

function registryKeyExists(key) {
  if (process.platform !== "win32") return false;
  return runQuiet("reg", ["query", key]).status === 0;
}

function findProfileSid() {
  if (process.platform !== "win32" || !process.env.USERPROFILE) return "";
  const result = spawnSync("reg", ["query", "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList", "/s", "/v", "ProfileImagePath"], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) return "";

  const expected = normalizeFsPath(process.env.USERPROFILE);
  let currentKey = "";
  for (const line of result.stdout.split(/\r?\n/)) {
    const keyMatch = line.match(/^HKEY_LOCAL_MACHINE\\.+\\([^\\]+)$/i);
    if (keyMatch) {
      currentKey = keyMatch[1];
      continue;
    }
    const valueMatch = line.match(/^\s*ProfileImagePath\s+REG_\w+\s+(.+)$/i);
    if (valueMatch && currentKey && normalizeFsPath(valueMatch[1]) === expected) {
      return currentKey;
    }
  }
  return "";
}

function smokeRegistryKeys() {
  if (process.platform !== "win32") return [];
  const roots = ["HKCU"];
  const profileSid = findProfileSid();
  if (profileSid) roots.push(`HKEY_USERS\\${profileSid}`);
  return [...new Set(roots.flatMap((root) => [
    `${root}\\${uninstallRegistryKeySuffix}`,
    `${root}\\${vendorRegistryKeySuffix}`,
  ]))];
}

function snapshotRegistryFiles(root) {
  if (process.platform !== "win32") return null;
  const snapshotDir = join(root, "registry-snapshot");
  mkdirSync(snapshotDir, { recursive: true });
  return smokeRegistryKeys().map((key, index) => {
    const snapshot = join(snapshotDir, `${index}.reg`);
    const existed = registryKeyExists(key);
    if (!existed) return { key, snapshot, existed: false };

    const result = runQuiet("reg", ["export", key, snapshot, "/y"]);
    if (result.status !== 0) {
      fail(`Could not snapshot existing registry key before smoke: ${key}`);
    }
    return { key, snapshot, existed: true };
  });
}

function windowsShortcutPaths() {
  if (process.platform !== "win32") return [];
  return [
    join(process.env.APPDATA || "", "Microsoft", "Windows", "Start Menu", "Programs", "JustHireMe.lnk"),
    join(process.env.USERPROFILE || "", "Desktop", "JustHireMe.lnk"),
    join(process.env.APPDATA || "", "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar", "JustHireMe.lnk"),
  ].filter(Boolean);
}

function snapshotShortcutFiles(root) {
  if (process.platform !== "win32") return [];
  const snapshotDir = join(root, "shortcut-snapshot");
  mkdirSync(snapshotDir, { recursive: true });
  return windowsShortcutPaths().map((shortcut, index) => {
    const backup = join(snapshotDir, `${index}.lnk`);
    const existed = existsSync(shortcut);
    if (existed) copyFileSync(shortcut, backup);
    return { shortcut, backup, existed };
  });
}

function restoreShortcutFiles(records) {
  if (process.platform !== "win32") return;
  for (const record of records) {
    if (record.existed && existsSync(record.backup)) {
      mkdirSync(dirname(record.shortcut), { recursive: true });
      copyFileSync(record.backup, record.shortcut);
    } else {
      rmSync(record.shortcut, { force: true });
    }
  }
}

function restoreRegistryFiles(records) {
  if (process.platform !== "win32") return;
  for (const record of records || []) {
    if (record.existed && existsSync(record.snapshot)) {
      const result = runQuiet("reg", ["import", record.snapshot]);
      if (result.status !== 0) {
        console.warn(`Cleanup warning: could not restore previous registry entry ${record.key}.`);
      }
      continue;
    }
    if (registryKeyExists(record.key)) {
      runQuiet("reg", ["delete", record.key, "/f"]);
    }
  }
}

function stripOuterQuotes(value) {
  return String(value || "").trim().replace(/^"|"$/g, "");
}

function normalizeFsPath(value) {
  return resolve(stripOuterQuotes(value)).toLowerCase();
}

function readRegistryValue(name) {
  if (process.platform !== "win32") return "";
  const result = spawnSync("reg", ["query", uninstallRegistryKey, "/v", name], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) return "";
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`^\\s*${escaped}\\s+REG_\\w+\\s+(.+)$`, "im");
  return stripOuterQuotes(result.stdout.match(pattern)?.[1] || "");
}

function readShortcutTarget(shortcut) {
  const script = `$s=(New-Object -ComObject WScript.Shell).CreateShortcut('${shortcut.replace(/'/g, "''")}'); [Console]::Out.Write($s.TargetPath)`;
  const result = spawnSync("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    fail(`Could not inspect shortcut ${shortcut}: ${result.stderr || result.stdout}`);
  }
  return stripOuterQuotes(result.stdout);
}

function assertInstalledMetadata(installDir, expectedVersion = "") {
  if (process.platform !== "win32") return;
  const expectedApp = join(installDir, "justhireme.exe");
  if (!existsSync(expectedApp)) {
    fail(`Installed app executable is missing: ${expectedApp}`);
  }
  const installLocation = readRegistryValue("InstallLocation");
  if (normalizeFsPath(installLocation) !== normalizeFsPath(installDir)) {
    fail(`Registry InstallLocation points to ${installLocation || "(missing)"}, expected ${installDir}.`);
  }
  if (expectedVersion) {
    const displayVersion = readRegistryValue("DisplayVersion");
    if (displayVersion !== expectedVersion) {
      fail(`Registry DisplayVersion is ${displayVersion || "(missing)"}, expected ${expectedVersion}.`);
    }
  }
  const uninstallString = readRegistryValue("UninstallString");
  if (!normalizeFsPath(uninstallString.replace(/\\uninstall\.exe.*$/i, "")).startsWith(normalizeFsPath(installDir))) {
    fail(`Registry UninstallString points outside the install dir: ${uninstallString || "(missing)"}.`);
  }

  const shortcuts = windowsShortcutPaths();
  const startMenuShortcut = shortcuts[0];
  if (!existsSync(startMenuShortcut)) {
    fail(`Missing Start Menu shortcut: ${startMenuShortcut}`);
  }
  for (const shortcut of shortcuts) {
    if (!existsSync(shortcut)) continue;
    const target = readShortcutTarget(shortcut);
    if (normalizeFsPath(target) !== normalizeFsPath(expectedApp)) {
      fail(`Shortcut ${shortcut} points to ${target || "(missing)"}, expected ${expectedApp}.`);
    }
    if (!existsSync(target)) {
      fail(`Shortcut ${shortcut} points to missing executable: ${target || "(missing)"}.`);
    }
  }
}

async function cleanupInstalledPackage(installDir, registrySnapshots) {
  if (process.platform !== "win32") return;
  const uninstaller = join(installDir, "uninstall.exe");
  if (existsSync(uninstaller)) {
    const result = runQuiet(uninstaller, ["/S"]);
    if (result.status !== 0) {
      console.warn(`Cleanup warning: JustHireMe uninstaller exited with ${result.status}.`);
    }
    await sleep(2500);
  }
  restoreRegistryFiles(registrySnapshots);
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
    console.warn(`Runtime pack archive not found at ${archive}; installed package OTA smoke skipped.`);
    return initial;
  }
  await readApi(port, token, "/api/v1/runtime/vector/install", { method: "POST" });
  const deadline = Date.now() + 90_000;
  let last = initial;
  while (Date.now() < deadline) {
    last = await readApi(port, token, "/api/v1/runtime/vector");
    if (last.ready) return last;
    if (last.progress?.status === "error") fail(`Runtime pack install failed: ${JSON.stringify(last)}`);
    await sleep(500);
  }
  fail(`Runtime pack install did not become ready: ${JSON.stringify(last)}`);
}

async function smokeInstalledSidecar(installDir, appDataDir) {
  const sidecar = join(installDir, "jhm-sidecar-next.exe");
  const runtime = join(installDir, "_internal");
  if (!existsSync(sidecar)) fail(`Missing installed sidecar: ${sidecar}`);
  if (existsSync(runtime)) fail(`Slim installer must not include bundled PyInstaller runtime directory: ${runtime}`);

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
      JHM_RUNTIME_PACK_URL: localRuntimePackUrl(),
      JHM_VECTOR_RUNTIME_URL: localRuntimePackUrl(),
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
  const expectedVersion = expectedVersionFromInstaller(newInstaller);

  const root = newSmokeRoot("windows-installer-smoke");
  const installDir = join(root, "install");
  const appDataDir = join(root, "appdata");
  await removeWithRetry(root);
  mkdirSync(installDir, { recursive: true });
  mkdirSync(appDataDir, { recursive: true });
  const registrySnapshot = snapshotRegistryFiles(root);
  const shortcutSnapshot = snapshotShortcutFiles(root);

  try {
    run(newInstaller, ["/S", `/D=${installDir}`]);
    assertInstalledMetadata(installDir, expectedVersion);
    await smokeInstalledSidecar(installDir, appDataDir);
    console.log(`Windows installed package smoke passed: ${installDir}`);
  } finally {
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    killImage("backend.exe");
    await cleanupInstalledPackage(installDir, registrySnapshot);
    restoreShortcutFiles(shortcutSnapshot);
    await sleep(3000);
    restoreRegistryFiles(registrySnapshot);
    await removeWithRetry(root, { allowFailure: true, label: "Windows installed package smoke temp dir" });
  }
}

async function updateInstallerSmoke() {
  if (process.platform !== "win32") {
    fail("Installer-over-existing smoke must run on Windows.");
  }
  const oldInstaller = resolveInstaller("JHM_OLD_INSTALLER");
  const newInstaller = resolveInstaller("JHM_NEW_INSTALLER");
  const expectedVersion = expectedVersionFromInstaller(newInstaller);

  const root = newSmokeRoot("windows-update-smoke");
  const installDir = join(root, "install");
  const appDataDir = join(root, "appdata");
  await removeWithRetry(root);
  mkdirSync(installDir, { recursive: true });
  mkdirSync(appDataDir, { recursive: true });
  const registrySnapshot = snapshotRegistryFiles(root);
  const shortcutSnapshot = snapshotShortcutFiles(root);

  try {
    run(oldInstaller, ["/S", `/D=${installDir}`], { timeout: installerTimeoutMs });
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

    // Stop the previous version (app + sidecar) BEFORE upgrading. Otherwise the
    // new installer blocks indefinitely trying to overwrite the still-running,
    // file-locked sidecar binary — which hung this smoke for 45+ minutes.
    if (appProcess && appProcess.exitCode === null) {
      killProcessTree(appProcess);
      await waitForChildClose(appProcess, 5_000);
    }
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    await sleep(1000);

    run(newInstaller, ["/S", `/D=${installDir}`], { timeout: installerTimeoutMs });
    assertInstalledMetadata(installDir, expectedVersion);
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    await smokeInstalledSidecar(installDir, appDataDir);
    console.log(`Windows installer-over-existing smoke passed: ${installDir}`);
  } finally {
    killImage("justhireme.exe");
    killImage("jhm-sidecar-next.exe");
    killImage("backend.exe");
    await cleanupInstalledPackage(installDir, registrySnapshot);
    restoreShortcutFiles(shortcutSnapshot);
    await sleep(3000);
    restoreRegistryFiles(registrySnapshot);
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
