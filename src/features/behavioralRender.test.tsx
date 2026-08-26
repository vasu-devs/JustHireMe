import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { DashboardView } from "./dashboard/DashboardView";
import { ApplyJobView } from "./apply/ApplyJobView";
import { JobCard } from "./pipeline/components/JobCard";
import { ApprovalDrawer } from "./pipeline/components/ApprovalDrawer";
import { IngestionView } from "./profile/IngestionView";
import { ProfileView } from "./profile/ProfileView";
import { OpportunitiesView } from "./opportunities/OpportunitiesView";
import { hasRequiredApplicationIdentity } from "./opportunities/opportunityIdentity";
import ErrorBoundary from "../shared/components/ErrorBoundary";
import type { ApiFetch, Lead } from "../types";

vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));

const okResponse = (body: unknown = {}) => ({
  ok: true,
  status: 200,
  json: async () => body,
  blob: async () => new Blob(["pdf"], { type: "application/pdf" }),
}) as Response;

const api: ApiFetch = vi.fn(async () => okResponse({
  n: "Ada Lovelace",
  skills: [{ n: "Python", cat: "technical" }],
  projects: [],
  exp: [],
}));

const lead: Lead = {
  job_id: "lead-1",
  title: "Backend Engineer",
  company: "Acme AI",
  url: "https://example.com/jobs/1",
  platform: "manual",
  status: "approved",
  asset: "",
  score: 91,
  signal_score: 84,
  reason: "Strong FastAPI match",
  description: "Build Python APIs and reliable AI workflows.",
  match_points: ["Python", "FastAPI"],
  gaps: [],
  source_meta: { seniority_level: "junior" },
};

describe("high-risk component behavioral render coverage", () => {
  it("renders DashboardView with live lead data and primary controls", () => {
    const html = renderToStaticMarkup(
      <DashboardView
        leads={[lead]}
        dueFollowups={[lead]}
        logs={[{ id: 1, ts: "now", msg: "scan complete", src: "test", kind: "agent" }]}
        setView={vi.fn()}
        openDrawer={vi.fn()}
        scanning={false}
        reevaluating={false}
        cleaning={false}
        progress={{ active: false, mode: null, total: 0, completed: 0, current: "", updatedAt: 0 }}
        onScan={vi.fn()}
        onStopScan={vi.fn()}
        onReevaluate={vi.fn()}
        onStopReevaluate={vi.fn()}
        onCleanup={vi.fn()}
        scanErr={null}
      />,
    );

    expect(html).toContain("Find work");
    expect(html).toContain("Your next focused move");
    expect(html).toContain("Acme AI");
    expect(html).toContain("Backend Engineer");
  });

  it("renders JobCard and keeps generation CTA visible", () => {
    const html = renderToStaticMarkup(
      <JobCard lead={lead} onOpen={vi.fn()} onDelete={vi.fn()} showScore showGenerate port={1420} api={api} />,
    );

    expect(html).toContain("Backend Engineer");
    expect(html).toContain("Generate Package");
    expect(html).toContain("91%");
  });

  it("renders profile and ingestion entry points without crashing", () => {
    const profileHtml = renderToStaticMarkup(<ProfileView api={api} setView={vi.fn()} />);
    const ingestionHtml = renderToStaticMarkup(<IngestionView api={api} />);

    expect(profileHtml).toContain("Profile");
    expect(ingestionHtml).toContain("Resume");
  });

  it("exposes degree and spoken-language eligibility in the candidate opportunity setup", () => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
    });
    try {
      const html = renderToStaticMarkup(<OpportunitiesView api={api} />);
      expect(html).toContain("Current degree level");
      expect(html).toContain("Bachelor&#x27;s");
      expect(OpportunitiesView.toString()).toContain("minimum degree:");
      expect(OpportunitiesView.toString()).toContain("required_language_groups");
      expect(html).toContain("Spoken languages");
      expect(html).toContain("Used only to verify explicit job-language requirements.");
      expect(html).toContain("Candidate consent confirmed");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("keeps candidate profile confirmation locked until contact identity is complete", () => {
    expect(hasRequiredApplicationIdentity({
      email: "candidate@example.com", phone: "+91 98765 43210",
      city: "", linkedin_url: "", github_url: "", website_url: "",
    })).toBe(true);
    expect(hasRequiredApplicationIdentity({
      email: "candidate@example.com", phone: "   ",
      city: "", linkedin_url: "", github_url: "", website_url: "",
    })).toBe(false);
    expect(hasRequiredApplicationIdentity({
      email: " ", phone: "+91 98765 43210",
      city: "", linkedin_url: "", github_url: "", website_url: "",
    })).toBe(false);
  });

  it("renders apply and approval workflows with mocked API surface", () => {
    const applyHtml = renderToStaticMarkup(
      <ApplyJobView port={1420} api={api} leads={[lead]} openDrawer={vi.fn()} initialInput="https://example.com/jobs/1" />,
    );
    const drawerHtml = renderToStaticMarkup(<ApprovalDrawer j={lead} api={api} onClose={vi.fn()} />);

    expect(applyHtml).toContain("job");
    expect(drawerHtml).toContain("Backend Engineer");
    expect(drawerHtml).toContain("Mark as applied");
  });

  it("reports ErrorBoundary crashes through the configured API", () => {
    const boundary = new ErrorBoundary({ label: "Pipeline", api, children: null });
    const nextState = ErrorBoundary.getDerivedStateFromError(new Error("boom"));

    expect(nextState.error.message).toBe("boom");
    boundary.componentDidCatch(new Error("boom"), { componentStack: "\n<Component />" });
    expect(api).toHaveBeenCalledWith("/api/v1/errors", expect.objectContaining({ method: "POST" }));
  });
});

