import { describe, expect, it } from "vitest";

import { leadsApi } from "./leads";
import { opportunitiesApi } from "./opportunities";
import type { ApiFetch, ApiFetchOptions } from "./types";

// Vite's raw glob: every UI source file as text, no node:fs shim needed.
const sources = import.meta.glob("../**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

/** Files allowed to mention a raw /api/v1 path. Glob keys are relative to this
 *  directory, so "./x.ts" is the service layer itself and "../" is the rest of src. */
const isAllowed = (path: string) =>
  !path.startsWith("../")             // the service layer itself
  || path.startsWith("../preview/")   // the preview harness mocks fetch by matching paths
  || /\.test\.tsx?$/.test(path);      // tests assert the wire contract on purpose

describe("UI layer never calls the backend directly", () => {
  it("has no /api/v1 path outside src/api", () => {
    const offenders = Object.entries(sources)
      .filter(([path]) => !isAllowed(path))
      .filter(([, source]) => /["'`]\/api\/v1/.test(source))
      .map(([path]) => path);

    expect(offenders, "these files bypass src/api — add a client function instead").toEqual([]);
  });
});

describe("leadsApi path building", () => {
  it("builds versioned and unversioned PDF paths", () => {
    expect(leadsApi.pdfPath("job-1", "resume")).toBe("/api/v1/leads/job-1/pdf?kind=resume");
    expect(leadsApi.pdfPath("job-1", "cover_letter", 3))
      .toBe("/api/v1/leads/job-1/pdf?kind=cover_letter&version=3");
  });

  it("encodes ids that would otherwise split into path segments", () => {
    expect(leadsApi.pdfPath("a/b", "resume")).toBe("/api/v1/leads/a%2Fb/pdf?kind=resume");
  });
});

describe("opportunitiesApi profile confirmation", () => {
  const identity = {
    email: "friend@example.test", phone: "+91 98765 43210", city: "Bengaluru",
    linkedin_url: "", github_url: "", website_url: "",
  };
  it("reviews a candidate profile before posting its exact fingerprint", async () => {
    const calls: Array<{ path: string; opts?: ApiFetchOptions }> = [];
    const api: ApiFetch = async (path, opts) => {
      calls.push({ path, opts });
      return new Response("{}", { status: 200 });
    };

    await opportunitiesApi.previewApplicationProfile(api, "friend/one");
    await opportunitiesApi.snapshotApplicationProfile(api, "friend/one", "a".repeat(64), identity);

    expect(calls[0].path).toBe("/api/v1/opportunities/candidate/friend%2Fone/application-profile/preview");
    expect(calls[1].opts?.method).toBe("POST");
    expect(JSON.parse(String(calls[1].opts?.body))).toEqual({ expected_payload_sha256: "a".repeat(64), identity });
  });

  it("keeps candidate resume upload and confirmation candidate-scoped", async () => {
    const calls: Array<{ path: string; opts?: ApiFetchOptions }> = [];
    const api: ApiFetch = async (path, opts) => {
      calls.push({ path, opts });
      return new Response("{}", { status: 200 });
    };
    const file = new File(["Candidate Resume"], "resume.txt", { type: "text/plain" });
    const preview = {
      candidate_id: "friend-1",
      ready: true as const,
      profile_name: "Candidate",
      summary_preview: "Engineer",
      evidence_count: 1,
      skill_count: 1,
      project_count: 0,
      experience_count: 0,
      education_count: 0,
      payload_sha256: "b".repeat(64),
      profile: { n: "Candidate", s: "Engineer", skills: [{ n: "Python" }] },
    };

    await opportunitiesApi.previewCandidateResume(api, "friend-1", file);
    await opportunitiesApi.confirmCandidateResume(api, "friend-1", preview, identity);

    expect(calls[0].opts?.body).toBeInstanceOf(FormData);
    expect(calls[1].path).toContain("/friend-1/application-profile/resume/confirm");
    expect(JSON.parse(String(calls[1].opts?.body))).toEqual({
      expected_payload_sha256: "b".repeat(64),
      profile: preview.profile,
      identity,
    });
  });

  it("starts auto-apply through a candidate-scoped POST endpoint", async () => {
    const calls: Array<{ path: string; opts?: ApiFetchOptions }> = [];
    const api: ApiFetch = async (path, opts) => {
      calls.push({ path, opts });
      return new Response("{}", { status: 200 });
    };

    await opportunitiesApi.autoApply(api, "friend/one", "role/two");

    expect(calls[0].path).toBe(
      "/api/v1/opportunities/role%2Ftwo/auto-apply?candidate_id=friend%2Fone",
    );
    expect(calls[0].opts?.method).toBe("POST");
  });
});
