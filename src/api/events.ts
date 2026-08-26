import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/events.py — the activity log. */
export const eventsApi = {
  list: (api: ApiFetch, limit = 200, opts?: ApiFetchOptions) => api(`/api/v1/events?limit=${limit}`, opts),
};
