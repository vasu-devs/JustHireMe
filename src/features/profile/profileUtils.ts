import type { GraphStats } from "../../types";

const IDENTITY_KEYS = ["email", "phone", "linkedin_url", "github_url", "website_url", "city"] as const;

export type ProfileTextType = "education" | "certification" | "achievement";

type ProfileRecord = Record<string, unknown>;

const asArray = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const asRecord = (value: unknown): ProfileRecord =>
  value && typeof value === "object" && !Array.isArray(value) ? value as ProfileRecord : {};

const textOrEmpty = (value: unknown): string => {
  if (typeof value === "string" || typeof value === "number") return String(value);
  return "";
};

const joinedLabel = (values: unknown[], separator: string): string =>
  values.map(textOrEmpty).filter(Boolean).join(separator);

export const entryTitle = (item: unknown): string =>
  typeof item === "string"
    ? item
    : textOrEmpty(
        asRecord(item).title
        || asRecord(item).name
        || asRecord(item).n
        || joinedLabel([asRecord(item).role, asRecord(item).co], " at ")
        || asRecord(item).id
        || "",
      );

export const profileDeleteKey = (item: unknown): string => {
  if (typeof item === "string") return item;
  const source = asRecord(item);
  return String(source.id || entryTitle(source));
};

export function normalizeProfileResponse(data: unknown) {
  const source = asRecord(data);
  const identitySource = asRecord(source.identity);
  const identity = Object.fromEntries(
    IDENTITY_KEYS.map(key => [key, String(identitySource[key] || source[key] || "")]),
  );

  return {
    ...source,
    n: String(source.n || ""),
    s: String(source.s || ""),
    skills: asArray(source.skills),
    projects: asArray(source.projects),
    exp: asArray(source.exp),
    education: asArray(source.education),
    certifications: asArray(source.certifications || source.certs),
    achievements: asArray(source.achievements || source.awards),
    identity,
  };
}

export function profileHasContent(profile: unknown) {
  const source = normalizeProfileResponse(profile);
  return Boolean(
    source.n.trim()
    || source.s.trim()
    || source.skills.length
    || source.projects.length
    || source.exp.length
    || source.education.length
    || source.certifications.length
    || source.achievements.length
    || Object.values(source.identity).some(value => String(value || "").trim()),
  );
}

const graphId = (id: unknown, prefix: string): string => {
  const text = String(id || "");
  return text.startsWith(`${prefix}:`) ? text.slice(prefix.length + 1) : text;
};

const goodLabel = (value: unknown): string => String(value || "").trim();

const splitTerms = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map(goodLabel).filter(Boolean);
  return String(value || "")
    .replace(/[;|]/g, ",")
    .split(",")
    .map(part => part.trim())
    .filter(Boolean);
};

const mergeRows = (baseRows: unknown[], fallbackRows: unknown[]) => {
  const seen = new Set<string>();
  const rows: unknown[] = [];
  for (const item of [...baseRows, ...fallbackRows]) {
    const marker = String(profileDeleteKey(item) || entryTitle(item)).trim().toLowerCase();
    if (!marker || seen.has(marker)) continue;
    seen.add(marker);
    rows.push(item);
  }
  return rows;
};

const mergeFallbackProfiles = (baseProfile: unknown, fallbackProfile: unknown) => {
  const base = normalizeProfileResponse(baseProfile);
  const fallback = normalizeProfileResponse(fallbackProfile);
  return normalizeProfileResponse({
    ...base,
    n: base.n || fallback.n,
    s: base.s || fallback.s,
    skills: mergeRows(base.skills, fallback.skills),
    projects: mergeRows(base.projects, fallback.projects),
    exp: mergeRows(base.exp, fallback.exp),
    education: mergeRows(base.education, fallback.education),
    certifications: mergeRows(base.certifications, fallback.certifications),
    achievements: mergeRows(base.achievements, fallback.achievements),
    identity: { ...fallback.identity, ...Object.fromEntries(Object.entries(base.identity).filter(([, value]) => String(value || "").trim())) },
  });
};

const pointText = (point: unknown, ...keys: string[]): string => {
  const source = asRecord(point);
  for (const key of keys) {
    const text = goodLabel(source[key]);
    if (text) return text;
  }
  return "";
};

