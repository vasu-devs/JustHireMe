from __future__ import annotations
import logging

import re
from typing import Any
from urllib.parse import unquote, urlparse

from models.schema import C, E, P, S

# Canonical skill alias map now lives in the data layer so non-profile layers
# (e.g. data/graph/connection.py) can use it without crossing import boundaries.
# Re-exported here for backward compatibility with existing call sites.
from data.skill_taxonomy import SKILL_CANONICAL

# Precompile the whole-token alias patterns ONCE at import. The ingest skill-scan
# runs this vocabulary against every project + experience description; the old code
# rebuilt a fresh regex for each of the ~77 entries on every call.
_SKILL_SCAN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![a-z0-9+#.-])" + re.escape(raw) + r"(?![a-z0-9+#.-])"), canonical)
    for raw, canonical in SKILL_CANONICAL.items()
]


def scan_skills_in_text(text: str) -> set[str]:
    """Canonical skills whose alias appears as a whole token in ``text`` (case-insensitive)."""
    if not text:
        return set()
    lowered = text.lower()
    return {canonical for pattern, canonical in _SKILL_SCAN_PATTERNS if pattern.search(lowered)}


SECTION_TITLES = {
    "about",
    "achievements",
    "certifications",
    "contact",
    "education",
    "experience",
    "featured projects",
    "featured work",
    "portfolio",
    "projects",
    "selected projects",
    "selected work",
    "skills",
    "technical expertise",
    "technical skills",
    "work",
}

NON_PROJECT_TITLES = SECTION_TITLES | {
    "ai agents & automation",
    "backend",
    "contact me",
    "frontend",
    "languages",
    "services",
    "tools",
}

LOCATION_WORDS = {
    "andhra pradesh",
    "bengaluru",
    "bangalore",
    "chandigarh",
    "delhi",
    "haryana",
    "hyderabad",
    "india",
    "jalandhar",
    "karnataka",
    "maharashtra",
    "mumbai",
    "new delhi",
    "noida",
    "punjab",
    "remote",
    "uttar pradesh",
}

EDUCATION_ANCHOR_RE = re.compile(
    r"\b(university|college|institute|school|academy|polytechnic|b\.?\s?tech|bachelor|master|m\.?\s?tech|"
    r"b\.?\s?e\.?|m\.?\s?e\.?|bsc|msc|bca|mca|mba|ph\.?d|degree|diploma)\b",
    re.I,
)
INSTITUTION_ANCHOR_RE = re.compile(r"\b(university|college|institute|school|academy|polytechnic)\b", re.I)
DEGREE_ANCHOR_RE = re.compile(
    r"\b(b\.?\s?tech|bachelor|master|m\.?\s?tech|b\.?\s?e\.?|m\.?\s?e\.?|bsc|msc|bca|mca|mba|ph\.?d|degree|diploma)\b",
    re.I,
)
GRADE_RE = re.compile(r"\b(cgpa|gpa|grade|percentage|marks?|score)\b|^\d+(?:\.\d+)?\s*/\s*\d+$|^\d+(?:\.\d+)?$", re.I)
DATE_RE = re.compile(r"\b(?:19|20)\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)
ACTION_SENTENCE_RE = re.compile(
    r"^(built|created|developed|designed|engineered|implemented|integrated|led|launched|shipped|supports?|"
    r"automated|optimized|improved|reduced|increased|features?|worked|used|using|maintained|deployed)\b",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s|)]+|www\.[^\s|)]+", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
