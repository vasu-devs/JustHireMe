import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/ingestion.py — getting a CV/profile into the graph.
 *  These default to timeoutMs: 0 (no timeout): parsing a large CV or crawling a
 *  portfolio can outlast the default 30s, and aborting mid-write loses the import. */
const NO_TIMEOUT = { timeoutMs: 0 } as const;

export const ingestionApi = {
  /** Upload a CV file or raw text (FormData: `file` or `raw`). */
  upload: (api: ApiFetch, form: FormData, opts?: ApiFetchOptions) =>
    api("/api/v1/ingest", withOpts({ method: "POST", body: form, ...NO_TIMEOUT }, opts)),
  /** LinkedIn export archive (FormData: `file`). A LinkedIn PDF goes to upload(). */
  linkedin: (api: ApiFetch, form: FormData, opts?: ApiFetchOptions) =>
    api("/api/v1/ingest/linkedin", withOpts({ method: "POST", body: form, ...NO_TIMEOUT }, opts)),
  github: (api: ApiFetch, body: { username: string; token?: string; max_repos?: number }, opts?: ApiFetchOptions) =>
    api("/api/v1/ingest/github", withOpts({ ...json("POST", body), ...NO_TIMEOUT }, opts)),
  portfolio: (api: ApiFetch, body: { url: string; auto_import?: boolean }, opts?: ApiFetchOptions) =>
    api("/api/v1/ingest/portfolio", withOpts({ ...json("POST", body), ...NO_TIMEOUT }, opts)),
  /** Import a structured profile document (JSON Resume, camelCase, or our shape). */
  profile: (api: ApiFetch, body: unknown, opts?: ApiFetchOptions) =>
    api("/api/v1/ingest/profile", withOpts({ ...json("POST", body), ...NO_TIMEOUT }, opts)),
  profileTemplate: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/ingest/profile/template", opts),
};
