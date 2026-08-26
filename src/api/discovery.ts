import { withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/discovery.py — scanning and re-evaluation.
 *  `/leads/reevaluate` and `/leads/cleanup` are discovery endpoints despite the
 *  `/leads` prefix: the discovery router owns them server-side. */
export const discoveryApi = {
  scan: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/scan", withOpts({ method: "POST" }, opts)),
  stopScan: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/scan/stop", withOpts({ method: "POST" }, opts)),
  freeSources: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/free-sources/scan", withOpts({ method: "POST" }, opts)),
  status: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/status", opts),
  reevaluate: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/leads/reevaluate", withOpts({ method: "POST" }, opts)),
  stopReevaluate: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/leads/reevaluate/stop", withOpts({ method: "POST" }, opts)),
  cleanup: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/leads/cleanup", withOpts({ method: "POST" }, opts)),
};
