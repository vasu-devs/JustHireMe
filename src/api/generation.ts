import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

export const GENERATION_TIMEOUT_MS = 180000;

/** Mirrors backend/api/routers/generation.py — resume/cover-letter packages. */
export const generationApi = {
  generate: (api: ApiFetch, jobId: string, templateId = "", opts?: ApiFetchOptions) => api(
    `/api/v1/leads/${encodeURIComponent(jobId)}/generate${templateId ? `?template_id=${encodeURIComponent(templateId)}` : ""}`,
    withOpts({ method: "POST", timeoutMs: GENERATION_TIMEOUT_MS }, opts),
  ),
  start: (api: ApiFetch, jobId: string, templateId = "", opts?: ApiFetchOptions) => api(
    `/api/v1/leads/${encodeURIComponent(jobId)}/generate/start${templateId ? `?template_id=${encodeURIComponent(templateId)}` : ""}`,
    withOpts({ method: "POST" }, opts),
  ),
  /** Create a pasted lead and immediately start generating for it. */
  startFromManual: (api: ApiFetch, body: { text: string; url: string; kind?: string }, opts?: ApiFetchOptions) =>
    api("/api/v1/leads/manual/generate/start", withOpts(json("POST", body), opts)),
  runPipeline: (api: ApiFetch, jobId: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}/pipeline/run`, withOpts({ method: "POST" }, opts)),
};