CERT_DATE_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*'?\.?\s*\d{2,4}\b|\b(?:19|20)\d{2}\b",
    re.I,
)
GENERIC_PROJECT_TITLE_FRAGMENTS = {
    "api",
    "apis",
    "conditioning",
    "certificate link",
    "github",
    "repo",
    "repository",
    "live",
    "demo",
    "link",
    "source code",
}
CERTIFICATE_ISSUERS = {
    "nptel",
    "coursera",
    "udemy",
    "edx",
    "aws",
    "google",
    "microsoft",
    "oracle",
    "meta",
    "ibm",
    "linkedin learning",
}
REPO_METADATA_SKILL_RE = re.compile(
    r"(?i)(?:"
    r"^\d+(?:\.\d+)?\s+(?:forks?|stars?|watchers?|issues?|prs?|pull\s+requests?|commits?|branches?|repos?)$|"
    r"\b(?:maintained|updated|pushed|created)\s+(?:through|until|on|at)\s+(?:19|20)\d{2}(?:-\d{2}){0,2}\b|"
    r"\b(?:last\s+pushed|pushed\s+at|updated\s+at|created\s+at)\b|"
    r"\b(?:live\s+preview|deployed\s+live|accessible\s+via|fully\s+client-side)\b"
    r")"
)
GENERIC_SKILL_DENYLIST = {
    "copy",
    "fork",
    "forks",
    "maintain",
    "maintained",
    "preview",
    "send",
    "sent",
    "star",
    "stars",
    "updated",
}


def normalize_profile_payload(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data or {})
    candidate = _normalize_candidate(data.get("candidate") or data)
    identity = dict(data.get("identity") or {})
    skills = normalize_skills(data.get("skills") or [])
    experience = normalize_experiences(data.get("experience") or [])
    projects = normalize_projects(data.get("projects") or [], known_skills=[item["name"] for item in skills])
    education = normalize_education_entries(data.get("education") or [])
    certifications = normalize_text_entries(data.get("certifications") or data.get("certs") or [], kind="certification")
    achievements = normalize_text_entries(data.get("achievements") or data.get("awards") or [], kind="achievement")

    return {
        **data,
        "candidate": candidate,
        "identity": identity,
        "skills": skills,
        "experience": experience,
        "projects": projects,
        "education": [{"title": item} for item in education],
        "certifications": [{"title": item} for item in certifications],
        "achievements": [{"title": item} for item in achievements],
    }


def normalize_candidate_model(profile: C) -> C:
    payload = normalize_profile_payload({
        "candidate": {"name": profile.n, "summary": profile.s},
        "skills": [{"name": skill.n, "category": skill.cat} for skill in profile.skills],
        "experience": [
            {"role": exp.role, "company": exp.co, "period": exp.period, "description": exp.d, "skills": exp.s}
            for exp in profile.exp
        ],
        "projects": [
            {"title": project.title, "stack": project.stack, "repo": project.repo or "", "impact": project.impact}
            for project in profile.projects
        ],
        "education": profile.education,
        "certifications": profile.certifications,
        "achievements": profile.achievements,
    })
    clean_name = payload["candidate"].get("name", "")
    return C(
        n=clean_name or "Candidate",
        s=payload["candidate"].get("summary", "") or profile.s,
        skills=[S(n=item["name"], cat=item.get("category", "general")) for item in payload["skills"]],
        exp=[
            E(
                role=item.get("role", ""),
                co=item.get("company", ""),
                period=item.get("period", ""),
                d=item.get("description", ""),
                s=list(item.get("skills") or []),
            )
            for item in payload["experience"]
        ],
        projects=[
            P(
                title=item["title"],
                stack=_stack_list(item.get("stack")),
                repo=item.get("repo") or "",
                impact=item.get("impact", ""),
                s=_stack_list(item.get("stack")),
            )
            for item in payload["projects"]
        ],
        education=[item["title"] for item in payload["education"]],
        certifications=[item["title"] for item in payload["certifications"]],
        achievements=[item["title"] for item in payload["achievements"]],
    )


