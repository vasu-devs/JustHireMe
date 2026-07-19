import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const app = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const dashboard = readFileSync(new URL("./dashboard/DashboardView.tsx", import.meta.url), "utf8");
const jobCard = readFileSync(new URL("./pipeline/components/JobCard.tsx", import.meta.url), "utf8");
const profile = readFileSync(new URL("./profile/ProfileView.tsx", import.meta.url), "utf8");
const ingestion = readFileSync(new URL("./profile/IngestionView.tsx", import.meta.url), "utf8");
const errorBoundary = readFileSync(new URL("../shared/components/ErrorBoundary.tsx", import.meta.url), "utf8");
const approvalDrawer = readFileSync(new URL("./pipeline/components/ApprovalDrawer.tsx", import.meta.url), "utf8");
const semanticRuntimePrompt = readFileSync(new URL("../shared/components/SemanticRuntimePrompt.tsx", import.meta.url), "utf8");
const updatePrompt = readFileSync(new URL("../shared/components/UpdatePrompt.tsx", import.meta.url), "utf8");
const settingsModal = readFileSync(new URL("./settings/SettingsModal.tsx", import.meta.url), "utf8");
const stylesheet = readFileSync(new URL("../index.css", import.meta.url), "utf8");

describe("FIX.md frontend stability contracts", () => {
  it("keeps App wrapped with recovery and subsystem degradation surfaces", () => {
    expect(app).toContain("ErrorBoundary");
    expect(app).toContain("SubsystemBanner");
    expect(app).toContain("SemanticRuntimePrompt");
    expect(app).toContain("/api/v1/health/subsystems");
  });

  it("keeps dashboard primary operations wired", () => {
    expect(dashboard).toContain("onScan");
    expect(dashboard).toContain("onReevaluate");
    expect(dashboard).toContain("onCleanup");
    // Journal redesign: the live agent-status surface is the "Scout kept
    // watch" line (was "Agent Online" in the pre-journal dashboard).
    expect(dashboard).toContain("Scout kept watch");
  });

  it("keeps job cards actionable from the pipeline", () => {
    expect(jobCard).toContain("onDelete");
    expect(jobCard).toContain("showGenerate");
    expect(jobCard).toContain("/generate");
  });

  it("keeps the profile dossier read surface wired", () => {
    expect(profile).toContain("/api/v1/profile");
    expect(profile).toContain("Recheck profile");
    expect(profile).not.toContain("deleteQueueRef");
  });

  it("keeps per-item deletion single-flight guarded", () => {
    // Restored after the dossier redesign dropped it: concurrent backend
    // DELETEs from rapid double clicks were a real bug class (graph-lock
    // contention), so deletion must stay behind a same-tick flight guard.
    expect(profile).toContain("deleteFlightRef");
    expect(profile).toContain("window.confirm");
    expect(profile).toContain("profileDeletePath");
  });

  it("keeps profile and ingestion flows connected to their API contracts", () => {
    expect(profile).toContain("/api/v1/profile");
    expect(ingestion).toContain("/api/v1/ingest");
    expect(ingestion).toContain("/api/v1/template");
  });

  it("keeps error reporting and approval workflow controls present", () => {
    expect(errorBoundary).toContain("getDerivedStateFromError");
    expect(errorBoundary).toContain("/api/v1/errors");
    expect(approvalDrawer).toContain("/status");
    expect(approvalDrawer).toContain("/feedback");
    expect(approvalDrawer).toContain("Mark as applied");
  });

  it("keeps required runtime pack mandatory", () => {
    // Simplified compact banner: still a mandatory install/restart flow, just
    // with terse button copy. Assert the guarantees the UI must keep, not the
    // old verbose strings.
    expect(semanticRuntimePrompt).toContain("/api/v1/runtime/vector");
    expect(semanticRuntimePrompt).toContain("/api/v1/runtime/vector/install");
    expect(semanticRuntimePrompt).toContain("installInFlightRef");
    expect(semanticRuntimePrompt).toContain("Runtime pack required for semantic matching.");
    expect(semanticRuntimePrompt).toContain("restart_required");
    expect(semanticRuntimePrompt).toContain("RUNTIME_STATUS_TIMEOUT_MS = 90000");
    expect(semanticRuntimePrompt).not.toContain("timeoutMs: 15000");
    expect(semanticRuntimePrompt).not.toContain("Later");
    expect(semanticRuntimePrompt).not.toContain("initialized once per interpreter");
  });

  it("keeps updater reachable above mandatory runtime blockers", () => {
    expect(stylesheet).toMatch(/\.update-toast\s*{[^}]*z-index:\s*260;/s);
    expect(stylesheet).toMatch(/\.semantic-runtime-banner\s*{[^}]*z-index:\s*180;/s);
  });

  it("keeps updater downloads resilient to release asset transport hiccups", () => {
    expect(updatePrompt).toContain("downloadAndInstall");
    expect(updatePrompt).toContain("UPDATE_DOWNLOAD_TIMEOUT_MS");
    expect(updatePrompt).toContain("Cache-Control");
    expect(updatePrompt).toContain("isRetryableUpdateDownloadError");
  });

  it("does not persist pending update restart state across app launches", () => {
    expect(updatePrompt).toContain("sessionStorage.getItem(PENDING_RESTART_KEY)");
    expect(updatePrompt).toContain("sessionStorage.setItem(PENDING_RESTART_KEY");
    expect(updatePrompt).not.toContain("localStorage.getItem(PENDING_RESTART_KEY)");
  });

  it("does not present expected setup states as broken UI", () => {
    expect(app).toContain("isActionableSubsystemIssue");
    expect(app).toContain('name === "llm"');
    expect(settingsModal).toContain('"Saved"');
    expect(settingsModal).toContain('"Saving..."');
    expect(settingsModal).not.toContain("? Saved");
    expect(settingsModal).not.toContain("Saving?");
  });
});
