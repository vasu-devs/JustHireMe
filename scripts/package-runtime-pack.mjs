import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = join(repoRoot, "backend");
const pythonVersion = readFileSync(join(backendDir, ".python-version"), "utf8").trim();
const python = process.platform === "win32"
  ? join(backendDir, ".venv", "Scripts", "python.exe")
  : join(backendDir, ".venv", "bin", "python");
const sitePackages = process.platform === "win32"
  ? join(backendDir, ".venv", "Lib", "site-packages")
  : join(backendDir, ".venv", "lib", `python${pythonVersion}`, "site-packages");
const browserRuntimeSource = join(repoRoot, "src-tauri", "resources", "bin", "ms-playwright");
const stageRoot = join(repoRoot, ".codex-temp-runtime-pack");
const stageDir = join(stageRoot, "runtime-pack");
const vectorStageDir = join(stageDir, "vector-runtime");
const browserStageDir = join(stageDir, "browser-runtime", "ms-playwright");
const releaseAssetsDir = join(repoRoot, "release-assets");

const vectorEntries = [
  "lancedb",
  "lance_namespace",
  "lance_namespace_urllib3_client",
  "pyarrow",
  "numpy",
  "packaging",
  "pydantic",
  "pydantic_core",
  "tqdm",
  "dateutil",
  "typing_inspection",
  "annotated_doc",
  "annotated_types",
  "urllib3",
  "deprecation.py",
  "typing_extensions.py",
  "six.py",
];

const optionalVectorEntries = [
  "pyarrow.libs",
  "numpy.libs",
];

const vectorDistInfoPrefixes = [
  "lancedb-",
  "lance_namespace-",
  "lance_namespace_urllib3_client-",
  "pyarrow-",
  "numpy-",
  "packaging-",
  "pydantic-",
  "pydantic_core-",
  "tqdm-",
  "python_dateutil-",
  "typing_inspection-",
  "annotated_doc-",
  "annotated_types-",
  "urllib3-",
  "deprecation-",
  "typing_extensions-",
  "six-",
];

function platformName() {
  if (process.platform === "win32") return "windows";
  if (process.platform === "darwin") return "macos";
  return "linux";
}

function runtimePackAssetName() {
  return `JustHireMe-runtime-pack-${platformName()}.zip`;
}

function vectorRuntimeAssetName() {
  return `JustHireMe-vector-runtime-${platformName()}.zip`;
}

