import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/learning.py — what your feedback taught the ranker. */
export const learningApi = {
  insights: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/learning/insights", opts),
};
