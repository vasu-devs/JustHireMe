import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/automation.py — reading and submitting application forms. */
export const automationApi = {
  readForm: (api: ApiFetch, jobId: string, url = "", opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}/form/read`, withOpts(json("POST", { url }), opts)),
  previewApply: (api: ApiFetch, jobId: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}/apply/preview`, withOpts({ method: "POST" }, opts)),
  fire: (api: ApiFetch, jobId: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/fire/${encodeURIComponent(jobId)}`, withOpts({ method: "POST" }, opts)),
  refreshSelectors: (api: ApiFetch, opts?: ApiFetchOptions) =>
    api("/api/v1/selectors/refresh", withOpts({ method: "POST" }, opts)),
};
