import { useEffect, useState } from "react";
import type { ApiFetch } from "../../types";
import { opportunitiesApi } from "../../api";
import type {
  OpportunityCandidate,
  OpportunityCandidateResumePreview,
  OpportunityApplicationProfilePreview,
  OpportunityApplicationIdentity,
  OpportunityApplicationProfileStatus,
  OpportunityCandidateSummary,
  OpportunityCard,
  OpportunityCohortMetrics,
  OpportunityCoverageStatus,
  OpportunityDecision,
  OpportunityFunnelMetrics,
  OpportunityOutcomeType,
  OpportunityProviderStatus,
  OpportunityScanStatus,
  OpportunityTechnicalTrack,
  OpportunityTypePreference,
} from "../../api";
import { openExternalUrl } from "../../shared/lib/openExternal";
import { hasRequiredApplicationIdentity } from "./opportunityIdentity";

const CANDIDATE_KEY = "jhm-opportunity-candidate-id";
const TABS: Array<{ id: OpportunityDecision; label: string; promise: string }> = [
  { id: "apply_now", label: "Apply now", promise: "Verified live, applicable, safe" },
  { id: "strong_stretch", label: "Strong stretch", promise: "Eligible with a bounded experience stretch" },
  { id: "needs_review", label: "Needs review", promise: "A material fact is still unknown" },
  { id: "skip", label: "Skip", promise: "Closed, incompatible, unsafe, or irrelevant" },
];
const TRACK_OPTIONS: Array<{ id: OpportunityTechnicalTrack; label: string }> = [
  { id: "software", label: "General software" }, { id: "backend", label: "Backend" },
  { id: "frontend", label: "Frontend" }, { id: "fullstack", label: "Full stack" },
  { id: "ai_ml", label: "AI / ML" }, { id: "data", label: "Data" },
  { id: "cloud_devops", label: "Cloud / DevOps" }, { id: "security", label: "Security" },
  { id: "mobile", label: "Mobile" }, { id: "qa_automation", label: "QA automation" },
  { id: "embedded_systems", label: "Embedded / systems" },
];
const TYPE_OPTIONS: Array<{ id: OpportunityTypePreference; label: string }> = [
  { id: "internship", label: "Internships" }, { id: "new_grad", label: "New grad" },
  { id: "entry_level_full_time", label: "Entry-level full time" },
  { id: "stretch_full_time", label: "1–3 year stretch" },
];
const OUTCOME_OPTIONS: Array<{ id: OpportunityOutcomeType; label: string }> = [
  { id: "application_started", label: "Application started" },
  { id: "application_submitted", label: "Application submitted" },
  { id: "outreach_sent", label: "Outreach sent" },
  { id: "recruiter_reply", label: "Recruiter replied" },
  { id: "screening", label: "Screening call" },
  { id: "technical_assessment", label: "Technical assessment" },
  { id: "interview", label: "Interview" },
  { id: "rejected", label: "Rejected" },
  { id: "offer", label: "Offer" },
  { id: "withdrawn", label: "Withdrawn" },
];

function words(value: string) {
  return value.replace(/_/g, " ");
}

const DEFAULT_PROFILE: OpportunityCandidate = {
  candidate_id: "default",
  consent_confirmed_at: null,
  home_country: "IN",
  graduation_year: 2027,
  currently_enrolled: true,
  current_degree_level: "unknown",
  accepted_india_cities: [],
  technical_skills: [],
  project_keywords: [],
  spoken_languages: [],
  preferred_technical_tracks: [],
  accepted_opportunity_types: ["internship", "new_grad", "entry_level_full_time", "stretch_full_time"],
  allow_india_onsite: true,
  allow_india_hybrid: true,
  allow_india_remote: true,
  allow_worldwide_remote: true,
  allow_unpaid: false,
  allow_bond: false,
  professional_experience_years: 0,
  minimum_monthly_compensation_inr: 0,
  target_monthly_compensation_inr: 0,
  minimum_monthly_compensation_usd: 0,
  target_monthly_compensation_usd: 0,
  unknown_compensation_policy: "allow",
  maximum_internship_months: 12,
};
const EMPTY_APPLICATION_IDENTITY: OpportunityApplicationIdentity = {
  email: "", phone: "", linkedin_url: "", github_url: "", website_url: "", city: "",
};

async function responseJson<T>(response: Response, label: string): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `${label} failed (${response.status})`);
  return payload as T;
}

