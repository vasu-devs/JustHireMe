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
    expect(dashboard).toContain("Agent Online");
  });

  it("keeps job cards actionable from the pipeline", () => {
    expect(jobCard).toContain("onDelete");
    expect(jobCard).toContain("showGenerate");
    expect(jobCard).toContain("/generate");
  });

  it("keeps profile and ingestion flows connected to their API contracts", () => {
    expect(profile).toContain("/api/v1/profile");
    expect(profile).toContain("profileDeletePath");
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
    expect(semanticRuntimePrompt).toContain("/api/v1/runtime/vector");
    expect(semanticRuntimePrompt).toContain("/api/v1/runtime/vector/install");
    expect(semanticRuntimePrompt).toContain("installInFlightRef");
    expect(semanticRuntimePrompt).toContain("formatBytes");
    expect(semanticRuntimePrompt).toContain("Install required runtime pack");
    expect(semanticRuntimePrompt).toContain("Restart JustHireMe");
    expect(semanticRuntimePrompt).toContain("Playwright Chromium");
    expect(semanticRuntimePrompt).not.toContain("Later");
  });

  it("keeps updater reachable above mandatory runtime blockers", () => {
    expect(stylesheet).toMatch(/\.update-toast\s*{[^}]*z-index:\s*260;/s);
    expect(stylesheet).toMatch(/\.semantic-runtime-backdrop\s*{[^}]*z-index:\s*180;/s);
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
