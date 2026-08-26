#!/usr/bin/env node
/**
 * `npm run web` — start the whole web app with one command.
 *
 * Starts the Python sidecar, reads the port and bearer token it prints on
 * startup, then starts Vite with both in its environment so the dev proxy can
 * attach the token server-side. The browser never sees a token and the user
 * never pastes one.
 *
 * Set JHM_BACKEND_PORT to point at a sidecar you are already running instead.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { platform } from "node:process";

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const VENV_PYTHON = platform === "win32"
  ? `${ROOT}/backend/.venv/Scripts/python.exe`
  : `${ROOT}/backend/.venv/bin/python`;

const children = [];
let shuttingDown = false;

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    try { child.kill(); } catch { /* already gone */ }
  }
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function startVite(port, token) {
  console.log(`\n  backend  http://127.0.0.1:${port}`);
  console.log("  web      http://localhost:5273\n");
  const vite = spawn("npx", ["vite", "--config", "vite.web.config.ts"], {
    cwd: ROOT,
    stdio: "inherit",
    shell: true,
    env: { ...process.env, JHM_BACKEND_PORT: String(port), JHM_TOKEN: token },
  });
  children.push(vite);
  vite.on("exit", (code) => shutdown(code ?? 0));
}

// Reuse a sidecar the user already started.
if (process.env.JHM_BACKEND_PORT && process.env.JHM_TOKEN) {
  startVite(process.env.JHM_BACKEND_PORT, process.env.JHM_TOKEN);
} else {
  if (!existsSync(VENV_PYTHON)) {
    console.error(`\n  Backend virtualenv not found at ${VENV_PYTHON}`);
    console.error("  Run:  cd backend && uv sync --dev\n");
    process.exit(1);
  }

  console.log("  starting backend…");
  const backend = spawn(VENV_PYTHON, ["main.py", "--port", "0"], {
    cwd: `${ROOT}/backend`,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  children.push(backend);

  let token = "";
  let port = "";
  let launched = false;
  const ready = setTimeout(() => {
    if (!launched) {
      console.error("\n  Backend did not report a port within 90s. Its output is above.\n");
      shutdown(1);
    }
  }, 90_000);

  backend.stdout.on("data", (chunk) => {
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line.startsWith("JHM_TOKEN=")) token = line.slice("JHM_TOKEN=".length).trim();
      else if (line.startsWith("PORT:")) port = line.slice("PORT:".length).trim();
      else if (line.trim()) console.log(`  [backend] ${line}`);

      if (token && port && !launched) {
        launched = true;
        clearTimeout(ready);
        startVite(port, token);
      }
    }
  });

  backend.stderr.on("data", (chunk) => process.stderr.write(`  [backend] ${chunk}`));
  backend.on("exit", (code) => {
    if (!shuttingDown) {
      console.error(`\n  Backend exited (${code}).\n`);
      shutdown(code ?? 1);
    }
  });
}
