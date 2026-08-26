import type { ApiFetch, ApiFetchOptions } from "./types";

export interface DashboardHeadline {
  total: number;
  verified_confirmed: number;
  in_apply_queue: number;
  applied: number;
  interviews: number;
  offers: number;
  rejections: number;
}

export interface FunnelStage {
  label: string;
  count: number;
  dropoff_pct: number | null;
}

export interface SourceRow {
  platform: string;
  total: number;
  verified: number;
  confirmed: number;
  confirm_rate: number | null;
}

export interface ActivityRow {
  ts: string;
  label: string;
  title: string;
  company: string;
}

export interface DashboardOverview {
  headline: DashboardHeadline;
  funnel: FunnelStage[];
  sources: SourceRow[];
  leads_per_day: [string, number][];
  applications_per_day: [string, number][];
  activity: ActivityRow[];
}

export interface ApplicationDetail {
  verify_status: string;
  verify_evidence: string;
  verify_checked_at: string;
  answers: string;
}

/** Mirrors backend/api/routers/dashboard.py — the audit-report queries. */
export const dashboardApi = {
  overview: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/dashboard/overview", opts),
  applicationDetail: (api: ApiFetch, jobId: string, opts?: ApiFetchOptions) =>
    api(`/api/v1/dashboard/applications/${encodeURIComponent(jobId)}`, opts),
};
