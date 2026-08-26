import { withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/templates.py — stored resume templates. */
export const templatesApi = {
  list: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/templates", opts),
  get: (api: ApiFetch, id: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/templates/${encodeURIComponent(id)}`, opts),
  upload: (api: ApiFetch, form: FormData, opts?: ApiFetchOptions) =>
    api("/api/v1/templates/upload", withOpts({ method: "POST", body: form, timeoutMs: 0 }, opts)),
  setDefault: (api: ApiFetch, id: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/templates/${encodeURIComponent(id)}/default`, withOpts({ method: "POST" }, opts)),
  delete: (api: ApiFetch, id: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/templates/${encodeURIComponent(id)}`, withOpts({ method: "DELETE" }, opts)),
};
