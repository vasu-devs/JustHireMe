export type ConnSt = "disconnected" | "connecting" | "connected";
export type PipelineTab = "all" | "hot" | "found" | "evaluated" | "generated" | "applied" | "discarded";
export type PipelineViewId =
  | "pipeline"
  | "pipeline-hot"
  | "pipeline-found"
  | "pipeline-evaluated"
  | "pipeline-generated"
  | "pipeline-applied"
  | "pipeline-discarded";
export type View = "apply" | "dashboard" | PipelineViewId | "graph" | "activity" | "profile" | "ingestion";
export type LeadSort = "recommended" | "newest" | "signal" | "match" | "company";
export type SeniorityFilter = "all" | "beginner" | "fresher" | "junior" | "mid" | "senior" | "unknown";

export interface KeywordCoverage {
  jd_terms?: string[];
  covered_terms?: string[];
  missing_terms?: string[];
  incorporated_terms?: string[];
  coverage_pct?: number;
}

export interface ContactLookup {
  status?: string;
  domain?: string;
  message?: string;
  primary_contact?: {
    name?: string;
    first_name?: string;
    title?: string;
    email?: string;
    linkedin_url?: string;
    confidence?: number;
    personalized_email?: string;
  };
  contacts?: {
    name?: string;
    title?: string;
    email?: string;
    linkedin_url?: string;
    confidence?: number;
  }[];
}

export interface Lead {
  job_id: string; title: string; company: string;
  url: string; platform: string; status: string; asset: string;
  resume_asset?: string; cover_letter_asset?: string; selected_projects?: string[];
  resume_version?: number;
  keyword_coverage?: KeywordCoverage;
  contact_lookup?: ContactLookup;
  score: number; reason: string; match_points: string[]; gaps?: string[];
  description?: string; kind?: string; budget?: string;
  signal_score?: number; signal_reason?: string; signal_tags?: string[];
  base_signal_score?: number; learning_delta?: number; learning_reason?: string;
  outreach_reply?: string; outreach_dm?: string; outreach_email?: string; proposal_draft?: string;
  fit_bullets?: string[]; followup_sequence?: string[]; proof_snippet?: string;
  tech_stack?: string[]; location?: string; urgency?: string;
  seniority_level?: string;
  lead_quality_score?: number; lead_quality_reason?: string;
  source_meta?: Record<string, any>; feedback?: string; feedback_note?: string;
  followup_due_at?: string; last_contacted_at?: string;
  events?: { action: string; ts: string }[];
}
export interface GraphStats {
  candidate: number; skill: number; project: number;
  experience: number; joblead: number;
  available?: boolean; status?: "live" | "degraded"; error?: string;
  loading?: boolean; loaded?: boolean; request_error?: string;
  sync?: { status?: string; synced?: number; refreshed_at?: string; error?: string };
  graph?: {
    nodes: { id: string; label: string; type: string; subtitle?: string }[];
    edges: { source: string; target: string; type: string }[];
    available?: boolean;
    error?: string;
  };
  embedding?: {
    available?: boolean;
    points: { id: string; label: string; type: string; x: number; y: number; z?: number }[];
    error?: string;
  };
}
export interface LogLine {
  id: number; ts: string; msg: string; src: string;
  kind: "heartbeat" | "agent" | "system";
}

export type ApiFetchOptions = RequestInit & {
  timeoutMs?: number;
};

export type ApiFetch = (path: string, opts?: ApiFetchOptions) => Promise<Response>;

export interface FormField {
  type: string;
  label: string;
  selector: string;
  answer: string;
  found_on_page: boolean;
  confidence: "high" | "medium" | "low";
}

export interface FormReadResult {
  platform: string | null;
  platform_label: string;
  screenshot_b64: string;
  fields: FormField[];
  unmatched_labels: string[];
  error: string | null;
}