function profileFromEmbeddingStats(stats: GraphStats | null | undefined) {
  const points = stats?.embedding?.points || [];
  if (!points.length) return null;

  const candidate = points.find(point =>
    point.type === "Candidate"
    && !["candidate", "profile", "complete profile"].includes(point.label.trim().toLowerCase()),
  );
  const profilePoint = points.find(point => point.type === "Profile");
  const profilePointLabel = profilePoint && !["candidate", "profile", "complete profile"].includes(profilePoint.label.trim().toLowerCase())
    ? profilePoint.label
    : "";

  const skills = points
    .filter(point => point.type === "Skill")
    .map(point => ({ id: graphId(point.id, "skill"), n: goodLabel(point.label), cat: goodLabel(point.subtitle) || "vector" }))
    .filter(skill => skill.n);

  const projects = points
    .filter(point => point.type === "Project")
    .map(point => {
      const source = point as Record<string, unknown>;
      return {
        id: graphId(point.id, "project"),
        title: goodLabel(point.label),
        stack: splitTerms(source.stack || point.subtitle),
        repo: "",
        impact: pointText(source, "impact", "description", "text", "summary"),
      };
    })
    .filter(project => project.title);

  const exp = points
    .filter(point => point.type === "Experience")
    .map(point => {
      const source = point as Record<string, unknown>;
      return {
        id: graphId(point.id, "experience"),
        role: goodLabel(point.label),
        co: pointText(source, "company", "co", "subtitle"),
        period: pointText(source, "period"),
        d: pointText(source, "description", "d", "text", "summary"),
      };
    })
    .filter(item => item.role || item.co);

  const textPoints = (type: string) => points.filter(point => point.type === type).map(point => goodLabel(point.label)).filter(Boolean);

  const profile = normalizeProfileResponse({
    n: candidate?.label || profilePointLabel || "",
    s: pointText(candidate as Record<string, unknown>, "summary", "text", "subtitle"),
    skills,
    projects,
    exp,
    education: textPoints("Education"),
    certifications: textPoints("Certification"),
    achievements: textPoints("Achievement"),
  });
  return profileHasContent(profile) ? profile : null;
}

function profileFromGraphNodes(stats: GraphStats | null | undefined) {
  const nodes = stats?.graph?.nodes || [];
  const edges = stats?.graph?.edges || [];
  if (!nodes.length) return null;

  const byId = new Map(nodes.map(node => [node.id, node]));
  const candidateNodes = nodes.filter(node => node.type === "Candidate");
  const candidateIds = new Set(candidateNodes.map(node => node.id));
  const hasCandidate = candidateIds.size > 0;
  const candidate = candidateNodes.find(node => !["candidate", "profile"].includes(node.label.trim().toLowerCase())) || candidateNodes[0];

  const targetsFrom = (types: string[], sources = candidateIds) => new Set(
    edges
      .filter(edge => types.includes(edge.type) && (!hasCandidate || sources.has(edge.source)))
      .map(edge => edge.target),
  );

  const projectIds = targetsFrom(["BUILT"]);
  const experienceIds = targetsFrom(["WORKED_AS"]);
  const credentialIds = targetsFrom(["HAS_EDUCATION", "HAS_CERTIFICATION", "HAS_ACHIEVEMENT"]);
  if (!hasCandidate) {
    nodes.forEach(node => {
      if (node.type === "Project") projectIds.add(node.id);
      if (node.type === "Experience") experienceIds.add(node.id);
      if (node.type === "Credential") credentialIds.add(node.id);
    });
  }

  const skillIds = targetsFrom(["HAS_SKILL"]);
  for (const edge of edges) {
    if ((projectIds.has(edge.source) && edge.type === "PROJ_UTILIZES") || (experienceIds.has(edge.source) && edge.type === "EXP_UTILIZES")) {
      skillIds.add(edge.target);
    }
  }
  if (!skillIds.size) {
    nodes.filter(node => node.type === "Skill").forEach(node => skillIds.add(node.id));
  }

  const skills = [...skillIds]
    .map(id => byId.get(id))
    .filter(Boolean)
    .map(node => ({ id: graphId(node!.id, "skill"), n: goodLabel(node!.label), cat: goodLabel(node!.subtitle) || "graph" }))
    .filter(skill => skill.n);

  const skillNameById = new Map(skills.map(skill => [`skill:${skill.id}`, skill.n]));
  const projects = [...projectIds]
    .map(id => byId.get(id))
    .filter(Boolean)
    .map(node => {
      const stack = edges
        .filter(edge => edge.source === node!.id && edge.type === "PROJ_UTILIZES")
        .map(edge => skillNameById.get(edge.target) || goodLabel(byId.get(edge.target)?.label))
        .filter(Boolean);
      return {
        id: graphId(node!.id, "project"),
        title: goodLabel(node!.label),
        stack: stack.length ? stack : (goodLabel(node!.subtitle) ? [goodLabel(node!.subtitle)] : []),
        repo: "",
        impact: "",
      };
    })
    .filter(project => project.title);

  const exp = [...experienceIds]
    .map(id => byId.get(id))
    .filter(Boolean)
    .map(node => ({ id: graphId(node!.id, "experience"), role: goodLabel(node!.label), co: goodLabel(node!.subtitle), period: "", d: "" }))
    .filter(item => item.role || item.co);

  const credentials = [...credentialIds].map(id => byId.get(id)).filter(Boolean);
  const education = credentials.filter(node => goodLabel(node!.subtitle).toLowerCase() === "education").map(node => goodLabel(node!.label)).filter(Boolean);
  const certifications = credentials.filter(node => goodLabel(node!.subtitle).toLowerCase() === "certification").map(node => goodLabel(node!.label)).filter(Boolean);
  const achievements = credentials.filter(node => goodLabel(node!.subtitle).toLowerCase() === "achievement").map(node => goodLabel(node!.label)).filter(Boolean);

  const profile = normalizeProfileResponse({
    n: candidate && !["candidate", "profile"].includes(candidate.label.trim().toLowerCase()) ? candidate.label : "",
    s: candidate?.subtitle || "",
    skills,
    projects,
    exp,
    education,
    certifications,
    achievements,
  });
  return profileHasContent(profile) ? profile : null;
}