export function OpportunitiesView({ api }: { api: ApiFetch }) {
  const [candidateId, setCandidateId] = useState(() => localStorage.getItem(CANDIDATE_KEY) || "default");
  const [candidateDraft, setCandidateDraft] = useState(candidateId);
  const [tab, setTab] = useState<OpportunityDecision>("apply_now");
  const [items, setItems] = useState<OpportunityCard[]>([]);
  const [profile, setProfile] = useState<OpportunityCandidate>({ ...DEFAULT_PROFILE, candidate_id: candidateId });
  const [citiesDraft, setCitiesDraft] = useState("");
  const [skillsDraft, setSkillsDraft] = useState("");
  const [projectsDraft, setProjectsDraft] = useState("");
  const [languagesDraft, setLanguagesDraft] = useState("");
  const [scan, setScan] = useState<OpportunityScanStatus>({ status: "idle" });
  const [metrics, setMetrics] = useState<OpportunityFunnelMetrics | null>(null);
  const [cohort, setCohort] = useState<OpportunityCohortMetrics | null>(null);
  const [savedCandidates, setSavedCandidates] = useState<OpportunityCandidateSummary[]>([]);
  const [applicationProfile, setApplicationProfile] = useState<OpportunityApplicationProfileStatus>({ candidate_id: candidateId, ready: false });
  const [applicationIdentity, setApplicationIdentity] = useState<OpportunityApplicationIdentity>(EMPTY_APPLICATION_IDENTITY);
  const applicationIdentityReady = hasRequiredApplicationIdentity(applicationIdentity);
  const [applicationPreview, setApplicationPreview] = useState<OpportunityApplicationProfilePreview | null>(null);
  const [resumePreview, setResumePreview] = useState<OpportunityCandidateResumePreview | null>(null);
  const [providerStatus, setProviderStatus] = useState<OpportunityProviderStatus | null>(null);
  const [coverage, setCoverage] = useState<OpportunityCoverageStatus | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [trackingId, setTrackingId] = useState("");
  const [outcomeSavingId, setOutcomeSavingId] = useState("");
  const [linkingProfile, setLinkingProfile] = useState(false);
  const [outcomeDrafts, setOutcomeDrafts] = useState<Record<string, OpportunityOutcomeType>>({});
  const [trackedIds, setTrackedIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setApplicationPreview(null);
    setResumePreview(null);
    setApplicationIdentity(EMPTY_APPLICATION_IDENTITY);
    Promise.all([
      opportunitiesApi.getCandidate(api, candidateId, { signal: controller.signal })
        .then(response => responseJson<OpportunityCandidate>(response, "Candidate profile")),
      opportunitiesApi.scanStatus(api, candidateId, { signal: controller.signal })
        .then(response => responseJson<OpportunityScanStatus>(response, "Scan status")),
      opportunitiesApi.metrics(api, candidateId, { signal: controller.signal })
        .then(response => responseJson<OpportunityFunnelMetrics>(response, "Pilot metrics")),
      opportunitiesApi.candidates(api, { signal: controller.signal })
        .then(response => responseJson<OpportunityCandidateSummary[]>(response, "Saved candidates")),
      opportunitiesApi.cohortMetrics(api, { signal: controller.signal })
        .then(response => responseJson<OpportunityCohortMetrics>(response, "Cohort metrics")),
      opportunitiesApi.applicationProfileStatus(api, candidateId, { signal: controller.signal })
        .then(response => responseJson<OpportunityApplicationProfileStatus>(response, "Application profile")),
      opportunitiesApi.providerStatus(api, { signal: controller.signal })
        .then(response => responseJson<OpportunityProviderStatus>(response, "Provider status")),
      opportunitiesApi.coverageStatus(api, candidateId, { signal: controller.signal })
        .then(response => responseJson<OpportunityCoverageStatus>(response, "Coverage status")),
    ]).then(([candidate, status, funnel, candidates, cohortMetrics, applicationStatus, paidStatus, coverageStatus]) => {
      setProfile({
        ...DEFAULT_PROFILE,
        ...candidate,
        preferred_technical_tracks: candidate.preferred_technical_tracks || [],
        accepted_opportunity_types: candidate.accepted_opportunity_types || DEFAULT_PROFILE.accepted_opportunity_types,
      });
      setCitiesDraft(candidate.accepted_india_cities.join(", "));
      setSkillsDraft((candidate.technical_skills || []).join(", "));
      setProjectsDraft((candidate.project_keywords || []).join(", "));
      setLanguagesDraft((candidate.spoken_languages || []).join(", "));
      setScan(status);
      setMetrics(funnel);
      setSavedCandidates(candidates);
      setCohort(cohortMetrics);
      setApplicationProfile(applicationStatus);
      setProviderStatus(paidStatus);
      setCoverage(coverageStatus);
    }).catch(cause => {
      if ((cause as DOMException)?.name !== "AbortError") {
        setError(cause instanceof Error ? cause.message : "Candidate setup failed");
      }
    });
    return () => controller.abort();
  }, [api, candidateId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    opportunitiesApi.list(api, candidateId, tab, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || `Opportunity queue failed (${response.status})`);
        }
        return response.json();
      })
      .then(payload => setItems(Array.isArray(payload) ? payload : []))
      .catch(cause => {
        if ((cause as DOMException)?.name !== "AbortError") {
          setError(cause instanceof Error ? cause.message : "Opportunity queue failed");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, candidateId, tab, refreshVersion]);

  useEffect(() => {
    if (scan.status !== "running") return;
    const timer = window.setInterval(() => {
      opportunitiesApi.scanStatus(api, candidateId)
        .then(response => responseJson<OpportunityScanStatus>(response, "Scan status"))
        .then(status => {
          setScan(status);
          if (status.status === "completed") {
            setRefreshVersion(value => value + 1);
            opportunitiesApi.providerStatus(api)
              .then(response => responseJson<OpportunityProviderStatus>(response, "Provider status"))
              .then(setProviderStatus)
              .catch(() => undefined);
            opportunitiesApi.coverageStatus(api, candidateId)
              .then(response => responseJson<OpportunityCoverageStatus>(response, "Coverage status"))
              .then(setCoverage)
              .catch(() => undefined);
          }
        })
        .catch(cause => setError(cause instanceof Error ? cause.message : "Scan status failed"));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [api, candidateId, scan.status]);

  const saveCandidate = () => {
    const normalized = candidateDraft.trim();
    if (!normalized) return;
    localStorage.setItem(CANDIDATE_KEY, normalized);
    setCandidateId(normalized);
  };

  const applyEliteAiInternshipPreset = () => {
    setProfile(value => ({
      ...value,
      current_degree_level: "bachelors",
      currently_enrolled: true,
      preferred_technical_tracks: ["ai_ml", "backend", "data"],
      accepted_opportunity_types: ["internship"],
      allow_india_onsite: true,
      allow_india_hybrid: true,
      allow_india_remote: true,
      allow_worldwide_remote: true,
      allow_unpaid: false,
      allow_bond: false,
      minimum_monthly_compensation_inr: 100_000,
      target_monthly_compensation_inr: 200_000,
      minimum_monthly_compensation_usd: 1_200,
      target_monthly_compensation_usd: 2_400,
      unknown_compensation_policy: "review",
      maximum_internship_months: 6,
    }));
  };

  const profileBody = () => ({
    consent_confirmed_at: profile.consent_confirmed_at,
    home_country: "IN",
    graduation_year: profile.graduation_year,
    currently_enrolled: profile.currently_enrolled,
    current_degree_level: profile.current_degree_level,
    accepted_india_cities: citiesDraft.split(",").map(value => value.trim()).filter(Boolean),
    technical_skills: skillsDraft.split(",").map(value => value.trim()).filter(Boolean),
    project_keywords: projectsDraft.split(",").map(value => value.trim()).filter(Boolean),
    spoken_languages: languagesDraft.split(",").map(value => value.trim()).filter(Boolean),
    preferred_technical_tracks: profile.preferred_technical_tracks,
    accepted_opportunity_types: profile.accepted_opportunity_types,
    allow_india_onsite: profile.allow_india_onsite,
    allow_india_hybrid: profile.allow_india_hybrid,
    allow_india_remote: profile.allow_india_remote,
    allow_worldwide_remote: profile.allow_worldwide_remote,
    allow_unpaid: profile.allow_unpaid,
    allow_bond: profile.allow_bond,
    professional_experience_years: profile.professional_experience_years,
    minimum_monthly_compensation_inr: profile.minimum_monthly_compensation_inr,
    target_monthly_compensation_inr: profile.target_monthly_compensation_inr,
    minimum_monthly_compensation_usd: profile.minimum_monthly_compensation_usd,
    target_monthly_compensation_usd: profile.target_monthly_compensation_usd,
    unknown_compensation_policy: profile.unknown_compensation_policy,
    maximum_internship_months: profile.maximum_internship_months,
  });

  const persistProfile = async () => {
    setSaving(true);
    setError("");
    try {
      const response = await opportunitiesApi.saveCandidate(api, candidateId, profileBody());
      const saved = await responseJson<OpportunityCandidate>(response, "Saving candidate profile");
      setProfile({ ...DEFAULT_PROFILE, ...saved });
      setCitiesDraft(saved.accepted_india_cities.join(", "));
      setSkillsDraft(saved.technical_skills.join(", "));
      setProjectsDraft(saved.project_keywords.join(", "));
      setLanguagesDraft(saved.spoken_languages.join(", "));
      setRefreshVersion(value => value + 1);
      const metricsResponse = await opportunitiesApi.metrics(api, candidateId);
      setMetrics(await responseJson<OpportunityFunnelMetrics>(metricsResponse, "Pilot metrics"));
      const cohortResponse = await opportunitiesApi.cohortMetrics(api);
      setCohort(await responseJson<OpportunityCohortMetrics>(cohortResponse, "Cohort metrics"));
      const candidatesResponse = await opportunitiesApi.candidates(api);
      setSavedCandidates(await responseJson<OpportunityCandidateSummary[]>(candidatesResponse, "Saved candidates"));
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Saving candidate profile failed");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const startScan = async () => {
    if (!await persistProfile()) return;
    setSaving(true);
    try {
      const response = await opportunitiesApi.startScan(api, candidateId);
      const status = await responseJson<OpportunityScanStatus>(response, "Starting opportunity scan");
      setScan(status);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Starting opportunity scan failed");
    } finally {
      setSaving(false);
    }
  };

  const trackOpportunity = async (opportunityId: string) => {
    setTrackingId(opportunityId);
    setError("");
    try {
      const response = await opportunitiesApi.track(api, candidateId, opportunityId);
      await responseJson(response, "Adding opportunity to application pipeline");
      setTrackedIds(previous => new Set(previous).add(opportunityId));
      const metricsResponse = await opportunitiesApi.metrics(api, candidateId);
      setMetrics(await responseJson<OpportunityFunnelMetrics>(metricsResponse, "Pilot metrics"));
      const cohortResponse = await opportunitiesApi.cohortMetrics(api);
      setCohort(await responseJson<OpportunityCohortMetrics>(cohortResponse, "Cohort metrics"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Adding opportunity to pipeline failed");
    } finally {
      setTrackingId("");
    }
  };

  const recordOutcome = async (opportunityId: string) => {
    const eventType = outcomeDrafts[opportunityId] || "application_submitted";
    setOutcomeSavingId(opportunityId);
    setError("");
    try {
      const response = await opportunitiesApi.recordOutcome(api, candidateId, opportunityId, eventType);
      await responseJson(response, "Recording application outcome");
      setTrackedIds(previous => new Set(previous).add(opportunityId));
      const metricsResponse = await opportunitiesApi.metrics(api, candidateId);
      setMetrics(await responseJson<OpportunityFunnelMetrics>(metricsResponse, "Pilot metrics"));
      const cohortResponse = await opportunitiesApi.cohortMetrics(api);
      setCohort(await responseJson<OpportunityCohortMetrics>(cohortResponse, "Cohort metrics"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Recording application outcome failed");
    } finally {
      setOutcomeSavingId("");
    }
  };

  const linkCurrentProfile = async () => {
    setLinkingProfile(true);
    setError("");
    try {
      if (!applicationPreview) {
        const response = await opportunitiesApi.previewApplicationProfile(api, candidateId);
        setApplicationPreview(await responseJson<OpportunityApplicationProfilePreview>(response, "Reviewing application profile"));
        return;
      }
      const response = await opportunitiesApi.snapshotApplicationProfile(api, candidateId, applicationPreview.payload_sha256, applicationIdentity);
      setApplicationProfile(await responseJson<OpportunityApplicationProfileStatus>(response, "Linking application profile"));
      setApplicationPreview(null);
    } catch (cause) {
      if (applicationPreview) setApplicationPreview(null);
      setError(cause instanceof Error ? cause.message : "Linking application profile failed");
    } finally {
      setLinkingProfile(false);
    }
  };

  const previewCandidateResume = async (file: File) => {
    setLinkingProfile(true);
    setError("");
    try {
      const response = await opportunitiesApi.previewCandidateResume(api, candidateId, file);
      setResumePreview(await responseJson<OpportunityCandidateResumePreview>(response, "Parsing candidate resume"));
      setApplicationPreview(null);
    } catch (cause) {
      setResumePreview(null);
      setError(cause instanceof Error ? cause.message : "Candidate resume parsing failed");
    } finally {
      setLinkingProfile(false);
    }
  };

  const confirmCandidateResume = async () => {
    if (!resumePreview) return;
    setLinkingProfile(true);
    setError("");
    try {
      const response = await opportunitiesApi.confirmCandidateResume(api, candidateId, resumePreview, applicationIdentity);
      setApplicationProfile(await responseJson<OpportunityApplicationProfileStatus>(response, "Linking candidate resume"));
      setResumePreview(null);
    } catch (cause) {
      setResumePreview(null);
      setError(cause instanceof Error ? cause.message : "Linking candidate resume failed");
    } finally {
      setLinkingProfile(false);
    }
  };

  const toggleTrack = (track: OpportunityTechnicalTrack) => {
    setProfile(value => ({
      ...value,
      preferred_technical_tracks: value.preferred_technical_tracks.includes(track)
        ? value.preferred_technical_tracks.filter(item => item !== track)
        : [...value.preferred_technical_tracks, track],
    }));
  };

  const toggleOpportunityType = (kind: OpportunityTypePreference) => {
    setProfile(value => ({
      ...value,
      accepted_opportunity_types: value.accepted_opportunity_types.includes(kind)
        ? value.accepted_opportunity_types.length === 1
          ? value.accepted_opportunity_types
          : value.accepted_opportunity_types.filter(item => item !== kind)
        : [...value.accepted_opportunity_types, kind],
    }));
  };

  const activeTab = TABS.find(item => item.id === tab)!;
  return (
    <section className="opportunity-page">
      <header className="opportunity-hero">
        <div>
          <span className="eyebrow">Early-career CSE opportunity engine</span>
          <h2>One live requisition. One honest decision.</h2>
          <p>India onsite/hybrid or remote that explicitly includes India. Unknown geography never silently passes.</p>
        </div>
        <form
          className="opportunity-candidate"
          onSubmit={event => { event.preventDefault(); saveCandidate(); }}
        >
          <label htmlFor="opportunity-candidate-id">Local candidate ID</label>
          <div>
            <input
              id="opportunity-candidate-id"
              list="opportunity-candidate-list"
              value={candidateDraft}
              onChange={event => setCandidateDraft(event.target.value)}
              maxLength={240}
              aria-describedby="opportunity-candidate-note"
            />
            <datalist id="opportunity-candidate-list">
              {savedCandidates.map(candidate => <option key={candidate.candidate_id} value={candidate.candidate_id} />)}
            </datalist>
            <button type="submit">Load queue</button>
          </div>
          <small id="opportunity-candidate-note">Candidate decisions stay in this local workspace.</small>
          <div className={`opportunity-profile-link ${applicationProfile.ready ? "ready" : "missing"}`}>
            <span>
              {resumePreview
                ? `Confirm uploaded resume: ${resumePreview.profile_name} · ${resumePreview.evidence_count} evidence items`
                : applicationPreview
                ? `Confirm ${applicationPreview.profile_name} · ${applicationPreview.evidence_count} evidence items`
                : applicationProfile.ready ? "Application profile linked" : "Application profile required for truthful documents"}
            </span>
            <div className="opportunity-identity-fields" aria-label="Candidate-specific application identity">
              {([
                ["email", "Candidate email"], ["phone", "Candidate phone"],
                ["city", "Current city"], ["linkedin_url", "LinkedIn URL"],
                ["github_url", "GitHub URL"], ["website_url", "Portfolio URL"],
              ] as Array<[keyof OpportunityApplicationIdentity, string]>).map(([key, label]) => (
                <label key={key}>
                  <span>{label}{key === "email" || key === "phone" ? " *" : ""}</span>
                  <input
                    type={key === "email" ? "email" : key === "phone" ? "tel" : "text"}
                    value={applicationIdentity[key]}
                    onChange={event => setApplicationIdentity(value => ({ ...value, [key]: event.target.value }))}
                    autoComplete="off"
                    maxLength={key === "phone" ? 80 : 500}
                  />
                </label>
              ))}
            </div>
            <div className="opportunity-profile-actions">
              {resumePreview ? (
                <button type="button" onClick={() => void confirmCandidateResume()} disabled={linkingProfile || !applicationIdentityReady}>
                  {linkingProfile ? "Linking…" : `Confirm ${resumePreview.profile_name}`}
                </button>
              ) : (
                <button type="button" onClick={() => void linkCurrentProfile()} disabled={linkingProfile || !profile.consent_confirmed_at || !applicationIdentityReady}>
                  {linkingProfile
                    ? "Checking…"
                    : applicationPreview ? `Confirm ${applicationPreview.profile_name}`
                      : applicationProfile.ready ? "Review current Profile" : "Use current Profile"}
                </button>
              )}
              <label className="opportunity-resume-upload">
                <span>Upload candidate resume</span>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,.md"
                  disabled={linkingProfile || !profile.consent_confirmed_at}
                  onChange={event => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) void previewCandidateResume(file);
                  }}
                />
              </label>
            </div>
          </div>
        </form>
      </header>

      <section className="opportunity-setup" aria-label="Candidate opportunity constraints">
        <div className="opportunity-campaign-preset">
          <div>
            <strong>Elite AI internship campaign</strong>
            <span>₹1L / $1.2k monthly floor · ₹2L / $2.4k target · AI, backend and data internships only</span>
          </div>
          <button type="button" onClick={applyEliteAiInternshipPreset}>Apply elite preset</button>
        </div>
        <label>
          <span>Current degree level</span>
          <select
            value={profile.current_degree_level}
            onChange={event => setProfile(value => ({
              ...value,
              current_degree_level: event.target.value as OpportunityCandidate["current_degree_level"],
            }))}
          >
            <option value="unknown">Not specified</option>
            <option value="bachelors">Bachelor&apos;s</option>
            <option value="masters">Master&apos;s</option>
            <option value="doctorate">Doctorate</option>
          </select>
        </label>
        <label>
          <span>Graduation year</span>
          <input
            type="number"
            min={2020}
            max={2040}
            value={profile.graduation_year}
            onChange={event => setProfile(value => ({ ...value, graduation_year: Number(event.target.value) }))}
          />
        </label>
        <label className="opportunity-city-field">
          <span>Accepted India cities</span>
          <input
            value={citiesDraft}
            onChange={event => setCitiesDraft(event.target.value)}
            placeholder="Bengaluru, Hyderabad, Pune"
          />
        </label>
        <label className="opportunity-evidence-field">
          <span>Technical skills</span>
          <input
            value={skillsDraft}
            onChange={event => setSkillsDraft(event.target.value)}
            placeholder="Python, FastAPI, React, Docker"
          />
        </label>
        <label className="opportunity-evidence-field">
          <span>Project evidence</span>
          <input
            value={projectsDraft}
            onChange={event => setProjectsDraft(event.target.value)}
            placeholder="RAG, REST API, PostgreSQL, CI/CD"
          />
        </label>
        <label className="opportunity-evidence-field">
          <span>Spoken languages</span>
          <input
            value={languagesDraft}
            onChange={event => setLanguagesDraft(event.target.value)}
            placeholder="English, Hindi, Kannada"
            aria-describedby="opportunity-language-note"
          />
          <small id="opportunity-language-note">Used only to verify explicit job-language requirements.</small>
        </label>
        <fieldset className="opportunity-choice-group opportunity-track-field">
          <legend>Preferred technical tracks</legend>
          <p>Leave all unselected to accept every CSE track.</p>
          <div>
            {TRACK_OPTIONS.map(option => (
              <label key={option.id}>
                <input
                  type="checkbox"
                  checked={profile.preferred_technical_tracks.includes(option.id)}
                  onChange={() => toggleTrack(option.id)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="opportunity-choice-group opportunity-type-field">
          <legend>Opportunity types</legend>
          <div>
            {TYPE_OPTIONS.map(option => (
              <label key={option.id}>
                <input
                  type="checkbox"
                  checked={profile.accepted_opportunity_types.includes(option.id)}
                  onChange={() => toggleOpportunityType(option.id)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label>
          <span>Hard floor ₹ / month</span>
          <input
            type="number"
            min={0}
            step={1000}
            value={profile.minimum_monthly_compensation_inr}
            onChange={event => setProfile(value => ({ ...value, minimum_monthly_compensation_inr: Number(event.target.value) }))}
          />
        </label>
        <label>
          <span>Target ₹ / month</span>
          <input
            type="number"
            min={0}
            step={5000}
            value={profile.target_monthly_compensation_inr}
            onChange={event => setProfile(value => ({ ...value, target_monthly_compensation_inr: Number(event.target.value) }))}
          />
        </label>
        <label>
          <span>Remote floor $ / month</span>
          <input
            type="number"
            min={0}
            step={100}
            value={profile.minimum_monthly_compensation_usd}
            onChange={event => setProfile(value => ({ ...value, minimum_monthly_compensation_usd: Number(event.target.value) }))}
          />
        </label>
        <label>
          <span>Remote target $ / month</span>
          <input
            type="number"
            min={0}
            step={100}
            value={profile.target_monthly_compensation_usd}
            onChange={event => setProfile(value => ({ ...value, target_monthly_compensation_usd: Number(event.target.value) }))}
          />
        </label>
        <label>
          <span>When pay is undisclosed</span>
          <select
            value={profile.unknown_compensation_policy}
            onChange={event => setProfile(value => ({
              ...value,
              unknown_compensation_policy: event.target.value as OpportunityCandidate["unknown_compensation_policy"],
            }))}
          >
            <option value="allow">Keep in normal queue</option>
            <option value="review">Send to review</option>
            <option value="skip">Skip</option>
          </select>
        </label>
        <label>
          <span>Max internship months</span>
          <input
            type="number"
            min={1}
            max={36}
            value={profile.maximum_internship_months}
            onChange={event => setProfile(value => ({ ...value, maximum_internship_months: Number(event.target.value) }))}
          />
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={Boolean(profile.consent_confirmed_at)}
            onChange={event => setProfile(value => ({
              ...value,
              consent_confirmed_at: event.target.checked ? new Date().toISOString() : null,
            }))}
          />
          <span>Candidate consent confirmed</span>
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={profile.currently_enrolled}
            onChange={event => setProfile(value => ({ ...value, currently_enrolled: event.target.checked }))}
          />
          <span>Currently enrolled</span>
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={profile.allow_india_onsite}
            onChange={event => setProfile(value => ({ ...value, allow_india_onsite: event.target.checked }))}
          />
          <span>India onsite</span>
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={profile.allow_india_hybrid}
            onChange={event => setProfile(value => ({ ...value, allow_india_hybrid: event.target.checked }))}
          />
          <span>India hybrid</span>
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={profile.allow_india_remote}
            onChange={event => setProfile(value => ({ ...value, allow_india_remote: event.target.checked }))}
          />
          <span>India remote</span>
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={profile.allow_worldwide_remote}
            onChange={event => setProfile(value => ({ ...value, allow_worldwide_remote: event.target.checked }))}
          />
          <span>Worldwide remote</span>
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={profile.allow_unpaid}
            onChange={event => setProfile(value => ({ ...value, allow_unpaid: event.target.checked }))}
          />
          <span>Allow unpaid</span>
        </label>
        <label className="opportunity-check">
          <input
            type="checkbox"
            checked={profile.allow_bond}
            onChange={event => setProfile(value => ({ ...value, allow_bond: event.target.checked }))}
          />
          <span>Allow employment bonds</span>
        </label>
        <div className="opportunity-scan-actions">
          <button type="button" onClick={() => void persistProfile()} disabled={saving || scan.status === "running"}>
            Save constraints
          </button>
          <button type="button" className="primary" onClick={() => void startScan()} disabled={saving || scan.status === "running" || !profile.consent_confirmed_at}>
            {scan.status === "running" ? `Scanning ${scan.target_count || ""} sources…` : "Refresh opportunities"}
          </button>
        </div>
      </section>

      {scan.status !== "idle" && (
        <div className={`opportunity-run status-${scan.status}`} role="status">
          <strong>{scan.status === "running" ? "Company-direct scan running" : `Last scan ${scan.status}`}</strong>
          <span>
            {scan.status === "completed"
              ? `${scan.opportunities || 0} canonical roles · ${scan.decision_counts?.apply_now || 0} apply now · ${scan.source_failures || 0} source failures`
              : scan.status === "failed" ? scan.error : `${scan.targets_completed || 0}/${scan.target_count || 0} ATS searches checked · ${scan.raw_rows_seen || 0} raw roles seen`}
          </span>
        </div>
      )}

      {providerStatus && (
        <section className="opportunity-providers" aria-label="Paid provider experiments">
          <header>
            <div><strong>Paid source experiments</strong><span>{providerStatus.master_enabled ? "Governed calls enabled" : "Zero-spend mode"}</span></div>
            <span>Retain at ≥10% net-new eligible yield</span>
          </header>
          <div>
            {providerStatus.providers.map(provider => (
              <article key={provider.provider} className={`provider-${provider.alert}`}>
                <div><strong>{provider.provider === "serpapi" ? "SerpApi" : provider.provider === "adzuna" ? "Adzuna" : "Jooble"}</strong><span>{words(provider.state)}</span></div>
                <p>{provider.usage.requests_today}/{provider.limits.daily_requests} today · {provider.usage.requests_month}/{provider.limits.monthly_requests} month</p>
                <p>{provider.usage.net_new_eligible_opportunities} net-new eligible · {provider.usage.net_new_eligible_yield_percent}% yield</p>
                <small>{words(provider.experiment.benchmark)}</small>
              </article>
            ))}
          </div>
        </section>
      )}

      {coverage && (
        <section className="opportunity-cohort" aria-label="Market coverage inventory">
          <div><span>Indexed canonicals</span><strong>{coverage.index.canonical_opportunity_count.toLocaleString("en-IN")}</strong></div>
          <div><span>Verified active</span><strong>{coverage.index.active_opportunity_count.toLocaleString("en-IN")}</strong></div>
          <div><span>Lifecycle unresolved</span><strong>{(coverage.index.status_counts.unknown || 0).toLocaleString("en-IN")}</strong></div>
          <div><span>Indexed observations</span><strong>{coverage.index.observation_count.toLocaleString("en-IN")}</strong></div>
          <div><span>Index observed through</span><strong>{coverage.index.latest_observed_at ? new Date(coverage.index.latest_observed_at).toLocaleString("en-IN") : "Not installed"}</strong></div>
          <div><span>Index installed</span><strong>{coverage.index.last_sync ? new Date(coverage.index.last_sync.completed_at).toLocaleString("en-IN") : "Not recorded"}</strong></div>
          <div><span>Free/direct targets</span><strong>{coverage.inventory_target_count}</strong></div>
          <div><span>Provider families</span><strong>{coverage.inventory_provider_count} + {coverage.paid_provider_count} paid</strong></div>
          <div><span>Candidate refresh targets</span><strong>{coverage.attempted_target_count} / {coverage.inventory_target_count}</strong></div>
          <div><span>Refresh failures</span><strong>{coverage.health_counts.failure || 0}</strong></div>
          <div><span>Refresh raw rows</span><strong>{coverage.raw_rows}</strong></div>
          <div><span>Refresh accepted</span><strong>{coverage.accepted_source_records}</strong></div>
        </section>
      )}

      {cohort && (
        <section className="opportunity-cohort" aria-label="Five candidate pilot progress">
          <div><span>Pilot cohort</span><strong>{cohort.candidate_count} / {cohort.targets.candidate_count}</strong></div>
          {cohort.pending_candidate_count > 0 && <div><span>Pending consent/profile</span><strong>{cohort.pending_candidate_count}</strong></div>}
          <div><span>Applications</span><strong>{cohort.funnel.application_submitted} / {cohort.targets.application_submitted}</strong></div>
          <div><span>Replies / next steps</span><strong>{cohort.funnel.meaningful_contacts} / {cohort.targets.meaningful_contacts}</strong></div>
          <div><span>Interviews</span><strong>{cohort.funnel.interviews} / {cohort.targets.interviews}</strong></div>
          <div><span>Candidates with traction</span><strong>{cohort.candidates_with_traction} / {cohort.targets.candidates_with_traction}</strong></div>
        </section>
      )}

      {metrics && (
        <section className="opportunity-funnel" aria-label="Candidate interview funnel">
          <article><span>Tracked</span><strong>{metrics.funnel.tracked}</strong></article>
          <article><span>Submitted</span><strong>{metrics.funnel.application_submitted}</strong></article>
          <article><span>Replies / next steps</span><strong>{metrics.funnel.meaningful_contacts}</strong></article>
          <article><span>Interviews</span><strong>{metrics.funnel.interviews}</strong></article>
          <article><span>Offers</span><strong>{metrics.funnel.offers}</strong></article>
          <article className="north-star"><span>Interviews / 20 apps</span><strong>{metrics.rates.interviews_per_20_applications}</strong></article>
        </section>
      )}

      <nav className="opportunity-tabs" aria-label="Opportunity decision queues">
        {TABS.map(item => (
          <button
            key={item.id}
            className={tab === item.id ? "active" : ""}
            onClick={() => setTab(item.id)}
            title={item.promise}
          >
            <strong>{item.label}</strong>
          </button>
        ))}
      </nav>

      <div className="opportunity-queue-head">
        <div><strong>{activeTab.label}</strong><span>{activeTab.promise}</span></div>
        <span>{loading ? "Measuring…" : `${items.length} canonical opportunities`}</span>
      </div>

      {error && <div className="opportunity-state error" role="alert">{error}</div>}
      {!error && loading && <div className="opportunity-state">Loading verified candidate decisions…</div>}
      {!error && !loading && items.length === 0 && (
        <div className="opportunity-state empty">
          <strong>No {activeTab.label.toLowerCase()} records for “{candidateId}” yet.</strong>
          <span>Save the constraints and refresh opportunities. Empty is safer than inventing applicability.</span>
        </div>
      )}
      {!error && !loading && items.length > 0 && (
        <div className="opportunity-grid">
          {items.map(item => {
            const facts = item.applicability;
            const concerns = [
              ...facts.hard_blockers,
              ...facts.safety_blockers,
              ...(facts.safety_warnings || []),
              ...facts.unknowns,
              ...(facts.candidate_evidence_missing ? ["candidate skill evidence missing"] : []),
            ];
            return (
              <article key={item.opportunity_id} className={`opportunity-card decision-${facts.decision}`}>
                <div className="opportunity-card-top">
                  <div>
                    <span className="opportunity-company">{item.employer_name}</span>
                    <h3>{item.title}</h3>
                  </div>
                  <span className={`opportunity-status status-${item.lifecycle.status}`}>{words(item.lifecycle.status)}</span>
                </div>
                <p className="opportunity-location">{item.location_text || "Workplace not supplied"}</p>
                <div className="opportunity-facts">
                  <span>priority {facts.priority_score}</span>
                  <span>growth {facts.career_growth_score}</span>
                  <span>hiring confidence {facts.hiring_confidence_score}</span>
                  <span>fit {facts.candidate_fit_score}</span>
                  <span>pay score {facts.compensation_score ?? 50}</span>
                  <span>{words(facts.opportunity_type)}</span>
                  <span>{words(facts.technical_track)}</span>
                  <span>{words(facts.workplace_scope)}</span>
                  <span>{facts.paid_status === "unknown" ? "pay unknown" : words(facts.paid_status)}</span>
                  {(facts.monthly_compensation_inr?.length || 0) > 0 && (
                    <span>₹{Math.min(...(facts.monthly_compensation_inr || [])).toLocaleString("en-IN")}/mo observed</span>
                  )}
                  {(facts.monthly_compensation_usd?.length || 0) > 0 && (
                    <span>${Math.min(...(facts.monthly_compensation_usd || [])).toLocaleString("en-US")}/mo observed</span>
                  )}
                  {facts.target_compensation_met === true && <span>target pay met</span>}
                  {(facts.internship_duration_months?.length || 0) > 0 && (
                    <span>up to {Math.max(...(facts.internship_duration_months || []))} months</span>
                  )}
                  {(facts.graduation_years?.length || 0) > 0 && (
                    <span>classes {facts.graduation_years?.join(", ")}</span>
                  )}
                  {(facts.minimum_experience_years || 0) > 0 && (
                    <span>{facts.minimum_experience_years}+ years requested</span>
                  )}
                  {facts.required_degree_level && facts.required_degree_level !== "unknown" && (
                    <span>minimum degree: {words(facts.required_degree_level)}</span>
                  )}
                  {(facts.required_language_groups?.length || 0) > 0 && (
                    <span>
                      languages: {facts.required_language_groups
                        ?.map(group => group.join(" or "))
                        .join(" + ")}
                    </span>
                  )}
                  {facts.requires_current_enrollment && <span>enrollment required</span>}
                  {facts.work_authorization_restricted && <span>authorization restricted</span>}
                </div>
                {(facts.career_signals?.length > 0 || facts.matched_skills?.length > 0) && (
                  <div className="opportunity-growth">
                    {facts.career_signals.map(signal => <span key={signal}>{words(signal)}</span>)}
                    {facts.matched_skills.map(skill => <span key={`skill-${skill}`}>match: {skill}</span>)}
                  </div>
                )}
                {concerns.length > 0 && (
                  <div className="opportunity-concerns">
                    {concerns.slice(0, 4).map(concern => <span key={concern}>{words(concern)}</span>)}
                  </div>
                )}
                {facts.decision !== "skip" && (
                  <div className="opportunity-outcome">
                    <label htmlFor={`outcome-${item.opportunity_id}`}>Record real outcome</label>
                    <div>
                      <select
                        id={`outcome-${item.opportunity_id}`}
                        value={outcomeDrafts[item.opportunity_id] || "application_submitted"}
                        onChange={event => setOutcomeDrafts(previous => ({
                          ...previous,
                          [item.opportunity_id]: event.target.value as OpportunityOutcomeType,
                        }))}
                      >
                        {OUTCOME_OPTIONS.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
                      </select>
                      <button
                        type="button"
                        className="secondary"
                        disabled={outcomeSavingId === item.opportunity_id}
                        onClick={() => void recordOutcome(item.opportunity_id)}
                      >
                        {outcomeSavingId === item.opportunity_id ? "Saving…" : "Save outcome"}
                      </button>
                    </div>
                  </div>
                )}
                <footer>
                  <small>{item.source_count} source observation{item.source_count === 1 ? "" : "s"} · {item.providers.join(", ")}</small>
                  <div className="opportunity-card-actions">
                    {facts.decision !== "skip" && (
                      <button
                        className="secondary"
                        disabled={trackingId === item.opportunity_id || trackedIds.has(item.opportunity_id)}
                        onClick={() => void trackOpportunity(item.opportunity_id)}
                      >
                        {trackedIds.has(item.opportunity_id) ? "Tracked" : trackingId === item.opportunity_id ? "Adding…" : "Track application"}
                      </button>
                    )}
                    <button onClick={() => void openExternalUrl(item.canonical_apply_url)}>Open application</button>
                  </div>
                </footer>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
