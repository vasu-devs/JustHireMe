import { spawn } from "node:child_process";
import process from "node:process";

const npm = process.platform === "win32" ? "npm.cmd" : "npm";

const groups = {
  "check:all": [
    ["version check", npm, ["run", "version:check"]],
    ["frontend typecheck", npm, ["run", "typecheck"]],
    ["frontend tests", npm, ["test"]],
    ["frontend build", npm, ["run", "build"]],
    ["website build", npm, ["run", "build"], { cwd: "website" }],
    ["backend tests", ".venv\\Scripts\\python.exe", ["-m", "pytest", "tests", "-q"], { cwd: "backend", fallback: ["python", ["-m", "pytest", "tests", "-q"]] }],
    ["rust tests", "cargo", ["test", "--lib"], { cwd: "src-tauri" }],
    ["rust check", "cargo", ["check"], { cwd: "src-tauri" }],
  ],
  "build:all": [
    ["frontend build", npm, ["run", "build"]],
    ["website build", npm, ["run", "build"], { cwd: "website" }],
    ["rust check", "cargo", ["check"], { cwd: "src-tauri" }],
  ],
  "release:smoke": [
    ["frontend build", npm, ["run", "build"]],
    ["sidecar build", npm, ["run", "build:sidecar"]],
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
  const cwd = options.cwd || ".";
  const taskStartedAt = Date.now();
  const child = spawn(command, args, {
    cwd,
    shell: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout.on("data", (chunk) => prefixLine(name, index, chunk));
  child.stderr.on("data", (chunk) => prefixLine(name, index, chunk));

  child.on("error", (error) => {
    if (options.fallback) {
      const [fallbackCommand, fallbackArgs] = options.fallback;
      tasks[index] = [name, fallbackCommand, fallbackArgs, { cwd }];
      startTask(tasks[index], index).then(() => {}, () => {});
      return;
    }
    failed = true;
    console.error(`[${name}] failed to start: ${error.message}`);
  });

  return new Promise((resolve) => {
    child.on("close", (code) => {
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
