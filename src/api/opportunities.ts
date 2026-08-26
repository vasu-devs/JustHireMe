import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

export type OpportunityDecision = "apply_now" | "strong_stretch" | "needs_review" | "skip";
export type OpportunityDegreeLevel = "unknown" | "bachelors" | "masters" | "doctorate";
export type OpportunityTechnicalTrack = "software" | "backend" | "frontend" | "fullstack" | "ai_ml" | "data" | "cloud_devops" | "security" | "mobile" | "qa_automation" | "embedded_systems";
export type OpportunityTypePreference = "internship" | "new_grad" | "entry_level_full_time" | "stretch_full_time";
export type OpportunityOutcomeType = "application_started" | "application_submitted" | "outreach_sent" | "recruiter_reply" | "screening" | "technical_assessment" | "interview" | "rejected" | "offer" | "withdrawn" | "skipped";

export interface OpportunityCard {
  opportunity_id: string;
  employer_name: string;
  title: string;
  location_text: string;
  canonical_apply_url: string;
  lifecycle: {
    status: string;
    last_verified_active_at?: string | null;
    deadline_at?: string | null;
    evidence?: string[];
  };
  source_count: number;
  providers: string[];
  applicability: {
    decision: OpportunityDecision;
    eligibility: string;
    opportunity_type: string;
    technical_track: string;
    workplace_scope: string;
    india_eligible: boolean;
    paid_status: string;
    hard_blockers: string[];
    safety_blockers: string[];
    safety_warnings: string[];
    unknowns: string[];
    evidence: Record<string, string[]>;
    career_growth_score: number;
    hiring_confidence_score: number;
    priority_score: number;
    career_signals: string[];
    candidate_fit_score: number;
    matched_skills: string[];
    posting_skills: string[];
    candidate_evidence_missing: boolean;
    posting_india_cities?: string[];
    graduation_years?: number[];
    monthly_compensation_inr?: number[];
    internship_duration_months?: number[];
    minimum_experience_years?: number;
    requires_current_enrollment?: boolean;
    work_authorization_restricted?: boolean;
    required_language_groups?: string[][];
    required_degree_level?: OpportunityDegreeLevel;
  };
  updated_at: string;
}

export interface OpportunityCandidate {
  candidate_id: string;
  consent_confirmed_at: string | null;
  home_country: string;
  graduation_year: number;
  currently_enrolled: boolean;
  current_degree_level: OpportunityDegreeLevel;
  accepted_india_cities: string[];
  technical_skills: string[];
  project_keywords: string[];
  spoken_languages: string[];
  preferred_technical_tracks: OpportunityTechnicalTrack[];
  accepted_opportunity_types: OpportunityTypePreference[];
  allow_india_onsite: boolean;
  allow_india_hybrid: boolean;
  allow_india_remote: boolean;
  allow_worldwide_remote: boolean;
  allow_unpaid: boolean;
  allow_bond: boolean;
  professional_experience_years: number;
  minimum_monthly_compensation_inr: number;
  maximum_internship_months: number;
}

export interface OpportunityFunnelMetrics {
  candidate_id: string;
  queue_counts: Partial<Record<OpportunityDecision, number>>;
  funnel: {
    tracked: number;
    application_started: number;
    application_submitted: number;
    outreach_sent: number;
    meaningful_contacts: number;
    screening_processes: number;
    interviews: number;
    offers: number;
    rejections: number;
    withdrawn: number;
  };
  rates: {
    completion_from_tracked_percent: number;
    meaningful_contacts_per_20_applications: number;
    interviews_per_20_applications: number;
    offers_per_20_applications: number;
  };
  source_outcomes: Array<{ provider: string; submitted: number; meaningful_contacts: number; interviews: number; offers: number }>;
  first_event_at?: string | null;
  latest_event_at?: string | null;
}

export interface OpportunityCandidateSummary {
  candidate_id: string;
  graduation_year: number;
  preferred_technical_tracks: OpportunityTechnicalTrack[];
  accepted_opportunity_types: OpportunityTypePreference[];
  consent_confirmed_at: string | null;
  application_profile_ready: boolean;
  pilot_ready: boolean;
  profile_updated_at: string;
}

export interface OpportunityCohortMetrics {
  candidate_count: number;
  saved_candidate_count: number;
  pending_candidate_count: number;
  funnel: OpportunityFunnelMetrics["funnel"];
  rates: Pick<OpportunityFunnelMetrics["rates"], "meaningful_contacts_per_20_applications" | "interviews_per_20_applications" | "offers_per_20_applications">;
  candidates_with_traction: number;
  targets: {
    candidate_count: number;
    application_submitted: number;
    meaningful_contacts: number;
    interviews: number;
    candidates_with_traction: number;
    stretch_offers: number;
  };
  progress_percent: Record<string, number>;
}

