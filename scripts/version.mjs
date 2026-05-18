import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const versionPattern = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/;

const files = [
  {
    name: "package.json",
    path: join(repoRoot, "package.json"),
    read: jsonVersion,
    write: writeJsonVersion,
  },
  {
    name: "package-lock.json",
    path: join(repoRoot, "package-lock.json"),
    read: jsonVersion,
    write: writeJsonVersion,
  },
  {
    name: "website/package.json",
    path: join(repoRoot, "website", "package.json"),
    read: jsonVersion,
    write: writeJsonVersion,
  },
  {
    name: "website/package-lock.json",
    path: join(repoRoot, "website", "package-lock.json"),
    read: jsonVersion,
    write: writeJsonVersion,
  },
  {
    name: "src-tauri/tauri.conf.json",
    path: join(repoRoot, "src-tauri", "tauri.conf.json"),
    read: jsonVersion,
    write: writeJsonVersion,
  },
  {
    name: "src-tauri/Cargo.toml",
    path: join(repoRoot, "src-tauri", "Cargo.toml"),
    read: tomlVersion,
    write: writeTomlVersion,
  },
  {
    name: "src-tauri/Cargo.lock",
    path: join(repoRoot, "src-tauri", "Cargo.lock"),
    read: (path) => tomlPackageLockVersion(path, "justhireme"),
    write: (path, version) => writeTomlPackageLockVersion(path, "justhireme", version),
  },
  {
    name: "backend/pyproject.toml",
    path: join(repoRoot, "backend", "pyproject.toml"),
    read: tomlVersion,
    write: writeTomlVersion,
  },
  {
    name: "backend/uv.lock",
    path: join(repoRoot, "backend", "uv.lock"),
    read: (path) => tomlPackageLockVersion(path, "backend"),
    write: (path, version) => writeTomlPackageLockVersion(path, "backend", version),
  },
  {
    name: "backend/core/version.py",
    path: join(repoRoot, "backend", "core", "version.py"),
    read: pythonConstVersion,
    write: writePythonConstVersion,
  },
];

function readText(path) {
  return readFileSync(path, "utf8");
}

function writeText(path, text) {
  writeFileSync(path, text, "utf8");
}

function jsonVersion(path) {
  return JSON.parse(readText(path)).version;
}

function writeJsonVersion(path, version) {
  const data = JSON.parse(readText(path));
  data.version = version;
  if (data.packages?.[""]?.version) {
    data.packages[""].version = version;
  }
  writeText(path, `${JSON.stringify(data, null, 2)}\n`);
}

function tomlVersion(path) {
  const match = readText(path).match(/^version\s*=\s*"([^"]+)"/m);
  if (!match) {
    throw new Error(`Could not find package/project version in ${path}`);
  }
  return match[1];
}

function writeTomlVersion(path, version) {
  const text = readText(path);
  const next = text.replace(/^version\s*=\s*"[^"]+"/m, `version = "${version}"`);
  if (next === text) {
    if (tomlVersion(path) === version) {
      return;
    }
    throw new Error(`Could not update package/project version in ${path}`);
  }
  writeText(path, next);
}

function findTomlPackageBlock(text, packageName) {
  const starts = [...text.matchAll(/^\[\[package\]\]/gm)].map((match) => match.index);
  for (let i = 0; i < starts.length; i += 1) {
    const index = starts[i];
    const end = starts[i + 1] ?? text.length;
    const block = text.slice(index, end);
    if (new RegExp(`^name\\s*=\\s*"${packageName}"\\s*$`, "m").test(block)) {
      return { block, index };
    }
  }
  throw new Error(`Could not find ${packageName} package entry in lockfile`);
}

function tomlPackageLockVersion(path, packageName) {
  const { block } = findTomlPackageBlock(readText(path), packageName);
  const match = block.match(/^version\s*=\s*"([^"]+)"/m);
  if (!match) {
    throw new Error(`Could not find ${packageName} package version in ${path}`);
  }
  return match[1];
}

function writeTomlPackageLockVersion(path, packageName, version) {
  const text = readText(path);
  const { block, index } = findTomlPackageBlock(text, packageName);
  const nextBlock = block.replace(/^version\s*=\s*"[^"]+"/m, `version = "${version}"`);
  if (nextBlock === block) {
    if (tomlPackageLockVersion(path, packageName) === version) {
      return;
    }
    throw new Error(`Could not update ${packageName} package version in ${path}`);
  }
  writeText(path, `${text.slice(0, index)}${nextBlock}${text.slice(index + block.length)}`);
}

function pythonConstVersion(path) {
  const match = readText(path).match(/^APP_VERSION\s*=\s*"([^"]+)"/m);
  if (!match) {
    throw new Error(`Could not find APP_VERSION in ${path}`);
  }
  return match[1];
}

function writePythonConstVersion(path, version) {
  const text = readText(path);
  const next = text.replace(/^APP_VERSION\s*=\s*"[^"]+"/m, `APP_VERSION = "${version}"`);
  if (next === text) {
    if (pythonConstVersion(path) === version) {
      return;
    }
    throw new Error(`Could not update APP_VERSION in ${path}`);
  }
  writeText(path, next);
}

function normalizeVersion(raw) {
  const version = raw?.trim().replace(/^v/i, "");
  if (!versionPattern.test(version || "")) {
    throw new Error(`Invalid version "${raw}". Expected semver like 0.1.29 or v0.1.29.`);
  }
  return version;
}

function expectedVersionFromRef(refName) {
  if (!refName) {
    return null;
  }
  const version = refName.trim().replace(/^v/i, "");
  return versionPattern.test(version) ? refName : null;
}

function versions() {
  return files.map((file) => ({
    name: file.name,
    version: file.read(file.path),
  }));
}

function printVersions(rows) {
  for (const row of rows) {
    console.log(`${row.name}: ${row.version}`);
  }
}

function check(expectedRaw) {
  const expected = expectedRaw ? normalizeVersion(expectedRaw) : null;
  const rows = versions();
  const baseline = expected || rows[0].version;
  const mismatches = rows.filter((row) => row.version !== baseline);

  printVersions(rows);

  if (mismatches.length > 0) {
    const details = mismatches.map((row) => `${row.name}=${row.version}`).join(", ");
    throw new Error(`Version mismatch. Expected ${baseline}; mismatches: ${details}`);
  }
  if (expected && baseline !== expected) {
    throw new Error(`Version mismatch. Expected ${expected}; found ${baseline}`);
  }

  console.log(`Version check passed: ${baseline}`);
}

function bump(versionRaw) {
  const version = normalizeVersion(versionRaw);
  for (const file of files) {
    file.write(file.path, version);
  }
  console.log(`Updated project version to ${version}`);
  check(version);
}

const [command, value] = process.argv.slice(2);

try {
  if (command === "check") {
    check(value || expectedVersionFromRef(process.env.GITHUB_REF_NAME));
  } else if (command === "bump") {
    bump(value);
  } else {
    console.error("Usage:");
    console.error("  node scripts/version.mjs check [version]");
    console.error("  node scripts/version.mjs bump <version>");
    process.exit(1);
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
