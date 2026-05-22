import { spawn } from "node:child_process";
import process from "node:process";

const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const backendPython = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const systemPython = process.platform === "win32" ? "python" : "python3";
const npmOptions = (options = {}) => ({
  ...options,
  shell: process.platform === "win32",
});

const groups = {
  "check:all": [
    ["version check", npm, ["run", "version:check"], npmOptions()],
    ["frontend typecheck", npm, ["run", "typecheck"], npmOptions()],
    ["frontend tests", npm, ["test"], npmOptions()],
    ["frontend build", npm, ["run", "build"], npmOptions()],
    ["website build", npm, ["run", "build"], npmOptions({ cwd: "website" })],
    ["backend tests", backendPython, ["-m", "pytest", "tests", "-q"], { cwd: "backend", fallback: [systemPython, ["-m", "pytest", "tests", "-q"]] }],
    ["rust tests", "cargo", ["test", "--lib"], { cwd: "src-tauri" }],
    ["rust check", "cargo", ["check"], { cwd: "src-tauri" }],
  ],
  "build:all": [
    ["frontend build", npm, ["run", "build"], npmOptions()],
    ["website build", npm, ["run", "build"], npmOptions({ cwd: "website" })],
    ["rust check", "cargo", ["check"], { cwd: "src-tauri" }],
  ],
  "release:smoke": [
    ["frontend build", npm, ["run", "build"], npmOptions()],
    ["sidecar build", npm, ["run", "build:sidecar"], npmOptions()],
    ["runtime pack asset", npm, ["run", "build:runtime-pack"], npmOptions()],
  ],
};

const groupName = process.argv[2];
const tasks = groups[groupName];

if (!tasks) {
  console.error(`Unknown parallel task group: ${groupName || "(missing)"}`);
  console.error(`Available groups: ${Object.keys(groups).join(", ")}`);
  process.exit(1);
}

const colors = [36, 35, 34, 33, 32, 31];
let failed = false;
const startedAt = Date.now();

function prefixLine(name, index, chunk) {
  const color = colors[index % colors.length];
  const lines = chunk.toString().split(/\r?\n/);
  for (const line of lines) {
    if (line) {
      process.stdout.write(`\x1b[${color}m[${name}]\x1b[0m ${line}\n`);
    }
  }
}

function startTask(task, index) {
  const [name, command, args, options = {}] = task;
  return runTask(name, command, args, options, index);
}

function runTask(name, command, args, options, index) {
  const cwd = options.cwd || ".";
  const taskStartedAt = Date.now();
  let settled = false;

  return new Promise((resolve) => {
    const handleStartError = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      if (options.fallback) {
        const [fallbackCommand, fallbackArgs] = options.fallback;
        runTask(name, fallbackCommand, fallbackArgs, { cwd }, index).then(resolve);
        return;
      }
      failed = true;
      console.error(`[${name}] failed to start: ${error.message}`);
      resolve();
    };

    let child;
    try {
      child = spawn(command, args, {
        cwd,
        shell: Boolean(options.shell),
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      handleStartError(error);
      return;
    }

    child.stdout.on("data", (chunk) => prefixLine(name, index, chunk));
    child.stderr.on("data", (chunk) => prefixLine(name, index, chunk));

    child.on("error", handleStartError);

    child.on("close", (code) => {
      if (settled) {
        return;
      }
      settled = true;
      const seconds = ((Date.now() - taskStartedAt) / 1000).toFixed(1);
      if (code !== 0) {
        failed = true;
        console.error(`[${name}] exited with code ${code} after ${seconds}s`);
      } else {
        console.log(`[${name}] completed in ${seconds}s`);
      }
      resolve();
    });
  });
}

await Promise.all(tasks.map(startTask));
console.log(`[${groupName}] completed in ${((Date.now() - startedAt) / 1000).toFixed(1)}s`);
process.exit(failed ? 1 : 0);