export interface OpportunityApplicationProfileStatus {
  candidate_id: string;
  ready: boolean;
  has_identity?: boolean;
  has_contact_identity?: boolean;
  missing_identity_fields?: string[];
  has_summary?: boolean;
  skill_count?: number;
  project_count?: number;
  experience_count?: number;
  education_count?: number;
  evidence_count?: number;
  updated_at?: string;
}

export interface OpportunityApplicationIdentity {
  email: string;
  phone: string;
  linkedin_url: string;
  github_url: string;
  website_url: string;
  city: string;
}

export interface OpportunityApplicationProfilePreview {
  candidate_id: string;
  ready: true;
  profile_name: string;
  summary_preview: string;
  evidence_count: number;
  skill_count: number;
  project_count: number;
  experience_count: number;
  education_count: number;
  payload_sha256: string;
}

export interface OpportunityCandidateResumePreview extends OpportunityApplicationProfilePreview {
  profile: Record<string, unknown>;
}

export interface OpportunityScanStatus {
  run_id?: string;
  candidate_id?: string;
  status: "idle" | "running" | "completed" | "failed";
  started?: boolean;
  target_count?: number;
  targets_completed?: number;
  raw_rows_seen?: number;
  source_failures?: number;
  opportunities?: number;
  decision_counts?: Partial<Record<OpportunityDecision, number>>;
  error?: string;
  started_at?: string;
  completed_at?: string | null;
}

export interface OpportunityProviderStatus {
  master_enabled: boolean;
  secrets_redacted: boolean;
  retention_rule: string;
  providers: Array<{
    provider: "serpapi" | "adzuna" | "jooble";
    state: "master_disabled" | "disabled" | "missing_credentials" | "cap_reached" | "ready";
    enabled: boolean;
    configured: boolean;
    alert: "normal" | "notice_50" | "warning_80" | "cap_reached";
    limits: {
      daily_requests: number; monthly_requests: number;
      daily_spend_usd: number; monthly_spend_usd: number;
      estimated_cost_per_request_usd: number;
    };
    usage: {
      requests_today: number; requests_month: number;
      estimated_spend_today_usd: number; estimated_spend_month_usd: number;
      response_rows: number; successful_requests: number; failed_requests: number;
      eligible_opportunities: number; net_new_eligible_opportunities: number;
      net_new_eligible_yield_percent: number;
    };
    remaining: { daily_requests: number; monthly_requests: number };
    experiment: { benchmark: "insufficient_data" | "retain" | "pause_and_review" };
  }>;
}

export interface OpportunityCoverageStatus {
  candidate_id: string;
  inventory_target_count: number;
  inventory_provider_count: number;
  inventory_by_provider: Record<string, number>;
  attempted_target_count: number;
  unattempted_target_count: number;
  health_counts: Record<string, number>;
  provider_health: Record<string, {
    targets: number; success: number; zero_result: number; failure: number;
    raw_rows: number; accepted_source_records: number;
  }>;
  raw_rows: number;
  accepted_source_records: number;
  latest_attempted_at: string | null;
  paid_provider_count: number;
  index: {
    source_record_count: number;
    canonical_opportunity_count: number;
    active_opportunity_count: number;
    observation_count: number;
    identity_alias_count: number;
    status_counts: Record<string, number>;
    latest_observed_at: string | null;
    last_sync: null | {
      sync_id: string;
      source_sha256: string;
      source_label: string;
      source_size_bytes: number;
      source_latest_observed_at: string | null;
      source_counts: Record<string, number>;
      inserted_counts: Record<string, number>;
      backup_label: string;
      completed_at: string;
    };
  };
}

