import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** A profile sub-resource: /api/v1/profile/<entity>. */
export type ProfileEntity =
  | "candidate" | "identity" | "skill" | "experience" | "project"
  | "education" | "certification" | "achievement";

/** Mirrors backend/api/routers/profile.py — the candidate graph. */
export const profileApi = {
  get: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/profile", opts),
  save: (api: ApiFetch, body: unknown, opts?: ApiFetchOptions) =>
    api("/api/v1/profile", withOpts(json("POST", body), opts)),
  getIdentity: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/profile/identity", opts),

  /** Create or update one profile entity. Sends the method the backend expects:
   *  PUT for the singleton sections and for updates by id, POST to add. */
  saveEntity: (api: ApiFetch, entity: ProfileEntity, body: unknown, id = "", opts?: ApiFetchOptions) => {
    const singleton = entity === "candidate" || entity === "identity";
    return api(
      `/api/v1/profile/${entity}${id ? `/${encodeURIComponent(id)}` : ""}`,
      withOpts(json(singleton || id ? "PUT" : "POST", body), opts),
    );
  },
  deleteEntity: (api: ApiFetch, entity: ProfileEntity, idOrTitle: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/profile/${entity}/${encodeURIComponent(idOrTitle)}`, withOpts({ method: "DELETE" }, opts)),
};