function browserRuntimeAssetName() {
  return `JustHireMe-browser-runtime-${platformName()}.zip`;
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

function copyFilter(source) {
  const name = source.split(/[\\/]/).pop()?.toLowerCase() || "";
  if (name === "__pycache__" || name === "tests" || name === "test") return false;
  if (name.endsWith(".pyc") || name.endsWith(".pyo")) return false;
  return true;
}

function copyEntry(name) {
  const source = join(sitePackages, name);
  if (!existsSync(source)) {
    throw new Error(`Required vector runtime entry is missing: ${source}`);
  }
  cpSync(source, join(vectorStageDir, name), { recursive: true, filter: copyFilter });
}

function matchingDistInfos(prefix) {
  return readdirSync(sitePackages)
    .filter(name => name.startsWith(prefix) && (name.endsWith(".dist-info") || name.endsWith(".egg-info")));
}

function psQuote(value) {
  return `'${value.replace(/'/g, "''")}'`;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || repoRoot,
    env: options.env || process.env,
    shell: false,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} exited with code ${result.status}`);
  }
}

function archiveDirectory(sourceDir, archivePath) {
  rmSync(archivePath, { force: true });
  if (process.platform === "win32") {
    const command = [
      "$ErrorActionPreference = 'Stop'",
      `$source = Join-Path ${psQuote(sourceDir)} '*'`,
      `Compress-Archive -Path $source -DestinationPath ${psQuote(archivePath)} -Force`,
    ].join("; ");
    run("powershell.exe", ["-NoProfile", "-Command", command]);
  } else {
    run("zip", ["-qr", archivePath, "."], { cwd: sourceDir });
  }
}

function hasChromiumRuntime() {
  if (!existsSync(browserRuntimeSource)) {
    return false;
  }
  return readdirSync(browserRuntimeSource, { withFileTypes: true })
    .some((entry) => entry.isDirectory() && entry.name.toLowerCase().startsWith("chromium"));
}

function installBrowserRuntime() {
  if (!existsSync(python)) {
    throw new Error(`Python virtual environment not found: ${python}`);
  }
  mkdirSync(browserRuntimeSource, { recursive: true });
  console.log(`Installing Playwright Chromium runtime: ${browserRuntimeSource}`);
  run(python, ["-m", "playwright", "install", "chromium"], {
    cwd: backendDir,
    env: {
      ...process.env,
      PLAYWRIGHT_BROWSERS_PATH: browserRuntimeSource,
      PYTHONNOUSERSITE: "1",
    },
  });
}

function assertBrowserRuntimeReady() {
  if (!hasChromiumRuntime()) {
    installBrowserRuntime();
  }
  if (!hasChromiumRuntime()) {
    throw new Error(`Playwright Chromium runtime does not contain a Chromium payload: ${browserRuntimeSource}`);
  }
}

if (!existsSync(sitePackages)) {
  throw new Error(`Python site-packages not found: ${sitePackages}`);
}

assertBrowserRuntimeReady();

rmSync(stageRoot, { recursive: true, force: true });
mkdirSync(vectorStageDir, { recursive: true });
mkdirSync(browserStageDir, { recursive: true });
mkdirSync(releaseAssetsDir, { recursive: true });

for (const entry of vectorEntries) {
  copyEntry(entry);
}

for (const entry of optionalVectorEntries) {
  if (existsSync(join(sitePackages, entry))) {
    copyEntry(entry);
  }
}

for (const prefix of vectorDistInfoPrefixes) {
  const matches = matchingDistInfos(prefix);
  if (matches.length === 0) {
    throw new Error(`Required vector runtime metadata is missing for prefix: ${prefix}`);
  }
  for (const match of matches) {
    copyEntry(match);
  }
}

cpSync(browserRuntimeSource, browserStageDir, {
  recursive: true,
  filter: (source) => {
    const name = source.split(/[\\/]/).pop()?.toLowerCase() || "";
    if (name === ".links" || name === "__pycache__") return false;
    if (name.startsWith("chromium_headless_shell")) return false;
    if (name.startsWith("ffmpeg-")) return false;
    if (name.startsWith("winldd-")) return false;
    return true;
  },
});

writeFileSync(join(vectorStageDir, "vector-runtime-manifest.json"), `${JSON.stringify({
  platform: platformName(),
  builtAt: new Date().toISOString(),
  source: "backend/.venv/site-packages",
  packages: vectorEntries,
}, null, 2)}\n`, "utf8");

writeFileSync(join(stageDir, "runtime-pack-manifest.json"), `${JSON.stringify({
  platform: platformName(),
  builtAt: new Date().toISOString(),
  source: "GitHub Actions release build",
  components: {
    vector: {
      path: "vector-runtime",
      packages: vectorEntries,
    },
    browser: {
      path: "browser-runtime/ms-playwright",
      package: "Playwright Chromium",
      optimization: "full Chromium executable only; Playwright headless-shell, ffmpeg, and install helpers are excluded",
    },
    embeddings: {
      mode: "built-in local embedder",
      externalDownloadRequired: false,
    },
  },
}, null, 2)}\n`, "utf8");

const runtimePackArchive = join(releaseAssetsDir, runtimePackAssetName());
const vectorArchive = join(releaseAssetsDir, vectorRuntimeAssetName());
const browserArchive = join(releaseAssetsDir, browserRuntimeAssetName());

archiveDirectory(stageDir, runtimePackArchive);
archiveDirectory(vectorStageDir, vectorArchive);
archiveDirectory(join(repoRoot, "src-tauri", "resources", "bin"), browserArchive);

console.log(`Runtime pack asset ready: ${runtimePackArchive}`);
console.log(`Runtime pack uncompressed size: ${formatMb(bytes(stageDir))}`);
console.log(`Runtime pack archive size: ${formatMb(bytes(runtimePackArchive))}`);
console.log(`Legacy vector runtime asset ready: ${vectorArchive} (${formatMb(bytes(vectorArchive))})`);
console.log(`Legacy browser runtime asset ready: ${browserArchive} (${formatMb(bytes(browserArchive))})`);
