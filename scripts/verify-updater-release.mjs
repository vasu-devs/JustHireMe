import { existsSync, readFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import process from "node:process";

const usage = `Usage: node scripts/verify-updater-release.mjs <release-assets-dir> <version-or-tag>`;
const [releaseDirRaw, versionRaw] = process.argv.slice(2);

if (!releaseDirRaw || !versionRaw) {
  console.error(usage);
  process.exit(1);
}

const releaseDir = resolve(releaseDirRaw);
const expectedVersion = normalizeVersion(versionRaw);
const manifestPath = join(releaseDir, "latest.json");

function normalizeVersion(raw) {
  // Case-insensitive prefix strip — the release workflow triggers on both "v*" and
  // "V*" tags and version.mjs normalizes with /^v/i, so an uppercase-V tag must not
  // slip through as invalid semver here and crash the publish step.
  const version = raw.trim().replace(/^v/i, "");
  if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error(`Invalid version "${raw}". Expected semver like 0.1.32 or v0.1.32.`);
  }
  return version;
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(`Could not read JSON at ${path}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function requireString(value, label) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${label} must be a non-empty string.`);
  }
  return value.trim();
}

function parseGithubAssetUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`Updater URL is not a valid URL: ${url}`);
  }

  if (parsed.protocol !== "https:" || parsed.hostname !== "github.com") {
    throw new Error(`Updater URL must point to a GitHub HTTPS release asset: ${url}`);
  }

  const segments = parsed.pathname.split("/").filter(Boolean);
  const downloadIndex = segments.indexOf("download");
  if (downloadIndex < 2 || downloadIndex + 2 >= segments.length) {
    throw new Error(`Updater URL is not a GitHub release download URL: ${url}`);
  }

  return {
    tag: segments[downloadIndex + 1],
    asset: decodeURIComponent(segments.slice(downloadIndex + 2).join("/")),
  };
}

function verifyPlatform(target, info) {
  const signature = requireString(info?.signature, `platforms.${target}.signature`);
  const url = requireString(info?.url, `platforms.${target}.url`);
  const { tag, asset } = parseGithubAssetUrl(url);

  if (normalizeVersion(tag) !== expectedVersion) {
    throw new Error(`platforms.${target}.url points to ${tag}, expected v${expectedVersion}.`);
  }

  const assetName = basename(asset);
  const assetPath = join(releaseDir, assetName);
  const sigPath = join(releaseDir, `${assetName}.sig`);

  if (!existsSync(assetPath)) {
    throw new Error(`platforms.${target}.url references missing asset ${assetName}.`);
  }
  if (!existsSync(sigPath)) {
    throw new Error(`Missing updater signature file ${assetName}.sig.`);
  }

  const sigText = readFileSync(sigPath, "utf8").trim();
  if (sigText !== signature) {
    throw new Error(`platforms.${target}.signature does not match ${assetName}.sig.`);
  }

  return assetName;
}

try {
  if (!existsSync(manifestPath)) {
    throw new Error(`Missing updater manifest: ${manifestPath}`);
  }

  const manifest = readJson(manifestPath);
  if (manifest.version !== expectedVersion) {
    throw new Error(`latest.json version is ${manifest.version}; expected ${expectedVersion}.`);
  }
  requireString(manifest.notes, "notes");
  requireString(manifest.pub_date, "pub_date");

  const date = Date.parse(manifest.pub_date);
  if (Number.isNaN(date)) {
    throw new Error(`pub_date is not parseable as a date: ${manifest.pub_date}`);
  }

  const platforms = manifest.platforms;
  if (!platforms || typeof platforms !== "object" || Array.isArray(platforms)) {
    throw new Error("latest.json must contain a platforms object.");
  }

  const targets = Object.keys(platforms).sort();
  if (targets.length === 0) {
    throw new Error("latest.json has no updater platforms.");
  }

  const verified = targets.map((target) => `${target} -> ${verifyPlatform(target, platforms[target])}`);
  console.log(`Updater release verification passed for ${expectedVersion}:`);
  for (const line of verified) {
    console.log(`- ${line}`);
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