def normalize_skills(raw_items: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_items:
        item = _as_dict(raw)
        value = item.get("name", item.get("n", raw if isinstance(raw, str) else ""))
        category = _clean_inline_text(item.get("category", item.get("cat", "general"))) or "general"
        for skill in split_skill_names(str(value or "")):
            if not _valid_skill(skill):
                continue
            key = _key(skill)
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": skill, "category": category})
    return out[:100]


def split_skill_names(value: str) -> list[str]:
    clean = _clean_inline_text(re.sub(r"^[A-Za-z /&+-]{2,35}:\s*", "", value or ""))
    if not clean:
        return []
    if ACTION_SENTENCE_RE.search(clean) and len(clean.split()) > 5:
        return []
    clean = clean.replace("•", ",").replace("|", ",").replace(";", ",")
    parts = [_clean_skill_token(part) for part in re.split(r",|\n|/", clean) if _clean_skill_token(part)]
    if len(parts) == 1:
        compact_hits = _known_skill_hits(parts[0])
        if len(compact_hits) >= 2:
            return compact_hits
    out: list[str] = []
    for part in parts:
        known_hits = _known_skill_hits(part)
        if len(known_hits) >= 2 and len(part.split()) > 2:
            out.extend(known_hits)
        else:
            out.append(_canonical_skill(part))
    return _dedupe(out)


def normalize_experiences(raw_items: list[Any]) -> list[dict[str, Any]]:
    """Clean and de-duplicate work experiences.

    The same job is often extracted more than once (LLM pass + deterministic
    heuristic, or a single block re-emitted), producing duplicate entries with
    near-identical wording. De-duplicate on a normalized role+company key and
    keep the richest variant (longest description, filled period, merged skills)
    instead of repeating the role.
    """
    out: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for raw in raw_items:
        item = _as_dict(raw)
        role = _clean_inline_text(str(item.get("role") or "")).strip()
        co = _clean_inline_text(str(item.get("company") or item.get("co") or "")).strip()
        if not role and not co:
            continue
        period = str(item.get("period") or "").strip()
        description = str(item.get("description") or item.get("d") or "").strip()
        skills = [str(s).strip() for s in (item.get("skills") or item.get("s") or []) if str(s).strip()]
        key = _key(f"{role} {co}")
        if not key:
            continue
        existing = index.get(key)
        if existing is not None:
            if len(description) > len(existing.get("description", "")):
                existing["description"] = description
            if not existing.get("period") and period:
                existing["period"] = period
            if skills:
                existing["skills"] = _dedupe([*(existing.get("skills") or []), *skills])
            continue
        entry = {"role": role, "company": co, "period": period, "description": description, "skills": skills}
        index[key] = entry
        out.append(entry)
    return out


def _short_project_title(text: str) -> str:
    """Salvage a concise project title from a longer detail/sentence string."""
    base = _clean_inline_text(str(text or ""))
    base = re.split(r"[.\n;:|]", base)[0].strip(" -*•")
    words = base.split()
    return " ".join(words[:8]) if words else ""


def normalize_projects(raw_items: list[Any], *, known_skills: list[str] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    known = {_key(skill) for skill in (known_skills or [])}
    for raw in raw_items:
        item = _as_dict(raw)
        raw_title = str(item.get("title") or item.get("name") or item.get("n") or "")
        raw_impact = str(item.get("impact") or item.get("description") or "")
        repo = _clean_repo_url(str(item.get("repo") or item.get("url") or "") or _first_url(f"{raw_title} {raw_impact}"))
        title = _clean_project_title(raw_title)
        impact = _clean_project_detail(raw_impact)
        stack_items = normalize_stack(_project_skill_fields(item))
        url_prefix = _prefix_before_first_url(raw_impact)
        if url_prefix and len(url_prefix.split()) <= 6 and _known_skill_hits(url_prefix):
            stack_items = _dedupe(stack_items + split_skill_names(url_prefix))
            impact = _clean_inline_text(impact.replace(_clean_inline_text(url_prefix), "", 1)).strip(" |:-")

        if not _valid_project_title(title, known):
            repo_title = _repo_title_from_url(repo)
            if repo_title and _valid_project_title(repo_title, known):
                title = repo_title

        if impact and _looks_like_skill_only_text(impact):
            stack_items = _dedupe(stack_items + split_skill_names(impact))
            impact = ""

        # A project with its own repo, a real stack, or a substantial impact
        # paragraph is a standalone project, not a continuation line — never
        # absorb it into the previous entry or drop it for a detail-like title.
        # This is what caused genuine projects to go missing during ingest.
        has_substance = bool(repo) or len(stack_items) >= 2 or len(impact.split()) >= 8

        if _looks_like_stack_cluster(title) and not has_substance:
            if out:
                merged_stack = _dedupe(_stack_list(out[-1].get("stack")) + split_skill_names(title) + stack_items)
                out[-1]["stack"] = ", ".join(merged_stack)
            continue

        if _looks_like_project_detail(title) and not has_substance:
            if out:
                detail = impact or title
                if detail:
                    out[-1]["impact"] = _join_detail(out[-1].get("impact", ""), detail)
                if stack_items:
                    out[-1]["stack"] = ", ".join(_dedupe(_stack_list(out[-1].get("stack")) + stack_items))
            continue

        if not _valid_project_title(title, known):
            repo_title = _repo_title_from_url(repo)
            if repo_title and _valid_project_title(repo_title, known):
                title = repo_title
            elif has_substance:
                # Keep the project; salvage a concise title from its first clause.
                title = _short_project_title(title) or _short_project_title(impact) or title
            else:
                continue

        if not (impact or repo or stack_items or _projectish_title(title)):
            continue

        # Dedup + merge by the project's identity. The SAME project written two
        # ways — once as a plain name, once with a repo / GitHub link or URL —
        # shares a cleaned title, so key on the canonical title (falling back to
        # the repo when the title is empty). On a collision, MERGE richest-wins
        # rather than dropping: fill a missing repo, union the stacks, and keep
        # the longer impact, so no detail is lost to the duplicate.
        ident = _key(title) or _key(repo)
        cleaned = {
            **item,
            "title": title,
            "stack": ", ".join(_dedupe(stack_items)),
            "repo": repo,
            "impact": impact,
        }
        if ident in seen:
            existing = seen[ident]
            if not existing.get("repo") and repo:
                existing["repo"] = repo
            existing["stack"] = ", ".join(_dedupe(_stack_list(existing.get("stack")) + stack_items))
            if len(impact) > len(str(existing.get("impact") or "")):
                existing["impact"] = impact
            continue
        seen[ident] = cleaned
        out.append(cleaned)
    return out[:80]


def normalize_stack(value: Any) -> list[str]:
    raw_parts = value if isinstance(value, list) else re.split(r",|;|\||/", str(value or ""))
    out: list[str] = []
    for raw in raw_parts:
        out.extend(split_skill_names(str(raw)))
    return [skill for skill in _dedupe(out) if _valid_skill(skill)]


def normalize_education_entries(raw_items: list[Any]) -> list[str]:
    lines: list[str] = []
    for raw in raw_items:
        text = _entry_title(raw)
        if not text:
            continue
        split = [_clean_inline_text(part) for part in re.split(r"\n+|(?:\s+-\s+)(?=(?:cgpa|gpa|grade|19|20|\d))", text) if _clean_inline_text(part)]
        lines.extend(split or [text])

    items: list[str] = []
    current = ""
    pending_details: list[str] = []

    for line in lines:
        if _is_section_or_noise(line):
            continue
        if _education_anchor(line):
            if current and _education_same_entry(current, line):
                current = _append_detail(current, line)
            else:
                if current:
                    items.append(current)
                current = _clean_inline_text(" ".join([line, *pending_details]))
                pending_details = []
            continue
        if _education_detail(line):
            if current:
                current = _append_detail(current, line)
            else:
                pending_details.append(line)
            continue
        if current and len(line.split()) <= 8:
            current = _append_detail(current, line)

    if current:
        items.append(current)
    return _dedupe([_clean_inline_text(item) for item in items if _valid_education_item(item)])[:20]


def _education_same_entry(current: str, line: str) -> bool:
    current_clean = _clean_inline_text(current)
    line_clean = _clean_inline_text(line)
    if not current_clean or not line_clean:
        return False
    current_key = _key(current_clean)
    line_key = _key(line_clean)
    if line_key and line_key in current_key:
        return True
    current_has_institution = bool(INSTITUTION_ANCHOR_RE.search(current_clean))
    current_has_degree = bool(DEGREE_ANCHOR_RE.search(current_clean))
    line_has_institution = bool(INSTITUTION_ANCHOR_RE.search(line_clean))
    line_has_degree = bool(DEGREE_ANCHOR_RE.search(line_clean))
    return (current_has_institution and line_has_degree and not line_has_institution) or (
        current_has_degree and line_has_institution and not current_has_institution
    )


def normalize_text_entries(raw_items: list[Any], *, kind: str) -> list[str]:
    out: list[str] = []
    for raw in raw_items:
        text = _entry_title(raw)
        if kind == "certification":
            text = _clean_certification_entry(text)
            if not text:
                continue
            if _is_cert_date_line(text) and out:
                out[-1] = _append_cert_detail(out[-1], _normalize_cert_date(text))
                continue
            if _is_cert_issuer_only(text) and out:
                out[-1] = _append_cert_issuer(out[-1], text)
                continue
        if not text or _is_section_or_noise(text):
            continue
        if kind == "achievement" and _education_detail(text):
            continue
        if len(text.split()) == 1 and _key(text) in {_key(skill) for skill in SKILL_CANONICAL.values()}:
            continue
        out.append(text)
    return _dedupe(out)[:30]


def _clean_certification_entry(value: str) -> str:
    clean = _clean_inline_text(value)
    clean = re.sub(r"(?i)\b(?:credential|certificate)\s+link\b", "", clean)
    clean = re.sub(r"(?i)\b(?:view|verify|open)\s+(?:credential|certificate)\b", "", clean)
    clean = URL_RE.sub("", clean)
    clean = re.sub(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)(\d{4})\b", r"\1 \2", clean, flags=re.I)
    clean = re.sub(r"\s*[-|]{2,}\s*", " - ", clean)
    clean = _clean_inline_text(clean).strip(" -:|")
    if not clean or clean.lower() in {"certificate", "certification", "certifications", "credential", "credentials", "link"}:
        return ""
    return clean


def _is_cert_date_line(text: str) -> bool:
    clean = _clean_inline_text(text)
    return bool(clean and CERT_DATE_RE.search(clean) and len(clean.split()) <= 7 and not re.search(r"[A-Za-z]{4,}", CERT_DATE_RE.sub("", clean)))


def _normalize_cert_date(text: str) -> str:
    clean = re.sub(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)(\d{4})\b", r"\1 \2", text, flags=re.I)
    return _clean_inline_text(clean)


def _is_cert_issuer_only(text: str) -> bool:
    lower = _clean_inline_text(text).lower()
    return lower in CERTIFICATE_ISSUERS or (len(lower.split()) <= 3 and lower in CERTIFICATE_ISSUERS)


def _append_cert_detail(base: str, detail: str) -> str:
    base = _clean_inline_text(base)
    detail = _clean_inline_text(detail)
    if not detail or detail.lower() in base.lower():
        return base
    return f"{base} {detail}".strip()


def _append_cert_issuer(base: str, issuer: str) -> str:
    base = _clean_inline_text(base)
    issuer = _clean_inline_text(issuer)
    if not issuer or issuer.lower() in base.lower():
        return base
    date_match = re.search(r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[A-Za-z]*\s+\d{4}\b.*)$", base, flags=re.I)
    if date_match:
        prefix = base[:date_match.start()].strip(" -")
        return f"{prefix} - {issuer} {date_match.group(1).strip()}".strip()
    return f"{base} - {issuer}"


def _normalize_candidate(raw: Any) -> dict[str, str]:
    item = _as_dict(raw)
    name = _clean_name(str(item.get("name") or item.get("n") or ""))
    summary = _clean_summary(str(item.get("summary") or item.get("s") or ""))
    return {"name": name, "summary": summary}


def _clean_name(value: str) -> str:
    clean = _clean_inline_text(re.sub(r"(?i)^name\s*:\s*", "", value or ""))
    clean = re.split(r"\s+[|–—-]\s+", clean, maxsplit=1)[0].strip()
    role_match = re.search(
        r"\b(?:full[- ]?stack|software|frontend|backend|ai|ml|data)?\s*"
        r"(?:engineer|developer|designer|architect|student|intern)\b",
        clean,
        re.I,
    )
    if role_match:
        if role_match.start() == 0:
            return ""
        clean = clean[:role_match.start()].strip(" |-")
    if "@" in clean or "http" in clean.lower():
        return ""
    words = clean.split()
    if not (1 <= len(words) <= 5):
        return ""
    lower = clean.lower()
    if any(term in lower for term in ("portfolio", "resume", "developer", "engineer", "student")) and len(words) <= 2:
        return ""
    if not re.search(r"[A-Za-z]", clean):
        return ""
    return clean


def _clean_summary(value: str) -> str:
    lines: list[str] = []
    for raw_line in str(value or "").splitlines():
        line = _clean_inline_text(raw_line)
        if not line:
            continue
        lower = line.lower().strip(" :-")
        if lower.startswith(("email", "phone", "mobile", "links", "linkedin", "github", "portfolio", "website", "contact")):
            continue
        if lower.startswith(("targeting ", "applying to ", "job url", "url")):
            continue
        line = URL_RE.sub("", line)
        line = EMAIL_RE.sub("", line)
        line = PHONE_RE.sub("", line)
        line = _clean_inline_text(line).strip(" .;|-")
        if line:
            lines.append(line)
    clean = _clean_inline_text(" ".join(lines))
    if not clean:
        return ""
    marker_count = sum(1 for marker in ("email", "phone", "links", "linkedin", "github", "http") if marker in clean.lower())
    if marker_count >= 2:
        return ""
    if len(clean.split()) < 4 and not re.search(r"\b(engineer|developer|student|designer|analyst|scientist|builder|architect)\b", clean, re.I):
        return ""
    return clean[:900]


def _valid_skill(skill: str) -> bool:
    clean = _clean_inline_text(skill)
    lower = clean.lower()
    if not clean or len(clean) > 60 or "@" in clean or "http" in lower:
        return False
    if REPO_METADATA_SKILL_RE.search(clean):
        return False
    if lower in GENERIC_SKILL_DENYLIST:
        return False
    if _is_section_or_noise(clean) or _education_detail(clean):
        return False
    if len(clean.split()) > 5:
        return False
    if len(clean.split()) > 2 and _known_skill_hits(clean) and _key(clean) not in _known_skill_key_set():
        return False
    if len(clean.split()) == 1 and lower == clean and _key(clean) not in _known_skill_key_set():
        return False
    return not ACTION_SENTENCE_RE.search(clean)


def _valid_project_title(title: str, known_skills: set[str]) -> bool:
    if not title or len(title) > 120:
        return False
    lower = title.lower().strip(" :-")
    lower_key = _key(lower)
    if URL_RE.search(title) or EMAIL_RE.search(title):
        return False
    if lower in GENERIC_PROJECT_TITLE_FRAGMENTS or lower_key in {_key(item) for item in GENERIC_PROJECT_TITLE_FRAGMENTS}:
        return False
    if lower in NON_PROJECT_TITLES or _is_section_or_noise(title) or _education_detail(title):
        return False
    if _key(title) in known_skills or _key(title) in {_key(skill) for skill in SKILL_CANONICAL.values()}:
        return False
    words = title.split()
    if len(words) > 10:
        return False
    return not ACTION_SENTENCE_RE.search(title)


def _projectish_title(title: str) -> bool:
    return bool(re.search(r"\b(app|agent|api|dashboard|engine|framework|interface|interviewer|platform|pipeline|system|tool|workbench)\b", title, re.I))


def _looks_like_project_detail(title: str) -> bool:
    clean = _clean_inline_text(title)
    if not clean:
        return False
    if ACTION_SENTENCE_RE.search(clean):
        return True
    if clean[:1].islower() and not _projectish_title(clean):
        return True
    if re.match(r"(?i)^(and|or|with|without|while|history|tion|negotiation,|repetition\b)\b", clean):
        return True
    if clean.startswith(("-", "*", "•")):
        return True
    if len(clean.split()) > 9 and re.search(r"[.!?]$", clean):
        return True
    return bool(re.search(r"(?i)\b(summary|description|highlights?|features?|tech stack|stack)\s*:", clean))


def _looks_like_stack_cluster(title: str) -> bool:
    clean = _clean_inline_text(title)
    if not clean or len(clean) > 120:
        return False
    hits = _known_skill_hits(clean)
    return bool(len(hits) >= 2 and (len(clean.split()) <= 8 or re.search(r"[A-Za-z]\.[A-Za-z]|[a-z][A-Z]", clean)))


def _looks_like_skill_only_text(text: str) -> bool:
    clean = _clean_inline_text(text)
    if not clean:
        return False
    if _looks_like_stack_cluster(clean):
        return True
    return _key(clean) in _known_skill_key_set()


def _projectish_text(text: str) -> bool:
    return bool(re.search(r"\b(project|app|dashboard|platform|agent|pipeline|automation|api|tool|built|shipped)\b", text, re.I))


def _clean_project_title(title: str) -> str:
    clean = _clean_inline_text(re.sub(r"^\d+\s*[.)/-]*\s*", "", title or ""))
    # Strip a trailing source/URL annotation like "(GitHub)", "(github.com/…)",
    # "(branchgpt.example.com)" or "(live demo)" so the same project written two
    # ways — "Vaani" and "Vaani (GitHub)" — yields one clean title that dedupes
    # to a single node (the graph project id derives from this title).
    clean = re.sub(
        r"\s*\((?:[^)]*(?:github|gitlab|bitbucket|gitea|repo|repository|source\s*code|live|demo|"
        r"website|https?://|www\.|[a-z0-9-]+\.[a-z]{2,})[^)]*)\)\s*$",
        "",
        clean,
        flags=re.I,
    ).strip()
    clean = URL_RE.sub("", clean)
    clean = re.sub(r"(?i)\b(?:github|repo|repository|live|demo|source code)\s*:\s*$", "", clean)
    clean = re.sub(r"(?i)^(featured|selected)\s+(project|projects|work|case study)\s*[:|-]?\s*", "", clean).strip()
    clean = re.split(r"\s+(?:\|\s*)?(?:https?://|www\.)", clean, maxsplit=1, flags=re.I)[0]
    return clean.strip(" :-|.,")


def _clean_project_detail(value: str) -> str:
    clean = _clean_inline_text(value)
    clean = URL_RE.sub("", clean)
    clean = re.sub(r"(?i)\b(?:github|repo|repository|live|demo|source code|certificate link)\s*:?\s*$", "", clean)
    return _clean_inline_text(clean).strip(" :-|")


def _first_url(value: str) -> str:
    match = URL_RE.search(value or "")
    return match.group(0).rstrip(".,;") if match else ""


def _prefix_before_first_url(value: str) -> str:
    match = URL_RE.search(value or "")
    if not match:
        return ""
    return _clean_inline_text(str(value or "")[:match.start()]).strip(" |:-")


def _clean_repo_url(value: str) -> str:
    url = _first_url(value) or _clean_inline_text(value)
    if not url:
        return ""
    if url.lower().startswith("www."):
        url = "https://" + url
    return url.rstrip(".,;)")


def _repo_title_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/profile/normalization.py:_repo_title_from_url: %s', log_exc)
        return ""
    if "github.com" not in parsed.netloc.lower():
        return ""
    parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
    if len(parts) < 2:
        return ""
    name = re.sub(r"\.git$", "", parts[1], flags=re.I)
    return _clean_inline_text(name.replace("-", " ").replace("_", " ")).strip(" .:-")


def _education_anchor(line: str) -> bool:
    return bool(EDUCATION_ANCHOR_RE.search(line or ""))


def _education_detail(line: str) -> bool:
    clean = _clean_inline_text(line)
    lower = clean.lower().strip(" ,")
    if not clean:
        return False
    if lower in LOCATION_WORDS:
        return True
    if GRADE_RE.search(clean):
        return True
    return bool(DATE_RE.search(clean) and len(clean.split()) <= 6)


def _valid_education_item(item: str) -> bool:
    if not item or _is_section_or_noise(item):
        return False
    if _education_detail(item) and not _education_anchor(item):
        return False
    return _education_anchor(item)


def _known_skill_hits(text: str) -> list[str]:
    compact = re.sub(r"[^a-z0-9]+", "", text.lower())
    hits: list[str] = []
    for raw, canonical in sorted(SKILL_CANONICAL.items(), key=lambda pair: len(pair[0]), reverse=True):
        key = re.sub(r"[^a-z0-9]+", "", raw.lower())
        if len(key) < 2:
            continue
        if re.search(r"(?<![a-z0-9+#.-])" + re.escape(raw) + r"(?![a-z0-9+#.-])", text, re.I) or (len(key) > 2 and key in compact):
            hits.append(canonical)
    return _dedupe(hits)


def _known_skill_key_set() -> set[str]:
    return {_key(item) for item in [*SKILL_CANONICAL.keys(), *SKILL_CANONICAL.values()] if _key(item)}


def _canonical_skill(value: str) -> str:
    clean = _clean_skill_token(value)
    return SKILL_CANONICAL.get(clean.lower(), clean)


def _clean_skill_token(value: str) -> str:
    clean = _clean_inline_text(value)
    clean = re.sub(r"^[^\w+#.]+|[^\w+#.]+$", "", clean)
    return SKILL_CANONICAL.get(clean.lower(), clean)


def _entry_title(value: Any) -> str:
    item = _as_dict(value)
    if item:
        return _clean_inline_text(str(item.get("title") or item.get("name") or item.get("n") or ""))
    return _clean_inline_text(str(value or ""))


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value) if isinstance(value, dict) else {}


def _stack_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean_inline_text(str(item)) for item in value if _clean_inline_text(str(item))]
    return [_clean_inline_text(part) for part in str(value or "").split(",") if _clean_inline_text(part)]


