"""Profile parsing for ingestion.

Turns raw resume / portfolio text into a structured profile (C): markdown and
section helpers, the portfolio-markdown parser, the generic local parser, and
the resume heuristic parser with its line-classification helpers, plus the
candidate-data merge used to combine parses.
"""

import re

from core.logging import get_logger
from core.occupations import OCCUPATION_TERMS
from models.schema import C
from profile.ingest_documents import _strip_md

_log = get_logger(__name__)

# Recognize an experience-header role word in ANY field. Built from the shared
# occupation vocabulary plus generic seniority/role nouns that span fields.
_HEADER_ROLE_EXTRA = (
    "intern", "trainee", "apprentice", "volunteer", "freelancer", "freelance",
    "contractor", "founder", "co-founder", "cofounder", "owner", "partner",
    "lead", "head", "chief", "president", "vice president", "vp", "principal",
    "engineering", "fellow", "registrar", "resident", "associate",
)
_OCCUPATION_HEADER_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in (*OCCUPATION_TERMS, *_HEADER_ROLE_EXTRA)) + r")\b",
    re.I,
)


def _split_csv(value: str) -> list[str]:
    from profile.normalization import split_skill_names

    out: list[str] = []
    for part in str(value or "").split(","):
        out.extend(split_skill_names(part))
    return out or [_strip_md(part) for part in str(value or "").split(",") if _strip_md(part)]


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        clean = _strip_md(item)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def _section_items(text: str, names: tuple[str, ...]) -> list[str]:
    pattern = "|".join(re.escape(name) for name in names)
    match = re.search(rf"(?im)^\s*#{1,3}\s+(?:\d+\s*/\s*)?(?:{pattern})\b[^\n]*$", text or "")
    if not match:
        return []
    tail = text[match.end():]
    end = re.search(r"(?m)^\s*#{1,3}\s+", tail)
    if end:
        tail = tail[:end.start()]
    items = []
    for line in tail.splitlines():
        clean = _strip_md(re.sub(r"^\s*[-*]\s*", "", line))
        if clean and not clean.startswith("---"):
            items.append(clean)
    return _dedupe(items)


def _section(text: str, start: str, end: str | None = None) -> str:
    start_match = re.search(start, text, flags=re.I | re.M)
    if not start_match:
        return ""
    tail = text[start_match.end():]
    if end:
        end_match = re.search(end, tail, flags=re.I | re.M)
        if end_match:
            tail = tail[:end_match.start()]
    return tail.strip()


def _field(block: str, name: str) -> str:
    match = re.search(rf"(?im)^\s*[-*]?\s*\*\*{re.escape(name)}:\*\*\s*(.+)$", block or "")
    return _strip_md(match.group(1)) if match else ""


