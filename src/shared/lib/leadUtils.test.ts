import { describe, expect, it } from "vitest";
import type { Lead } from "../../types";
import {
  cleanLeadText,
  getTone,
  getMark,
  isUrlOnlyText,
  leadSearchText,
  leadDisplayHeading,
  normalizeSeniority,
  roleFromUrl,
  seniorityMatches,
  seniorityLabel,
  seniorityTone,
  sortLeads,
  stripCompanyPrefix,
  uniqueLeadValues,
} from "./leadUtils";
import * as leadUtils from "./leadUtils";

const lead = (overrides: Partial<Lead> = {}): Lead => ({
  job_id: overrides.job_id || "lead",
  title: overrides.title || "Engineer",
  company: overrides.company || "Acme",
  url: overrides.url || "",
  platform: overrides.platform || "test",
  status: overrides.status || "discovered",
  asset: overrides.asset || "",
  score: overrides.score ?? 0,
  reason: overrides.reason || "",
  match_points: overrides.match_points || [],
  ...overrides,
});

describe("normalizeSeniority", () => {
  it("normalizes known seniority labels", () => {
    expect(normalizeSeniority("Senior")).toBe("senior");
    expect(normalizeSeniority("SENIOR")).toBe("senior");
    expect(normalizeSeniority("Entry Level")).toBe("junior");
  });

  it("returns unknown for empty or unrecognized values", () => {
    expect(normalizeSeniority(null)).toBe("unknown");
    expect(normalizeSeniority(undefined)).toBe("unknown");
    expect(normalizeSeniority("")).toBe("unknown");
    expect(normalizeSeniority("wizard")).toBe("unknown");
  });
});

describe("seniorityMatches", () => {
  it("matches all leads when the filter is all", () => {
    expect(seniorityMatches(lead({ seniority_level: "Senior" }), "all")).toBe(true);
    expect(seniorityMatches(lead({ seniority_level: "" }), "all")).toBe(true);
  });

  it("matches and rejects specific seniority filters", () => {
    const senior = lead({ seniority_level: "Senior" });
    expect(seniorityMatches(senior, "senior")).toBe(true);
    expect(seniorityMatches(senior, "junior")).toBe(false);
  });
});

describe("sortLeads", () => {
  it("keeps newest input first for newest sort", () => {
    const later = lead({ job_id: "later", source_meta: { created_at: "2026-05-02" } });
    const earlier = lead({ job_id: "earlier", source_meta: { created_at: "2026-05-01" } });
    expect(sortLeads([later, earlier], "newest").map(l => l.job_id)).toEqual(["later", "earlier"]);
  });

  it("sorts by signal and match score", () => {
    expect(sortLeads([
      lead({ job_id: "low", signal_score: 20 }),
      lead({ job_id: "high", signal_score: 80 }),
    ], "signal").map(l => l.job_id)).toEqual(["high", "low"]);

    expect(sortLeads([
      lead({ job_id: "low", score: 30 }),
      lead({ job_id: "high", score: 90 }),
    ], "match").map(l => l.job_id)).toEqual(["high", "low"]);
  });

  it("preserves order for ties", () => {
    expect(sortLeads([
      lead({ job_id: "first", signal_score: 50 }),
      lead({ job_id: "second", signal_score: 50 }),
    ], "signal").map(l => l.job_id)).toEqual(["first", "second"]);
  });

  it("sorts by company and recommended priority", () => {
    expect(sortLeads([
      lead({ job_id: "z", company: "Zulu", title: "Backend" }),
      lead({ job_id: "a", company: "Acme", title: "Frontend" }),
    ], "company").map(l => l.job_id)).toEqual(["a", "z"]);

    expect(sortLeads([
      lead({ job_id: "contacted", signal_score: 80, last_contacted_at: "2026-05-01" }),
      lead({ job_id: "fresh", signal_score: 80 }),
      lead({ job_id: "budget", signal_score: 80, budget: "$80/hr" }),
      lead({ job_id: "learned", signal_score: 80, learning_delta: 4 }),
    ], "recommended").map(l => l.job_id)).toEqual(["learned", "contacted", "budget", "fresh"]);
  });
});

describe("leadDisplayHeading", () => {
  it("returns the title when company is absent", () => {
    expect(leadDisplayHeading(lead({ title: "Frontend Engineer", company: "" })).role).toBe("Frontend Engineer");
  });

  it("strips a company prefix from the title", () => {
    expect(leadDisplayHeading(lead({ title: "Acme | Engineer", company: "Acme" })).role).toBe("Engineer");
  });

  it("derives a readable role when an old lead title is only a URL", () => {
    expect(leadDisplayHeading(lead({
      title: "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
      url: "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
      company: "Wellfound",
    })).role).toBe("AI Research Data Science Intern");
  });
});

describe("stripCompanyPrefix", () => {
  it("strips a leading company prefix", () => {
    expect(stripCompanyPrefix("Acme - Engineer", "Acme")).toBe("Engineer");
  });

  it("leaves non-prefix strings unchanged", () => {
    expect(stripCompanyPrefix("Engineer at Acme", "Acme")).toBe("Engineer at Acme");
  });
});

describe("getMark", () => {
  it("returns the first letter uppercased", () => {
    expect(getMark("anthropic")).toBe("A");
  });

  it("returns a fallback mark for empty company names", () => {
    expect(getMark("")).toBe("?");
  });
});

describe("lead utility formatting helpers", () => {
  it("builds searchable text and unique values", () => {
    const items = [
      lead({ company: "Acme", title: "AI Engineer", signal_tags: ["agent"], tech_stack: ["FastAPI"] }),
      lead({ company: "Beta", title: "React Engineer", platform: "x" }),
      lead({ company: "Acme", title: "Duplicate" }),
    ];
    expect(leadSearchText(items[0])).toContain("fastapi");
    expect(uniqueLeadValues(items, "company")).toEqual(["Acme", "Beta"]);
  });

  it("cleans URL-only text and derives roles from URLs", () => {
    expect(cleanLeadText("  hello\nworld  ")).toBe("hello world");
    expect(isUrlOnlyText("https://example.com/jobs/backend-engineer")).toBe(true);
    expect(isUrlOnlyText("Backend Engineer https://example.com")).toBe(false);
    expect(roleFromUrl("example.com/jobs/123-senior-llm-engineer-abcdef1234")).toBe("Senior LLM Engineer");
  });

  it("maps seniority and status labels to stable display values", () => {
    expect(seniorityLabel("beginner")).toBe("Beginner");
    expect(seniorityTone("fresher")).toBe("teal");
    expect(getTone("accepted")).toBe("teal");
    expect(getTone("discarded")).toBe("red");
    expect(getTone("matched")).toBe("green");
    expect(getTone("bidding")).toBe("teal");
    expect(getTone("proposal_sent")).toBe("purple");
    expect(getTone("awarded")).toBe("blue");
    expect(getTone("completed")).toBe("green");
    expect(getTone("unknown-status")).toBe("blue");
  });
});

describe("runtime demo data", () => {
  it("does not export fake onboarding jobs", () => {
    expect(JSON.stringify(leadUtils)).not.toMatch(/jobs\.example\.com|NimbusWorks/);
  });
});
