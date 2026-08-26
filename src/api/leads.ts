import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions, Lead } from "./types";

/** Mirrors backend/api/routers/leads.py — lead CRUD, feedback, follow-ups, assets. */
export const leadsApi = {
  list: async (api: ApiFetch, opts?: ApiFetchOptions): Promise<Lead[]> => {
    const response = await api("/api/v1/leads", opts);
    if (!response.ok) throw new Error("Failed to load leads");
    return response.json();
  },
  listRaw: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/leads", opts),
  get: (api: ApiFetch, jobId: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}`, opts),
  delete: (api: ApiFetch, jobId: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}`, withOpts({ method: "DELETE" }, opts)),
  updateStatus: (api: ApiFetch, jobId: string, status: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}/status`, withOpts(json("PUT", { status }), opts)),
  saveFeedback: (api: ApiFetch, jobId: string, feedback: string, note = "", opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}/feedback`, withOpts(json("PUT", { feedback, note }), opts)),
  setFollowup: (api: ApiFetch, jobId: string, days: number, opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}/followup`, withOpts(json("PUT", { days }), opts)),
  versions: (api: ApiFetch, jobId: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/leads/${encodeURIComponent(jobId)}/versions`, opts),
  createManual: (api: ApiFetch, body: { text: string; url: string }, opts?: ApiFetchOptions) =>
    api("/api/v1/leads/manual", withOpts(json("POST", body), opts)),
  dueFollowups: (api: ApiFetch, limit = 25, opts?: ApiFetchOptions) =>
    api(`/api/v1/followups/due?limit=${limit}`, opts),

  /** Path for an <embed>/download target — not fetched, so it returns the URL only. */
  pdfPath: (jobId: string, kind: "resume" | "cover_letter", version?: number) => {
    const params = new URLSearchParams({ kind });
    if (version !== undefined) params.set("version", String(version));
    return `/api/v1/leads/${encodeURIComponent(jobId)}/pdf?${params}`;
  },
  pdf: (api: ApiFetch, jobId: string, kind: "resume" | "cover_letter", opts?: ApiFetchOptions) =>
    api(leadsApi.pdfPath(jobId, kind), opts),
};