def _heading_blocks(section: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", section or ""))
    blocks = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        blocks.append((_strip_md(match.group(1)), section[match.end():end].strip()))
    return blocks


def _title_from_heading(heading: str) -> str:
    heading = re.sub(r"^\d+\.\s*", "", heading or "").strip()
    return _strip_md(re.sub(r"\s*\([^)]*\)\s*$", "", heading))


def _first_url(value: str) -> str:
    match = re.search(r"https?://[^\s|)]+", value or "")
    return match.group(0) if match else ""


def _project_from_block(heading: str, block: str):
    from models.schema import P

    title = _title_from_heading(heading)
    stack = _split_csv(_field(block, "Tech Stack") or _field(block, "Tech"))
    live = _first_url(_field(block, "Live"))
    video = _first_url(_field(block, "Video"))

    parts = []
    for key in ("Description", "Summary", "Highlights"):
        value = _field(block, key)
        if value:
            parts.append(f"{key}: {value}")

    modal = _section(block, r"(?m)^\s*[-*]?\s*\*\*Modal Details:\*\*", None)
    if not modal:
        modal = _section(block, r"(?m)^\s*\*\*Project Modal Details:\*\*", None)
    if modal:
        cleaned = "\n".join(_strip_md(line) for line in modal.splitlines() if _strip_md(line))
        if cleaned:
            parts.append(cleaned)

    if live:
        parts.append(f"Live: {live}")
    if video:
        parts.append(f"Video: {video}")

    return P(
        title=title,
        stack=stack,
        repo=live or video or "",
        impact="\n".join(parts).strip(),
        s=stack,
    )


def _parse_portfolio_markdown(txt: str):
    from models.schema import S, E, P

    if not re.search(r"(?i)portfolio content|selected work|technical expertise", txt or ""):
        return None

    hero = _section(txt, r"(?m)^##\s+Hero Section", r"(?m)^---\s*$")
    name = _field(hero, "Name") or "Candidate"
    tagline = _field(hero, "Tagline")

    exp_section = _section(txt, r"(?m)^##\s+01\s*/\s*Experience", r"(?m)^##\s+02\s*/")
    exp = []
    if exp_section:
        period_line = ""
        period_match = re.search(r"(?m)^\*\*(.+?)\*\*\s*$", exp_section)
        if period_match:
            period_line = _strip_md(period_match.group(1))
        role_match = re.search(r"(?m)^###\s+(.+?)\s*$", exp_section)
        role = _strip_md(role_match.group(1)) if role_match else "Full-Stack Engineer"
        company = "Freelance"
        if "|" in period_line:
            period, rest = [part.strip() for part in period_line.split("|", 1)]
            company = _strip_md(rest.split("-")[0])
        else:
            period = period_line
        exp_stack = _split_csv(_field(exp_section, "Tech Stack"))
        detail_lines = [
            _strip_md(line)
            for line in exp_section.splitlines()
            if _strip_md(line)
            and not line.strip().startswith("#")
            and not re.match(r"^\*\*.*\*\*$", line.strip())
        ]
        exp.append(E(role=role, co=company or "Freelance", period=period, d="\n".join(detail_lines), s=exp_stack))

    selected = _section(txt, r"(?m)^##\s+02\s*/\s+Selected Work", r"(?m)^##\s+03\s*/")
    more = _section(txt, r"(?m)^##\s+03\s*/\s+More from GitHub", r"(?m)^##\s+04\s*/")
    projects: list[P] = []
    for section_text in (selected, more):
        for heading, block in _heading_blocks(section_text):
            project = _project_from_block(heading, block)
            if project.title:
                projects.append(project)

    expertise = _section(txt, r"(?m)^##\s+04\s*/\s+Technical Expertise", r"(?m)^##\s+05\s*/")
    skill_names = []
    for line in expertise.splitlines():
        match = re.match(r"\s*[-*]\s*\*\*([^:]+):\*\*\s*(.+)$", line)
        if match:
            skill_names.extend(_split_csv(match.group(2)))
    for project in projects:
        skill_names.extend(project.stack)
    for item in exp:
        skill_names.extend(item.s)

    skills = [S(n=skill, cat="portfolio") for skill in _dedupe(skill_names)]
    services = _section(txt, r"(?m)^##\s+06\s*/\s+Services", r"(?m)^##\s+07\s*/")
    summary_parts = [tagline]
    if services:
        summary_parts.append("Services: " + " ".join(_strip_md(line) for line in services.splitlines() if _strip_md(line)))

    return C(
        n=name,
        s="\n".join(part for part in summary_parts if part),
        skills=skills,
        exp=exp,
        projects=projects,
        certifications=_section_items(txt, ("certifications", "credentials", "certificates")),
        education=_section_items(txt, ("education", "academic background")),
        achievements=_section_items(txt, ("achievements", "awards", "honors")),
    )


def _parse_local(txt: str) -> C:
    from models.schema import S, E, P

    portfolio = _parse_portfolio_markdown(txt)
    if portfolio is not None:
        return portfolio

    lines = txt.strip().splitlines()
    fields: dict[str, str] = {}
    projects_raw: list[str] = []
    exp_raw: list[str] = []

    section = "fields"
    buf: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == "--- Projects ---":
            section = "projects"
            continue
        if stripped == "--- Experience ---":
            if buf and section == "projects":
                projects_raw.append("\n".join(buf))
                buf = []
            section = "experience"
            continue

        if section == "fields":
            if ": " in stripped:
                k, v = stripped.split(": ", 1)
                fields[k.strip()] = v.strip()

        elif section == "projects":
            if stripped.startswith("Project: ") and buf:
                projects_raw.append("\n".join(buf))
                buf = []
            buf.append(stripped)

        elif section == "experience":
            if stripped.startswith("Experience: ") and buf:
                exp_raw.append("\n".join(buf))
                buf = []
            buf.append(stripped)

    if buf:
        if section == "projects":
            projects_raw.append("\n".join(buf))
        elif section == "experience":
            exp_raw.append("\n".join(buf))

    name = fields.get("name", "") or fields.get("targetRole", "") or "Candidate"
    summary = fields.get("summary", "")

    projects: list[P] = []
    for block in projects_raw:
        pf: dict[str, str] = {}
        for pline in block.splitlines():
            if ": " in pline:
                pk, pv = pline.split(": ", 1)
                pf[pk.strip()] = pv.strip()
        if pf.get("Project"):
            stack_str = pf.get("Stack", "")
            projects.append(P(
                title=pf["Project"],
                stack=[s.strip() for s in stack_str.split(",") if s.strip()],
                repo=pf.get("Repo", ""),
                impact=pf.get("Impact", ""),
                s=[s.strip() for s in stack_str.split(",") if s.strip()],
            ))

    exps: list[E] = []
    for block in exp_raw:
        ef: dict[str, str] = {}
        for eline in block.splitlines():
            if eline.startswith("Experience: "):
                parts = eline.replace("Experience: ", "").split(" at ", 1)
                ef["role"] = parts[0].strip()
                ef["co"] = parts[1].strip() if len(parts) > 1 else ""
            elif ": " in eline:
                ek, ev = eline.split(": ", 1)
                ef[ek.strip()] = ev.strip()
        if ef.get("role"):
            exps.append(E(
                role=ef["role"],
                co=ef.get("co", ""),
                period=ef.get("Period", ""),
                d=ef.get("Description", ""),
                s=[],
            ))

    skill_names: set[str] = set()
    for p in projects:
        skill_names.update(p.stack)
    skills = [S(n=sn, cat="general") for sn in skill_names if sn]

    certifications = _split_csv(fields.get("certifications", "") or fields.get("certs", ""))
    education = _split_csv(fields.get("education", ""))
    achievements = _split_csv(fields.get("achievements", "") or fields.get("awards", ""))

    parsed = C(
        n=name,
        s=summary,
        skills=skills,
        exp=exps,
        projects=projects,
        certifications=certifications,
        education=education,
        achievements=achievements,
    )
    from profile.normalization import normalize_candidate_model

    parsed = normalize_candidate_model(parsed)
    if _profile_has_content(parsed):
        return parsed
    return _parse_resume_heuristic(txt)


def _profile_has_content(profile: C) -> bool:
    return bool(
        str(profile.n or "").strip() not in {"", "Candidate", "Unknown"}
        or str(profile.s or "").strip()
        or profile.skills
        or profile.exp
        or profile.projects
        or profile.certifications
        or profile.education
        or profile.achievements
    )


def _section_lines(text: str, headings: tuple[str, ...]) -> list[str]:
    pattern = "|".join(re.escape(name) for name in headings)
    match = re.search(rf"(?im)^\s*(?:#+\s*)?(?:{pattern})\s*:?\s*$", text or "")
    if not match:
        return []
    tail = text[match.end():]
    end = re.search(
        r"(?im)^\s*(?:#+\s*)?(?:summary|profile|objective|skills|technical skills|experience|work experience|employment|projects|education|certifications|certificates|achievements|awards)\s*:?\s*$",
        tail,
    )
    if end:
        tail = tail[:end.start()]
    return [_strip_md(re.sub(r"^\s*(?:[-*]|\u2022|\u00e2\u20ac\u00a2)\s*", "", line)) for line in tail.splitlines() if _strip_md(line)]


def _parse_resume_heuristic(txt: str) -> C:
    from models.schema import S, E

    clean_text = re.sub(r"\r\n?", "\n", txt or "")
    lines = [_strip_md(line) for line in clean_text.splitlines()]
    lines = [line for line in lines if line]

    name = "Candidate"
    for line in lines[:8]:
        lower = line.lower()
        if "@" in line or "http" in lower or "linkedin" in lower or "github" in lower:
            continue
        words = re.findall(r"[A-Za-z][A-Za-z'.-]*", line)
        if 1 <= len(words) <= 5 and not any(token in lower for token in ("resume", "curriculum", "engineer |", "developer |")):
            name = " ".join(words)
            break

    summary_lines = _section_lines(clean_text, ("summary", "profile", "objective"))
    summary = " ".join(summary_lines[:3])
    if not summary:
        summary = ""

    skill_lines = _section_lines(clean_text, ("skills", "technical skills", "technologies", "tools"))
    skill_names: list[str] = []
    known_terms = {
        "Python", "TypeScript", "JavaScript", "React", "Next.js", "Node.js", "FastAPI", "Django", "Flask",
        "SQL", "PostgreSQL", "SQLite", "MongoDB", "Redis", "Docker", "Kubernetes", "AWS", "GCP", "Azure",
        "LangGraph", "LangChain", "OpenAI", "Gemini", "LLM", "RAG", "Machine Learning", "Pandas", "NumPy",
        "PyTorch", "TensorFlow", "Tauri", "Rust", "Git", "CI/CD", "Linux", "Playwright",
    }
    for line in skill_lines:
        value = re.sub(r"^[A-Za-z /&+-]{2,35}:\s*", "", line)
        skill_names.extend(_split_csv(re.sub(r"[|;]", ",", value)))
    lower_resume = clean_text.lower()
    for term in known_terms:
        if re.search(r"(?<![a-z0-9+#.-])" + re.escape(term.lower()) + r"(?![a-z0-9+#.-])", lower_resume):
            skill_names.append(term)
    skills = [S(n=item, cat="resume") for item in _dedupe(skill_names)[:40]]

    # Per-role skill matching uses the candidate's OWN listed skills (any field)
    # plus the tech known-terms, so a nurse's "IV therapy" is matched in their
    # role descriptions exactly like a developer's "Python" — precise because it
    # only matches skills the person actually listed.
    match_vocab = _dedupe([*known_terms, *[skill.n for skill in skills]])

    def _skills_in(text: str) -> list[str]:
        low = (text or "").lower()
        return [
            term for term in match_vocab
            if re.search(r"(?<![a-z0-9+#.-])" + re.escape(term.lower()) + r"(?![a-z0-9+#.-])", low)
        ]

    exp_lines = _section_lines(clean_text, ("experience", "work experience", "employment"))
    exp: list[E] = []
    current_exp: dict | None = None
    for line in exp_lines[:30]:
        if len(line) < 6:
            continue
        header = _resume_experience_header(line)
        if header:
            if current_exp:
                exp.append(E(role=current_exp["role"], co=current_exp["co"], period=current_exp.get("period", ""), d=current_exp.get("d", ""), s=_skills_in(current_exp.get("d", ""))))
            current_exp = header
            continue
        # Date patterns → period
        if current_exp and re.search(r"\b(?:19|20)\d{2}\b.*(?:present|current|19|20)\d{0,2}", line, flags=re.I):
            current_exp["period"] = line[:100]
            continue
        # Detail lines → description
        if current_exp:
            existing = current_exp.get("d", "")
            current_exp["d"] = f"{existing}\n{line}".strip()[:900]
        if len(exp) >= 10:
            break
    if current_exp:
        exp.append(E(role=current_exp["role"], co=current_exp["co"], period=current_exp.get("period", ""), d=current_exp.get("d", ""), s=_skills_in(current_exp.get("d", ""))))

    project_lines = _section_lines(clean_text, ("projects", "selected projects", "personal projects"))
    projects = _projects_from_resume_lines(project_lines, skills)
    education = _education_from_resume_lines(_section_lines(clean_text, ("education",)))

    parsed = C(
        n=name,
        s=summary,
        skills=skills,
        exp=exp,
        projects=projects,
        certifications=_section_lines(clean_text, ("certifications", "certificates"))[:8],
        education=education,
        achievements=_section_lines(clean_text, ("achievements", "awards"))[:8],
    )
    from profile.normalization import normalize_candidate_model

    return normalize_candidate_model(parsed)


def _resume_experience_header(line: str) -> dict | None:
    clean = _strip_md(line)
    if not clean or _resume_line_is_detail(clean) or clean.endswith("."):
        return None
    if len(clean.split()) > 16:
        return None
    # Field-agnostic header detection: accept a line that names a recognized
    # occupation in ANY field, OR has the structural shape of an experience
    # header (a "Title at Company" form, or "Title | Company | Dates" with a
    # date token). Structure-first keeps precision high for non-tech résumés
    # without grabbing arbitrary lines.
    has_occupation = bool(_OCCUPATION_HEADER_RE.search(clean))
    has_at = " at " in clean.lower()
    has_date = bool(re.search(r"\b(?:19|20)\d{2}\b|present|current", clean, re.I))
    has_separator = bool(re.search(r"\s\|\s|\s[–—-]\s", clean))
    if not (has_occupation or has_at or (has_date and has_separator)):
        return None

    period = ""
    role = clean
    company = ""
    if " at " in clean.lower():
        parts = re.split(r"\s+at\s+", clean, maxsplit=1, flags=re.I)
        role, company = parts[0], parts[1]
    else:
        parts = [part.strip(" -|") for part in re.split(r"\s+\|\s+|\s+-\s+", clean) if part.strip(" -|")]
        if len(parts) >= 2:
            date_parts = [part for part in parts if re.search(r"\b(?:19|20)\d{2}\b|present|current", part, re.I)]
            text_parts = [part for part in parts if part not in date_parts]
            if text_parts:
                role = text_parts[0]
            if len(text_parts) >= 2:
                company = text_parts[1]
            if date_parts:
                period = " - ".join(date_parts)

    # Reject "headers" that resolved to nothing but a date range (e.g. a bare
    # "Jan 2019 - Present" line passed the structural gate). Strip years, month
    # names, and present/current; a real role still has letters left over. This
    # lets pure date lines fall through to the period handler instead.
    role_clean = re.sub(
        r"\b(?:19|20)\d{2}\b|present|current|"
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?",
        "", role, flags=re.I,
    )
    if not re.search(r"[A-Za-z]{2,}", role_clean):
        return None

    return {"role": role[:180], "co": company[:180], "period": period[:100], "d": ""}


def _projects_from_resume_lines(lines: list[str], skills: list) -> list:
    from models.schema import P
    from profile.normalization import normalize_projects, normalize_stack

    raw_projects: list[dict] = []
    current: dict | None = None
    known_skill_names = [skill.n for skill in skills]

    def flush():
        nonlocal current
        if current:
            raw_projects.append(current)
            current = None

    def append_impact(detail: str) -> None:
        if current is None:
            return
        detail = _strip_md(detail)
        if not detail:
            return
        existing = str(current.get("impact") or "").strip()
        if existing and existing.endswith("-") and detail[:1].islower():
            current["impact"] = f"{existing[:-1]}{detail}".strip()
            return
        separator = " " if existing and detail[:1].islower() else "\n"
        current["impact"] = f"{existing}{separator}{detail}".strip()

    for raw_line in lines:
        line = _strip_md(raw_line)
        if raw_line.rstrip().endswith("-") and not line.endswith("-"):
            line = f"{line}-"
        if not line:
            continue
        header = _resume_project_header(line, known_skill_names)
        if header:
            flush()
            current = header
            continue
        if _first_url(line) and not re.search(r"(?i)\b(github|repo|link|live|demo)\s*:", line):
            flush()
            title, detail = _split_project_title_detail(line)
            current = {"title": title, "impact": detail, "repo": _first_url(line), "stack": ""}
            continue
        if current is None:
            if _resume_standalone_project_title(line, known_skill_names):
                title, detail = _split_project_title_detail(line)
                current = {"title": title, "impact": detail, "repo": _first_url(line), "stack": ""}
            continue
        lower = line.lower()
        repo = _first_url(line)
        stack = normalize_stack(line) if re.search(r"(?i)\b(tech stack|stack|built with)\b", line) else []
        if repo and not current.get("repo"):
            current["repo"] = repo
        if not stack and _resume_stack_only_line(line, known_skill_names):
            stack = normalize_stack(line)
        if stack:
            current["stack"] = ", ".join(normalize_stack(current.get("stack", "")) + stack)
        elif "stack" not in lower and "github" not in lower and "repo" not in lower:
            append_impact(line)
    flush()

    clean_projects = normalize_projects(raw_projects, known_skills=known_skill_names)
    return [
        P(
            title=item["title"],
            stack=normalize_stack(item.get("stack", "")),
            repo=item.get("repo") or "",
            impact=item.get("impact", ""),
            s=normalize_stack(item.get("stack", "")),
        )
        for item in clean_projects[:8]
    ]


def _resume_project_header(line: str, known_skills: list[str]) -> dict | None:
    clean = _strip_md(line)
    if not clean or re.search(r"(?i)^\s*(tech stack|stack|github|repo|link|live|demo)\s*:", clean):
        return None
    split_title, split_detail = _split_project_title_detail(clean)
    if split_detail and len(split_title.split()) <= 8 and _first_skill_position(split_title, known_skills) != 0 and not _resume_line_is_detail(split_title):
        return {"title": split_title, "impact": split_detail, "repo": _first_url(clean), "stack": ""}
    if _resume_line_is_detail(clean):
        return None
    repo = _first_url(clean) or _site_from_parentheses(clean)
    title = ""
    stack_text = ""
    paren = re.match(r"^(.{2,80}?)\s*\(([^)]{2,120})\)\s*(.*)$", clean)
    if paren:
        title = paren.group(1)
        stack_text = paren.group(3)
    else:
        skill_position = _first_skill_position(clean, known_skills)
        if skill_position is not None and 1 <= len(clean[:skill_position].split()) <= 4:
            title = clean[:skill_position]
            stack_text = clean[skill_position:]
    if not title:
        return None
    title = _strip_md(title).strip(" :-|.,")
    stack = _resume_stack_terms(stack_text, known_skills)
    if not stack and not repo:
        return None
    return {"title": title, "impact": "", "repo": repo, "stack": ", ".join(stack)}


def _resume_standalone_project_title(line: str, known_skills: list[str]) -> bool:
    clean = _strip_md(line)
    if not clean or _resume_line_is_detail(clean) or _resume_stack_only_line(clean, known_skills):
        return False
    title, _detail = _split_project_title_detail(clean)
    if _first_skill_position(title, known_skills) == 0:
        return False
    return len(title.split()) <= 7 and not re.search(r"(?i)\b(tech stack|stack|github|repo|link|live|demo)\s*:", clean)


def _resume_line_is_detail(line: str) -> bool:
    clean = _strip_md(line)
    return bool(
        re.match(
            r"(?i)^(built|created|developed|designed|engineered|implemented|integrated|launched|shipped|automated|features?|supports?|modeled|streamed|edit|and|or|with)\b",
            clean,
        )
        or clean[:1].islower()
        or clean.endswith(".")
    )


def _resume_stack_only_line(line: str, known_skills: list[str]) -> bool:
    clean = _strip_md(line)
    if not clean:
        return False
    if _resume_line_is_detail(clean):
        return False
    hits = _resume_stack_terms(clean, known_skills)
    if not hits:
        return False
    words = clean.split()
    if len(words) > 5 and not re.search(r"[,|;/]", clean):
        return False
    return len(hits) >= 2 or (len(words) <= 3 and clean.lower() in {skill.lower() for skill in known_skills})


def _resume_stack_terms(text: str, known_skills: list[str]) -> list[str]:
    from profile.normalization import normalize_stack

    stack = normalize_stack(text)
    known = {skill.lower() for skill in known_skills}
    return _dedupe([item for item in stack if item.lower() in known or len(item.split()) <= 3])


def _site_from_parentheses(line: str) -> str:
    match = re.search(r"\(([^)]*(?:\.[a-z]{2,}|github)[^)]*)\)", line, re.I)
    if not match:
        return ""
    value = match.group(1).strip()
    if value.lower() == "github":
        return ""
    return value if value.startswith(("http://", "https://")) else f"https://{value}"


def _first_skill_position(line: str, known_skills: list[str]) -> int | None:
    positions = []
    lower = line.lower()
    for skill in known_skills:
        if not skill:
            continue
        match = re.search(r"(?<![a-z0-9+#.-])" + re.escape(skill.lower()) + r"(?![a-z0-9+#.-])", lower)
        if match:
            positions.append(match.start())
    return min(positions) if positions else None


def _split_project_title_detail(line: str) -> tuple[str, str]:
    for separator in (" - ", " \u2013 ", " \u2014 ", " | ", ": "):
        if separator in line:
            title, detail = line.split(separator, 1)
            if len(title.split()) <= 8:
                return title.strip(), detail.strip()
    return line.strip(), ""


def _education_from_resume_lines(lines: list[str]) -> list[str]:
    from profile.normalization import normalize_education_entries

    return normalize_education_entries(lines)


def _merge_candidate_data(primary: C, fallback: C) -> C:
    from models.schema import C

    def merge_by(items, key_fn):
        seen: set[str] = set()
        out = []
        for item in items:
            key = re.sub(r"[^a-z0-9]+", "", key_fn(item).lower())
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return C(
        n=primary.n if primary.n and primary.n.lower() not in {"candidate", "unknown"} else fallback.n,
        s=primary.s or fallback.s,
        skills=merge_by([*primary.skills, *fallback.skills], lambda item: item.n),
        exp=merge_by([*primary.exp, *fallback.exp], lambda item: f"{item.role} {item.co}"),
        projects=merge_by([*primary.projects, *fallback.projects], lambda item: item.title),
        certifications=merge_by([*primary.certifications, *fallback.certifications], str),
        education=merge_by([*primary.education, *fallback.education], str),
        achievements=merge_by([*primary.achievements, *fallback.achievements], str),
    )