def _project_skill_fields(item: dict[str, Any]) -> list[str]:
    """Collect a project's skill tokens across every recognised skill field.

    Field list lives in the data layer (``project_stack_list``) so the
    snapshot-materialize path and this normalization path stay in sync.
    Returns a flat list of raw tokens; the caller normalizes/validates them.
    """
    from data.graph.profile_base import project_stack_list

    return project_stack_list(item)


def _append_detail(base: str, detail: str) -> str:
    detail = _clean_inline_text(detail)
    if not detail or detail.lower() in base.lower():
        return base
    separator = ", " if _education_detail(detail) else " - "
    return f"{base}{separator}{detail}"


def _join_detail(base: str, detail: str) -> str:
    base = _clean_inline_text(base)
    detail = _clean_inline_text(detail)
    if not base:
        return detail
    if not detail or detail.lower() in base.lower():
        return base
    return f"{base}\n{detail}"


def _is_section_or_noise(text: str) -> bool:
    clean = _clean_inline_text(text).lower().strip(" :-")
    if not clean or clean in SECTION_TITLES:
        return True
    if re.fullmatch(r"\d+[\d,.]*(?:%|x|k)?", clean):
        return True
    return bool(re.search(r"\b(show all|view all|open|menu|close|copyright|privacy)\b", clean))


def _clean_inline_text(value: str) -> str:
    value = re.sub(r"`([^`]+)`", r"\1", value or "")
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"\*([^*]+)\*", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"^\s*[-*•]\s*", "", value)
    value = re.sub(r"\b([A-Z]\.[A-Z])\s+([a-z]{2,})\b", r"\1\2", value)
    value = re.sub(r"\b([A-Z])\.\s+([A-Za-z]{2,})\b", r"\1.\2", value)
    value = re.sub(r"\b([BFV])\s+([a-z]{2,})\b", r"\1\2", value)
    return re.sub(r"\s+", " ", value).strip()


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = _clean_inline_text(value)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out
