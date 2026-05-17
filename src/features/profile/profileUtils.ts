const IDENTITY_KEYS = ["email", "phone", "linkedin_url", "github_url", "website_url", "city"] as const;

export type ProfileTextType = "education" | "certification" | "achievement";

const asArray = (value: unknown): any[] => Array.isArray(value) ? value : [];

export const entryTitle = (item: unknown): string =>
  typeof item === "string"
    ? item
    : String(
        (item as any)?.title
        || (item as any)?.name
        || (item as any)?.n
        || [(item as any)?.role, (item as any)?.co].filter(Boolean).join(" at ")
        || (item as any)?.id
        || "",
      );

export const profileDeleteKey = (item: unknown): string => {
  if (typeof item === "string") return item;
  const source = item && typeof item === "object" ? item as Record<string, any> : {};
  return String(source.id || entryTitle(source));
};

export function normalizeProfileResponse(data: unknown) {
  const source = data && typeof data === "object" ? data as Record<string, any> : {};
  const identitySource = source.identity && typeof source.identity === "object" ? source.identity as Record<string, any> : {};
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
    const source = item && typeof item === "object" ? item as Record<string, any> : {};
    return !deleteTokenMatches(target, [
      profileDeleteKey(item),
      entryTitle(item),
      source.id,
      ...values,
    ]);
  };
  const keepTextEntry = (item: unknown) => !deleteTokenMatches(target, [profileDeleteKey(item), entryTitle(item), item]);

  if (type === "skill") {
    next.skills = next.skills.filter((item: any) => keepStructured(item, [item?.n, item?.name, item?.title]));
  } else if (type === "experience") {
    next.exp = next.exp.filter((item: any) => keepStructured(item, [
      item?.role,
      item?.co,
      [item?.role, item?.co].filter(Boolean).join(" at "),
      [item?.role, item?.co].filter(Boolean).join(" - "),
    ]));
  } else if (type === "project") {
    next.projects = next.projects.filter((item: any) => keepStructured(item, [item?.title, item?.name]));
  } else if (type === "education") {
    next.education = next.education.filter(keepTextEntry);
  } else if (type === "certification") {
    next.certifications = next.certifications.filter(keepTextEntry);
  } else if (type === "achievement") {
    next.achievements = next.achievements.filter(keepTextEntry);
  }

  return next;
}