export const opportunitiesApi = {
  list(
    api: ApiFetch,
    candidateId: string,
    decision: OpportunityDecision,
    opts?: ApiFetchOptions,
  ) {
    const params = new URLSearchParams({ candidate_id: candidateId, decision, limit: "200" });
    return api(`/api/v1/opportunities?${params.toString()}`, opts);
  },
  getCandidate(api: ApiFetch, candidateId: string, opts?: ApiFetchOptions) {
    return api(`/api/v1/opportunities/candidate/${encodeURIComponent(candidateId)}`, opts);
  },
  candidates(api: ApiFetch, opts?: ApiFetchOptions) {
    return api("/api/v1/opportunities/candidates", opts);
  },
  applicationProfileStatus(api: ApiFetch, candidateId: string, opts?: ApiFetchOptions) {
    return api(`/api/v1/opportunities/candidate/${encodeURIComponent(candidateId)}/application-profile`, opts);
  },
  previewApplicationProfile(api: ApiFetch, candidateId: string, opts?: ApiFetchOptions) {
    return api(
      `/api/v1/opportunities/candidate/${encodeURIComponent(candidateId)}/application-profile/preview`,
      opts,
    );
  },
  snapshotApplicationProfile(api: ApiFetch, candidateId: string, expectedPayloadSha256: string, identity: OpportunityApplicationIdentity, opts?: ApiFetchOptions) {
    return api(
      `/api/v1/opportunities/candidate/${encodeURIComponent(candidateId)}/application-profile/snapshot`,
      withOpts(json("POST", { expected_payload_sha256: expectedPayloadSha256, identity }), opts),
    );
  },
  previewCandidateResume(api: ApiFetch, candidateId: string, file: File, opts?: ApiFetchOptions) {
    const form = new FormData();
    form.append("file", file);
    return api(
      `/api/v1/opportunities/candidate/${encodeURIComponent(candidateId)}/application-profile/resume/preview`,
      withOpts({ method: "POST", body: form }, opts),
    );
  },
  confirmCandidateResume(api: ApiFetch, candidateId: string, preview: OpportunityCandidateResumePreview, identity: OpportunityApplicationIdentity, opts?: ApiFetchOptions) {
    return api(
      `/api/v1/opportunities/candidate/${encodeURIComponent(candidateId)}/application-profile/resume/confirm`,
      withOpts(json("POST", {
        expected_payload_sha256: preview.payload_sha256,
        profile: preview.profile,
        identity,
      }), opts),
    );
  },
  saveCandidate(
    api: ApiFetch,
    candidateId: string,
    body: Omit<OpportunityCandidate, "candidate_id">,
    opts?: ApiFetchOptions,
  ) {
    return api(
      `/api/v1/opportunities/candidate/${encodeURIComponent(candidateId)}`,
      withOpts(json("PUT", body), opts),
    );
  },
  startScan(api: ApiFetch, candidateId: string, opts?: ApiFetchOptions) {
    return api(
      "/api/v1/opportunities/scan",
      withOpts(json("POST", { candidate_id: candidateId, target_limit: 500, max_concurrency: 6 }), opts),
    );
  },
  scanStatus(api: ApiFetch, candidateId: string, opts?: ApiFetchOptions) {
    const params = new URLSearchParams({ candidate_id: candidateId });
    return api(`/api/v1/opportunities/scan/status?${params.toString()}`, opts);
  },
  providerStatus(api: ApiFetch, opts?: ApiFetchOptions) {
    return api("/api/v1/opportunities/providers", opts);
  },
  coverageStatus(api: ApiFetch, candidateId: string, opts?: ApiFetchOptions) {
    const params = new URLSearchParams({ candidate_id: candidateId });
    return api(`/api/v1/opportunities/coverage?${params.toString()}`, opts);
  },
  metrics(api: ApiFetch, candidateId: string, opts?: ApiFetchOptions) {
    const params = new URLSearchParams({ candidate_id: candidateId });
    return api(`/api/v1/opportunities/metrics?${params.toString()}`, opts);
  },
  cohortMetrics(api: ApiFetch, opts?: ApiFetchOptions) {
    return api("/api/v1/opportunities/cohort/metrics", opts);
  },
  track(api: ApiFetch, candidateId: string, opportunityId: string, opts?: ApiFetchOptions) {
    const params = new URLSearchParams({ candidate_id: candidateId });
    return api(
      `/api/v1/opportunities/${encodeURIComponent(opportunityId)}/track?${params.toString()}`,
      withOpts({ method: "POST" }, opts),
    );
  },
  recordOutcome(
    api: ApiFetch,
    candidateId: string,
    opportunityId: string,
    eventType: OpportunityOutcomeType,
    opts?: ApiFetchOptions,
  ) {
    const params = new URLSearchParams({ candidate_id: candidateId });
    return api(
      `/api/v1/opportunities/${encodeURIComponent(opportunityId)}/outcomes?${params.toString()}`,
      withOpts(json("POST", { event_type: eventType, idempotency_key: `ui:${eventType}` }), opts),
    );
  },
};
