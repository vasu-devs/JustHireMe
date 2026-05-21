import { describe, expect, it } from "vitest";
import { entryTitle, mergeProfileWithGraphFallback, normalizeProfileResponse, profileDeleteKey, profileDeletePath, profileFromGraphStats, removeProfileItem } from "./profileUtils";

const fieldText = (item: unknown, key: string): string =>
  item && typeof item === "object" && key in item
    ? String((item as Record<string, unknown>)[key] || "")
    : "";

describe("normalizeProfileResponse", () => {
  it("normalizes partial profile payloads instead of rejecting them", () => {
    const profile = normalizeProfileResponse({
      n: "Vasu",
      identity: { email: "vasu@example.com" },
      certs: ["AWS"],
      awards: ["Shipped"],
    });

    expect(profile.n).toBe("Vasu");
    expect(profile.skills).toEqual([]);
    expect(profile.projects).toEqual([]);
    expect(profile.exp).toEqual([]);
    expect(profile.certifications).toEqual(["AWS"]);
    expect(profile.achievements).toEqual(["Shipped"]);
    expect(profile.identity.email).toBe("vasu@example.com");
    expect(profile.identity.github_url).toBe("");
  });
});

describe("profileDeletePath", () => {
  it("encodes text profile entries so slashes and spaces survive routing", () => {
    expect(profileDeletePath("education", "B.Tech / MBA")).toBe("/api/v1/profile/education/B.Tech%20%2F%20MBA");
  });
});

describe("profile delete labels", () => {
  it("uses stable ids when available and human labels as fallback", () => {
    expect(entryTitle({ role: "Engineer", co: "Acme" })).toBe("Engineer at Acme");
    expect(profileDeleteKey({ id: "proj-1", title: "Hiring Agent" })).toBe("proj-1");
    expect(profileDeleteKey({ title: "B.Tech / MBA" })).toBe("B.Tech / MBA");
    expect(profileDeleteKey({ n: "FastAPI" })).toBe("FastAPI");
  });
});

describe("graph profile fallback", () => {
  const stats = {
    candidate: 1,
    skill: 2,
    project: 1,
    experience: 0,
    joblead: 0,
    graph: {
      nodes: [
        { id: "candidate:vasu", label: "VASU", type: "Candidate", subtitle: "AI engineer" },
        { id: "project:justhireme", label: "JustHireMe", type: "Project", subtitle: "Python, React" },
        { id: "skill:python", label: "Python", type: "Skill", subtitle: "general" },
        { id: "skill:react", label: "React", type: "Skill", subtitle: "general" },
      ],
      edges: [
        { source: "candidate:vasu", target: "project:justhireme", type: "BUILT" },
        { source: "candidate:vasu", target: "skill:python", type: "HAS_SKILL" },
        { source: "project:justhireme", target: "skill:react", type: "PROJ_UTILIZES" },
      ],
    },
  };

  it("derives profile rows from graph evidence", () => {
    const profile = profileFromGraphStats(stats);

    expect(profile?.n).toBe("VASU");
    expect(profile?.projects.map((project) => fieldText(project, "title"))).toEqual(["JustHireMe"]);
    expect(profile?.skills.map((skill) => fieldText(skill, "n")).sort()).toEqual(["Python", "React"]);
  });

  it("fills sparse profile payloads from graph stats", () => {
    const profile = mergeProfileWithGraphFallback({ n: "", skills: [], projects: [], exp: [] }, stats);

    expect(profile.n).toBe("VASU");
    expect(profile.skills.length).toBe(2);
    expect(profile.projects.length).toBe(1);
  });

  it("derives profile rows from vector-backed embedding points when graph links are missing", () => {
    const profile = mergeProfileWithGraphFallback(
      { n: "Vasu", s: "AI engineer", skills: [], projects: [], exp: [] },
      {
        candidate: 0,
        skill: 0,
        project: 0,
        experience: 0,
        joblead: 0,
        graph: { nodes: [], edges: [] },
        embedding: {
          available: true,
          points: [
            { id: "typescript", label: "TypeScript", type: "Skill", subtitle: "seed", x: 0.1, y: 0.2 },
            { id: "gitart", label: "GitArt", type: "Project", stack: "TypeScript, React", text: "Generated art workflow", x: 0.2, y: 0.3 },
            { id: "cert-1", label: "Cloud Cert", type: "Certification", x: 0.3, y: 0.4 },
          ],
        },
      },
    );

    expect(profile.n).toBe("Vasu");
    expect(profile.skills.map((skill) => fieldText(skill, "n"))).toEqual(["TypeScript"]);
    expect(profile.projects.map((project) => fieldText(project, "title"))).toEqual(["GitArt"]);
    expect(profile.certifications).toEqual(["Cloud Cert"]);
  });
});

describe("removeProfileItem", () => {
  it("removes stored skills without treating project stack tags as skill rows", () => {
    const profile = normalizeProfileResponse({
      skills: [{ id: "fastapi", n: "FastAPI", cat: "backend" }, { id: "react", n: "React", cat: "frontend" }],
      projects: [{ id: "proj-1", title: "API", stack: ["FastAPI"], repo: "", impact: "" }],
    });

    const next = removeProfileItem(profile, "skill", "fastapi");
    const firstProject = next.projects[0];
    const firstProjectStack = firstProject && typeof firstProject === "object" && "stack" in firstProject
      ? firstProject.stack
      : [];

    expect(next.skills.map((skill) => fieldText(skill, "n"))).toEqual(["React"]);
    expect(firstProjectStack).toEqual(["FastAPI"]);
  });

  it("removes profile rows by fallback labels for text and structured entries", () => {
    const profile = normalizeProfileResponse({
      exp: [{ role: "Engineer", co: "Acme" }, { role: "Designer", co: "Beta" }],
      education: ["B.Tech / MBA", "MSc"],
      certifications: ["AWS"],
      achievements: ["Shipped"],
    });

    expect(removeProfileItem(profile, "experience", "Engineer at Acme").exp.map((item) => fieldText(item, "role"))).toEqual(["Designer"]);
    expect(removeProfileItem(profile, "education", "B.Tech%20%2F%20MBA").education).toEqual(["MSc"]);
    expect(removeProfileItem(profile, "certification", "AWS").certifications).toEqual([]);
    expect(removeProfileItem(profile, "achievement", "Shipped").achievements).toEqual([]);
  });
});
