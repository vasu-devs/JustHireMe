import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = join(repoRoot, "backend");
const pythonVersion = readFileSync(join(backendDir, ".python-version"), "utf8").trim();
const sitePackages = process.platform === "win32"
  ? join(backendDir, ".venv", "Lib", "site-packages")
  : join(backendDir, ".venv", "lib", `python${pythonVersion}`, "site-packages");
const stageRoot = join(repoRoot, ".codex-temp-vector-runtime");
const stageDir = join(stageRoot, "vector-runtime");
const releaseAssetsDir = join(repoRoot, "release-assets");

const entries = [
  "lancedb",
  "lance_namespace",
  "lance_namespace_urllib3_client",
  "pyarrow",
  "pyarrow.libs",
  "numpy",
  "numpy.libs",
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

const distInfoPrefixes = [
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
  cpSync(source, join(stageDir, name), { recursive: true, filter: copyFilter });
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
    shell: false,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} exited with code ${result.status}`);
  }
}

if (!existsSync(sitePackages)) {
  throw new Error(`Python site-packages not found: ${sitePackages}`);
}

rmSync(stageRoot, { recursive: true, force: true });
mkdirSync(stageDir, { recursive: true });
mkdirSync(releaseAssetsDir, { recursive: true });

for (const entry of entries) {
  copyEntry(entry);
}

for (const prefix of distInfoPrefixes) {
  const matches = matchingDistInfos(prefix);
  if (matches.length === 0) {
    throw new Error(`Required vector runtime metadata is missing for prefix: ${prefix}`);
  }
  for (const match of matches) {
    copyEntry(match);
  }
}

writeFileSync(join(stageDir, "vector-runtime-manifest.json"), `${JSON.stringify({
  platform: platformName(),
  builtAt: new Date().toISOString(),
  source: "backend/.venv/site-packages",
  packages: entries,
}, null, 2)}\n`, "utf8");

const archivePath = join(releaseAssetsDir, `JustHireMe-vector-runtime-${platformName()}.zip`);
rmSync(archivePath, { force: true });

if (process.platform === "win32") {
  const command = [
    "$ErrorActionPreference = 'Stop'",
    `$source = Join-Path ${psQuote(stageDir)} '*'`,
    `Compress-Archive -Path $source -DestinationPath ${psQuote(archivePath)} -Force`,
  ].join("; ");
  run("powershell.exe", ["-NoProfile", "-Command", command]);
} else {
  run("zip", ["-qr", archivePath, "."], { cwd: stageDir });
}

console.log(`Vector runtime asset ready: ${archivePath}`);
console.log(`Vector runtime uncompressed size: ${formatMb(bytes(stageDir))}`);
console.log(`Vector runtime archive size: ${formatMb(bytes(archivePath))}`);
