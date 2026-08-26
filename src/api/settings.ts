import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/settings.py — settings, preferences, the resume
 *  template body, and the data reset. */
export const settingsApi = {
  get: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/settings", opts),
  save: (api: ApiFetch, settings: object, opts?: ApiFetchOptions) =>
    api("/api/v1/settings", withOpts(json("POST", settings), opts)),
  validate: (api: ApiFetch, settings: object, opts?: ApiFetchOptions) =>
    api("/api/v1/settings/validate", withOpts(json("POST", settings), opts)),
  models: (api: ApiFetch, provider: string, settings: object, opts?: ApiFetchOptions) =>
    api(`/api/v1/settings/models/${encodeURIComponent(provider)}`, withOpts(json("POST", settings), opts)),
  getPreferences: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/preferences", opts),
  savePreferences: (api: ApiFetch, preferences: string, opts?: ApiFetchOptions) =>
    api("/api/v1/preferences", withOpts(json("POST", { preferences }), opts)),
  subscriptionStatus: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/settings/subscription-status", opts),
  subscriptionLogin: (api: ApiFetch, provider: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/settings/subscription-login/${encodeURIComponent(provider)}`, withOpts({ method: "POST" }, opts)),

  // The single free-text resume template. Distinct from templatesApi, which
  // manages the stored/uploaded template files.
  getTemplate: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/template", opts),
  saveTemplate: (api: ApiFetch, template: string, opts?: ApiFetchOptions) =>
    api("/api/v1/template", withOpts(json("POST", { template }), opts)),

  resetData: (api: ApiFetch, options?: { clearSettings?: boolean }, opts?: ApiFetchOptions) =>
    api("/api/v1/data/reset", withOpts(json("POST", { confirm: "DELETE", clear_settings: !!options?.clearSettings }), opts)),
};
