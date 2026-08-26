export type { ApiFetch, ApiFetchOptions, ContactLookup, FormReadResult, GraphStats, KeywordCoverage, Lead } from "../types";

export type WSMessage =
  | { type: "heartbeat"; status: string; beat: number; uptime_seconds: number; timestamp: string }
  | { type: "agent"; event?: string; msg?: string; job_id?: string; [key: string]: unknown }
  | { type: "LEAD_UPDATED"; data: import("../types").Lead }
  | { type: "HOT_X_LEAD"; data: import("../types").Lead };
