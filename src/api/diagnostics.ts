import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/diagnostics.py — error reporting in, metrics out. */
export const diagnosticsApi = {
  get: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/diagnostics", opts),

  /** Report a frontend crash. Field names must match what the backend records —
   *  it reads `componentStack`, `url` and `userAgent`, and drops anything else. */
  reportError: (api: ApiFetch, report: { error: string; componentStack?: string; label?: string }, opts?: ApiFetchOptions) =>
    api("/api/v1/errors", withOpts(json("POST", {
      error: report.label ? `[${report.label}] ${report.error}` : report.error,
      componentStack: report.componentStack ?? "",
      url: typeof window === "undefined" ? "" : window.location.href,
      userAgent: typeof navigator === "undefined" ? "" : navigator.userAgent,
    }), opts)),
};
