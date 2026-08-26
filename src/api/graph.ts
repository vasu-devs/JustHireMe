import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/graph.py — the Knowledge page snapshot.
 *  `repair` runs the expensive purge/re-sync; the default read is snapshot-only. */
export const graphApi = {
  stats: (api: ApiFetch, repair = false, opts?: ApiFetchOptions) =>
    api(`/api/v1/graph${repair ? "?repair=true" : ""}`, opts),
};
