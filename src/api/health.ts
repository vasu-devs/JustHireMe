import { withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/health.py — liveness, subsystem status, shutdown. */
export const healthApi = {
  check: (api: ApiFetch, opts?: ApiFetchOptions) => api("/health", opts),
  subsystems: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/health/subsystems", opts),
  shutdown: (api: ApiFetch, opts?: ApiFetchOptions) =>
    api("/api/v1/shutdown", withOpts({ method: "POST" }, opts)),
};
