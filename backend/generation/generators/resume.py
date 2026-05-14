from __future__ import annotations

import re

from generation.generators.base import GeneratedAsset, _DocPackage
from generation.generators.keywords import _job_keyword_terms, _keyword_coverage
from generation.generators.outreach_email import _fallback_outreach


def _build_proof(profile: dict) -> str:
    """Build proof-of-work string from profile dict -- avoids dead PROJ_UTILIZES graph edges."""
    parts = []
    for proj in profile.get("projects", []):
        stack = proj.get("stack", [])
        if isinstance(stack, list):
            stack = ", ".join(stack)
        title  = proj.get("title", "")
        impact = proj.get("impact", "")
        if title:
            parts.append(f"Project: {title} | Stack: {stack} | Impact: {impact}")
    for exp in profile.get("exp", []):
        role   = exp.get("role", "")
        co     = exp.get("co", "")
        period = exp.get("period", "")
        desc   = exp.get("d", "")
        if role:
            parts.append(f"Role: {role} at {co} ({period}) | {desc}")
    skills = [s["n"] for s in profile.get("skills", []) if s.get("n")]
    if skills:
        parts.append(f"Skills: {', '.join(skills)}")
    return "\n".join(parts) if parts else ""


def _keywords(text: str) -> set[str]:
    stop = {
        "and", "the", "with", "for", "from", "that", "this", "you", "are",
        "job", "role", "engineer", "developer", "company", "team", "will",
        "have", "has", "using", "build", "work", "your", "their",
    }
    return {t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", text.lower()) if t not in stop}


def _clean_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -;\n\t")
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _compact_list(values: list[str], limit: int = 18) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;")
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _dedupe_sentences(values: list[str], limit: int = 8) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = _clean_sentence(value)
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _lead_text(lead: dict) -> str:
    return "\n".join([
        str(lead.get("title", "")),
        str(lead.get("company", "")),
        str(lead.get("description", "")),
        str(lead.get("reason", "")),
        "\n".join(str(item) for item in lead.get("match_points", []) or []),
    ])


def _profile_skill_names(profile: dict) -> list[str]:
    return _compact_list([str(skill.get("n", "") or skill.get("name", "")) for skill in profile.get("skills", []) or []], 80)


def _prioritized_skills(profile: dict, lead: dict, limit: int = 28) -> list[str]:
    names = _profile_skill_names(profile)
    jd_terms = _job_keyword_terms(_lead_text(lead))
    exact = [skill for skill in names if any(skill.lower() == term.lower() for term in jd_terms)]
    fuzzy = [skill for skill in names if skill not in exact and any(skill.lower() in term.lower() or term.lower() in skill.lower() for term in jd_terms)]
    rest = [skill for skill in names if skill not in exact and skill not in fuzzy]
    return _compact_list([*exact, *fuzzy, *rest], limit)


def _role_headline(profile: dict, lead: dict, skills: list[str]) -> str:
    target = str(lead.get("title") or "Software Engineer").strip()
    summary = str(profile.get("s") or "").strip()
    if summary:
        first = _clean_sentence(summary).rstrip(".")
        return first[:260]
    skill_text = ", ".join(skills[:5]) if skills else "production software delivery"
    return f"{target} candidate with hands-on proof across {skill_text}"


def _impact_bullets(text: str, fallback: str, limit: int = 3) -> list[str]:
    chunks = re.split(r"(?:\n+|[.;]\s+|•|\u2022)", str(text or ""))
    bullets = [_clean_sentence(chunk) for chunk in chunks if len(chunk.strip()) > 16]
    return _dedupe_sentences(bullets or [_clean_sentence(fallback)], limit)


def _inferred_skill_category(name: str, current: str = "") -> str:
    raw = (current or "").strip().lower()
    if raw and raw not in {"technical", "portfolio", "project_stack", "general"}:
        return current
    lower = name.lower()
    if lower in {"python", "javascript", "typescript", "sql", "bash", "go", "rust", "java", "c++", "c#"}:
        return "language"
    if any(term in lower for term in ("react", "next", "fastapi", "django", "flask", "node", "tailwind", "vite", "langchain", "langgraph")):
        return "framework"
    if any(term in lower for term in ("postgres", "mysql", "mongo", "redis", "sqlite", "lancedb", "kuzu", "qdrant", "drizzle", "prisma")):
        return "database"
    if any(term in lower for term in ("docker", "kubernetes", "vercel", "aws", "gcp", "azure", "linux", "git", "ci/cd")):
        return "tool"
    if any(term in lower for term in ("rag", "llm", "agent", "openai", "groq", "deepgram", "livekit", "gemini")):
        return "ai"
    return current or "technical"


def _project_bullets(project: dict, lead: dict, jd_terms: list[str]) -> list[str]:
    title = project.get("title", "Project")
    stack = project.get("stack", [])
    stack_text = ", ".join(stack) if isinstance(stack, list) else str(stack or "")
    impact = project.get("impact", "")
    matched_terms = [term for term in jd_terms if term.lower() in f"{stack_text} {impact} {title}".lower()]
    focus = ", ".join(matched_terms[:4] or _compact_list(stack_text.split(","), 4))
    base = _impact_bullets(impact, f"Built {title} with {stack_text} to solve a role-relevant product problem", 2)
    bullets = [
        base[0],
        _clean_sentence(f"Applied {focus} in a production-style workflow aligned with the {lead.get('title', 'target role')} requirements") if focus else "",
    ]
    if len(base) > 1:
        bullets.append(base[1])
    bullets.append(_clean_sentence(f"Tech: {stack_text}"))
    return [bullet for bullet in bullets if bullet][:4]


def _experience_bullets(exp: dict, lead: dict, skills: list[str]) -> list[str]:
    desc = str(exp.get("d", "") or exp.get("description", ""))
    role = str(exp.get("role", "Role") or "Role")
    company = str(exp.get("co", "") or exp.get("company", ""))
    base = _impact_bullets(desc, f"Delivered {role} work for {company or 'the organization'} using {', '.join(skills[:4])}", 4)
    return base[:4]


def _line_items(values: list, limit: int = 4) -> str:
    items = []
    for value in values[:limit]:
        if isinstance(value, dict):
            text = value.get("title") or value.get("name") or value.get("n") or ""
        else:
            text = str(value or "")
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            items.append(f"- {text}")
    return "\n".join(items)


def _rank_projects(profile: dict, lead: dict, limit: int = 4) -> list[dict]:
    jd = " ".join([
        lead.get("title", ""),
        lead.get("company", ""),
        lead.get("description", ""),
        lead.get("reason", ""),
        " ".join(lead.get("match_points", []) or []),
    ])
    target = _keywords(jd)
    ranked = []
    for project in profile.get("projects", []):
        stack = project.get("stack", [])
        stack_text = ", ".join(stack) if isinstance(stack, list) else str(stack)
        text = " ".join([
            project.get("title", ""),
            stack_text,
            project.get("impact", ""),
        ])
        tokens = _keywords(text)
        stack_hits = len(target.intersection(_keywords(stack_text))) * 3
        score = len(target.intersection(tokens)) + stack_hits
        ranked.append((score, project))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [p for idx, (score, p) in enumerate(ranked[:limit]) if p.get("title") and (score > 0 or idx < 2)]


def _profile_payload(profile: dict) -> dict:
    return {
        "candidate": {"name": profile.get("n", ""), "summary": profile.get("s", "")},
        "identity": profile.get("identity", {}),
        "skills": profile.get("skills", []),
        "experience": profile.get("exp", []),
        "projects": profile.get("projects", []),
        "certifications": profile.get("certifications", []) or profile.get("certs", []),
        "education": profile.get("education", []),
        "achievements": profile.get("achievements", []),
    }


def _categorize_skills(skills: list[dict]) -> dict[str, list[str]]:
    """Group skills into categories matching the resume format."""
    categories: dict[str, list[str]] = {
        "Languages": [],
        "Frameworks & Libraries": [],
        "Databases & Data Tools": [],
        "Tools & Platforms": [],
        "Core Concepts": [],
        "AI Skills": [],
    }
    _cat_map = {
        "language": "Languages", "languages": "Languages", "lang": "Languages",
        "framework": "Frameworks & Libraries", "frameworks": "Frameworks & Libraries",
        "library": "Frameworks & Libraries", "libraries": "Frameworks & Libraries",
        "frontend": "Frameworks & Libraries", "backend": "Frameworks & Libraries",
        "database": "Databases & Data Tools", "databases": "Databases & Data Tools",
        "data": "Databases & Data Tools", "db": "Databases & Data Tools",
        "tool": "Tools & Platforms", "tools": "Tools & Platforms",
        "platform": "Tools & Platforms", "platforms": "Tools & Platforms",
        "devops": "Tools & Platforms", "cloud": "Tools & Platforms",
        "concept": "Core Concepts", "concepts": "Core Concepts",
        "soft": "Core Concepts",
        "ai": "AI Skills", "ml": "AI Skills", "machine learning": "AI Skills",
    }
    for s in skills:
        name = s.get("n", "")
        if not name:
            continue
        cat_raw = (s.get("cat", "") or s.get("category", "") or "").lower().strip()
        target_cat = _cat_map.get(cat_raw, "Tools & Platforms")
        categories[target_cat].append(name)
    return {k: v for k, v in categories.items() if v}


def _fallback_package(profile: dict, lead: dict, template: str = "") -> _DocPackage:
    selected = _rank_projects(profile, lead, limit=2)
    name = profile.get("n") or "Candidate"
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    title = lead.get("title", "Software Engineer")
    company = lead.get("company", "the company")
    skills_raw = profile.get("skills", [])
    education = profile.get("education", [])
    certs = profile.get("certifications", []) or profile.get("certs", [])
    achievements = profile.get("achievements", [])
    jd_terms = _job_keyword_terms(_lead_text(lead))
    prioritized_skills = _prioritized_skills(profile, lead)
    coverage = _keyword_coverage(profile, lead)

    skill_cats = _categorize_skills([
        {
            **skill,
            "n": skill.get("n") or skill.get("name", ""),
            "cat": _inferred_skill_category(skill.get("n") or skill.get("name", ""), skill.get("cat", skill.get("category", ""))),
        }
        for skill in skills_raw
        if skill.get("n") or skill.get("name")
    ])
    skills_lines = []
    for cat, items in skill_cats.items():
        ordered = _compact_list([s for s in prioritized_skills if s in items] + items, 8)
        if ordered:
            skills_lines.append(f"**{cat}:** {', '.join(ordered)}")
    skills_block = "\n".join(skills_lines) if skills_lines else f"**Core:** {', '.join(prioritized_skills[:12])}"

    project_lines = []
    for p in selected:
        stack = p.get("stack", [])
        stack_text = ", ".join(stack) if isinstance(stack, list) else str(stack)
        repo = str(p.get("repo") or "").strip()
        subtitle_bits = [bit for bit in [stack_text.split(",")[0].strip() if stack_text else "", repo] if bit]
        proj_block = f"### {p.get('title','Project')}"
        if subtitle_bits:
            proj_block += f" - {' | '.join(subtitle_bits[:2])}"
        proj_block += "\n"
        for bullet in _project_bullets(p, lead, jd_terms)[:3]:
            proj_block += f"- {bullet}\n"
        project_lines.append(proj_block)
    if not project_lines:
        project_lines.append("### Role-Matched Project Evidence\n- Add projects to the Identity Graph for stronger tailoring.")

    exp_lines = []
    for e in profile.get("exp", [])[:2]:
        role = e.get("role", "Role")
        co = e.get("co", "Company")
        period = e.get("period", "")
        exp_block = f"### {role} - {co} {period}\n".strip() + "\n"
        for bullet in _experience_bullets(e, lead, prioritized_skills)[:2]:
            exp_block += f"- {bullet}\n"
        exp_lines.append(exp_block)

    cert_lines = _line_items(certs, 4)
    achv_lines = _line_items(achievements, 4)
    edu_lines = _line_items(education, 3)
    summary = _role_headline(profile, lead, prioritized_skills)
    jd_line = ""
    if coverage.get("covered_terms"):
        jd_line = f" Role fit: {', '.join(coverage['covered_terms'][:8])}."

    contact_parts = []
    if identity.get("linkedin_url"):
        contact_parts.append(f"LinkedIn: {identity['linkedin_url']}")
    if identity.get("email"):
        contact_parts.append(f"Email: {identity['email']}")
    if identity.get("github_url"):
        contact_parts.append(f"GitHub: {identity['github_url']}")
    if identity.get("phone"):
        contact_parts.append(f"Phone: {identity['phone']}")

    resume = f"# {name}\n"
    if contact_parts:
        resume += " | ".join(contact_parts[:4]) + "\n"
    resume += "\n"
    resume += f"## SUMMARY\n{_clean_sentence(summary)} Targeting {title} at {company}.{jd_line}\n\n"
    resume += f"## SKILLS\n{skills_block}\n\n"
    if exp_lines:
        resume += f"\n## EXPERIENCE\n{chr(10).join(exp_lines)}\n"
    resume += f"## PROJECTS\n{chr(10).join(project_lines)}\n"
    if cert_lines:
        resume += f"\n## CERTIFICATES\n{cert_lines}\n"
    if achv_lines:
        resume += f"\n## ACHIEVEMENTS\n{achv_lines}\n"
    if edu_lines:
        resume += f"\n## EDUCATION\n{edu_lines}\n"

    all_skills = prioritized_skills
    cover = f"""Dear {company} team,

I am writing to apply for the {title} position at {company}. My background in {", ".join(all_skills[:5]) if all_skills else "software engineering"} aligns directly with the requirements outlined in your posting.

In my recent work, I have built and shipped {", ".join(p.get('title','Project') for p in selected[:3]) if selected else "production systems"} using technologies central to your stack. These projects demonstrate hands-on experience with the tools and patterns your team uses daily.

I would welcome the opportunity to discuss how my experience maps to your needs. Thank you for your consideration.

Sincerely,
{name}
"""
    outreach = _fallback_outreach(profile, lead)
    return _DocPackage(
        selected_projects=[p.get("title", "") for p in selected if p.get("title")],
        resume_markdown=resume,
        cover_letter_markdown=cover,
        founder_message=outreach["founder_message"],
        linkedin_note=outreach["linkedin_note"],
        cold_email=outreach["cold_email"],
    )


class ResumeGenerator:
    name = "resume"

    def generate(self, lead: dict, profile: dict, config: dict | None = None) -> GeneratedAsset:
        template = (config or {}).get("template", "")
        package = _fallback_package(profile, lead, template)
        return {"type": self.name, "text": package.resume_markdown}
