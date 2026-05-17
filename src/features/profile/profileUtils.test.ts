import { describe, expect, it } from "vitest";
import { entryTitle, normalizeProfileResponse, profileDeleteKey, profileDeletePath, removeProfileItem } from "./profileUtils";

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

describe("removeProfileItem", () => {
  it("removes stored skills without treating project stack tags as skill rows", () => {
    const profile = normalizeProfileResponse({
      skills: [{ id: "fastapi", n: "FastAPI", cat: "backend" }, { id: "react", n: "React", cat: "frontend" }],
      projects: [{ id: "proj-1", title: "API", stack: ["FastAPI"], repo: "", impact: "" }],
    });

    const next = removeProfileItem(profile, "skill", "fastapi");

    expect(next.skills.map((skill: any) => skill.n)).toEqual(["React"]);
    expect(next.projects[0].stack).toEqual(["FastAPI"]);
  });

  it("removes profile rows by fallback labels for text and structured entries", () => {
    const profile = normalizeProfileResponse({
      exp: [{ role: "Engineer", co: "Acme" }, { role: "Designer", co: "Beta" }],
      education: ["B.Tech / MBA", "MSc"],
      certifications: ["AWS"],
      achievements: ["Shipped"],
    });

    expect(removeProfileItem(profile, "experience", "Engineer at Acme").exp.map((item: any) => item.role)).toEqual(["Designer"]);
    expect(removeProfileItem(profile, "education", "B.Tech%20%2F%20MBA").education).toEqual(["MSc"]);
    expect(removeProfileItem(profile, "certification", "AWS").certifications).toEqual([]);
    expect(removeProfileItem(profile, "achievement", "Shipped").achievements).toEqual([]);
  });
});
