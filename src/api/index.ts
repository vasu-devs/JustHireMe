/**
 * The frontend service layer: every backend call the UI makes goes through here.
 *
 * One module per backend router (backend/api/routers/<feature>.py), so a feature's
 * endpoints are in exactly one place on both sides of the wire. UI components must
 * not call `api("/api/v1/...")` directly — src/api/api-layer.test.ts enforces it.
 */
export { createApiFetch, isAbortLikeError, json, withOpts } from "./client";
export { automationApi } from "./automation";
export { dashboardApi } from "./dashboard";
export { diagnosticsApi } from "./diagnostics";
export { discoveryApi } from "./discovery";
export { eventsApi } from "./events";
export { GENERATION_TIMEOUT_MS, generationApi } from "./generation";
export { graphApi } from "./graph";
export { healthApi } from "./health";
export { helpApi } from "./help";
export { ingestionApi } from "./ingestion";
export { leadsApi } from "./leads";
export { learningApi } from "./learning";
export { opportunitiesApi } from "./opportunities";
export { profileApi } from "./profile";
export { runtimeApi } from "./runtime";
export { settingsApi } from "./settings";
export { templatesApi } from "./templates";
export type { ApiFetch, ApiFetchOptions, Lead, WSMessage } from "./types";
export type { ActivityRow, ApplicationDetail, DashboardOverview, FunnelStage, SourceRow } from "./dashboard";
export type { HelpTurn } from "./help";
export type { ProfileEntity } from "./profile";
export type {
  OpportunityCandidate,
  OpportunityCandidateResumePreview,
  OpportunityApplicationProfilePreview,
  OpportunityApplicationProfileStatus,
  OpportunityAutoApplyResult,
  OpportunityApplicationIdentity,
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
} from "./opportunities";
