// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

import type { ApiFetch, ApiFetchOptions } from "../../api/types";

/**
 * Web replacement for src/api/client.ts, aliased in vite.web.config.ts.
 *
 * The desktop `createApiFetch(port, token)` builds an absolute
 * `http://127.0.0.1:<port>` URL and attaches the real bearer token — correct
 * for a Tauri webview talking to its own bundled sidecar, wrong for a
 * browser tab: it would need to know a port with no Tauri event bridge to
 * learn it from, and it would put the real secret token on the page (`npm
 * run web`'s whole point is that the browser never sees one — see
 * vite.web.config.ts's proxy, which attaches it server-side instead). So
 * this version ignores both arguments and fetches the path relative to
 * whatever origin served the page; the dev proxy (or, in a real deployment,
 * a same-origin reverse proxy) does the rest.
 *
 * `json`/`withOpts`/`isAbortLikeError` are desktop-agnostic pure helpers —
 * duplicated here (not re-exported from ../../api/client) because Vite's
 * alias intercepts that specifier by resolved path; importing it from inside
 * its own replacement would resolve right back to this file.
 */
const DEFAULT_TIMEOUT_MS = 30000;

export function json(method: string, body: unknown): ApiFetchOptions {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function withOpts(base: ApiFetchOptions, opts?: ApiFetchOptions): ApiFetchOptions {
  if (!opts) return base;
  return {
    ...base,
    ...opts,
    headers: { ...(base.headers as Record<string, string>), ...(opts.headers as Record<string, string>) },
  };
}

export function isAbortLikeError(error: unknown) {
  if (error instanceof DOMException && error.name === "AbortError") return true;
  const message = error instanceof Error ? error.message : String(error);
  return message.toLowerCase().includes("signal is aborted") || message.toLowerCase().includes("aborted");
}

export function createApiFetch(port: number, token: string): ApiFetch {
  // Signature-compatible with the desktop version (App.tsx calls
  // `createApiFetch(port, apiToken)` positionally) but both args are unused
  // by design — see the module docstring above.
  void port;
  void token;
  return (path, opts) => {
    const headers = new Headers(opts?.headers);
    const controller = new AbortController();
    const abort = () => controller.abort(new DOMException("Request cancelled", "AbortError"));
    const timeoutMs = Math.max(0, opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS);
    const timeoutId = timeoutMs > 0
      ? window.setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), timeoutMs)
      : null;
    if (opts?.signal) {
      if (opts.signal.aborted) controller.abort(new DOMException("Request cancelled", "AbortError"));
      else opts.signal.addEventListener("abort", abort, { once: true });
    }
    return fetch(path, { ...opts, headers, signal: controller.signal })
      .catch(error => {
        if (controller.signal.aborted || isAbortLikeError(error)) {
          const reason = controller.signal.reason;
          if (reason instanceof DOMException && reason.name === "TimeoutError") {
            throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s.`);
          }
          throw new DOMException("Request cancelled", "AbortError");
        }
        const message = error instanceof Error ? error.message : String(error);
        if (message === "Failed to fetch" || message.includes("NetworkError")) {
          throw new Error("Can't reach JustHireMe. Is the backend running?");
        }
        throw error;
      })
      .finally(() => {
        if (timeoutId !== null) window.clearTimeout(timeoutId);
        opts?.signal?.removeEventListener("abort", abort);
      });
  };
}