export function profileFromGraphStats(stats: GraphStats | null | undefined) {
  const graphProfile = profileFromGraphNodes(stats);
  const embeddingProfile = profileFromEmbeddingStats(stats);
  if (!graphProfile) return embeddingProfile;
  if (!embeddingProfile) return graphProfile;
  const merged = mergeFallbackProfiles(graphProfile, embeddingProfile);
  return profileHasContent(merged) ? merged : null;
}

export function mergeProfileWithGraphFallback(profile: unknown, stats: GraphStats | null | undefined) {
  const base = normalizeProfileResponse(profile);
  const statsProfile = profileHasContent(stats?.profile) ? normalizeProfileResponse(stats?.profile) : null;
  const graphProfile = statsProfile && profileFromGraphStats(stats)
    ? mergeFallbackProfiles(statsProfile, profileFromGraphStats(stats))
    : statsProfile || profileFromGraphStats(stats);
  if (!graphProfile) return base;
  return normalizeProfileResponse({
    ...base,
    n: base.n || graphProfile.n,
    s: base.s || graphProfile.s,
    skills: base.skills.length ? base.skills : graphProfile.skills,
    projects: base.projects.length ? base.projects : graphProfile.projects,
    exp: base.exp.length ? base.exp : graphProfile.exp,
    education: base.education.length ? base.education : graphProfile.education,
    certifications: base.certifications.length ? base.certifications : graphProfile.certifications,
    achievements: base.achievements.length ? base.achievements : graphProfile.achievements,
    identity: { ...graphProfile.identity, ...Object.fromEntries(Object.entries(base.identity).filter(([, value]) => String(value || "").trim())) },
  });
}

export function profileDeletePath(type: string, idOrTitle: string) {
  return `/api/v1/profile/${type}/${encodeURIComponent(idOrTitle)}`;
}

const cleanDeleteToken = (value: unknown): string => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    return decodeURIComponent(raw).trim().toLowerCase();
  } catch {
    return raw.toLowerCase();
  }
};

const deleteTokenMatches = (target: string, values: unknown[]) =>
  values.some(value => cleanDeleteToken(value) === target);

export function removeProfileItem(profile: unknown, type: string, idOrTitle: string) {
  const next = normalizeProfileResponse(profile);
  const target = cleanDeleteToken(idOrTitle);
  if (!target) return next;

  const keepStructured = (item: unknown, values: unknown[]) => {
    const source = asRecord(item);
    return !deleteTokenMatches(target, [
      profileDeleteKey(item),
      entryTitle(item),
      source.id,
      ...values,
    ]);
  };
  const keepTextEntry = (item: unknown) => !deleteTokenMatches(target, [profileDeleteKey(item), entryTitle(item), item]);

  if (type === "skill") {
    next.skills = next.skills.filter((item) => {
      const source = asRecord(item);
      return keepStructured(item, [source.n, source.name, source.title]);
    });
  } else if (type === "experience") {
    next.exp = next.exp.filter((item) => {
      const source = asRecord(item);
      return keepStructured(item, [
        source.role,
        source.co,
        joinedLabel([source.role, source.co], " at "),
        joinedLabel([source.role, source.co], " - "),
      ]);
    });
  } else if (type === "project") {
    next.projects = next.projects.filter((item) => {
      const source = asRecord(item);
      return keepStructured(item, [source.title, source.name]);
    });
  } else if (type === "education") {
    next.education = next.education.filter(keepTextEntry);
  } else if (type === "certification") {
    next.certifications = next.certifications.filter(keepTextEntry);
  } else if (type === "achievement") {
    next.achievements = next.achievements.filter(keepTextEntry);
  }

  return next;
}
