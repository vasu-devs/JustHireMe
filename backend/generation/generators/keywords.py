from __future__ import annotations

import re

from generation.generators.base import GeneratedAsset

# JD keywords beyond TECH_TAXONOMY that a backend/systems role commonly screens on.
# Scanned on BOTH the JD side (_job_keyword_terms) AND the profile side
# (_profile_keyword_terms) — otherwise a candidate who genuinely has these skills
# is structurally uncoverable (always reported as a gap and told to the LLM as a
# "gap, not a claim to make", suppressing the very skills the JD screens on).
_EXTRA_JD_TERMS: dict[str, tuple[str, ...]] = {
    "Kafka": ("kafka",),
    "Distributed Systems": ("distributed systems", "distributed system"),
    "Event-Driven Architecture": ("event-driven", "event driven"),
    "Microservices": ("microservices", "microservice"),
    "System Design": ("system design",),
}


def _matches_alias(text: str, alias: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9+#]){re.escape(alias)}(?![a-z0-9+#])", text))


def _extract_jd_keywords(jd: str, profile: dict) -> str:
    """Extract the top ATS keywords from a job description, prioritising terms the candidate can claim."""
    from core.taxonomy import TECH_TAXONOMY
    jd_lower = jd.lower()
    found: list[str] = []
    for canonical, aliases in TECH_TAXONOMY.items():
        for alias in (canonical.lower(), *aliases):
            # Word-boundary match (like _job_keyword_terms) — a raw substring test
            # matched e.g. 'go' inside 'category', injecting false ATS keywords into
            # the tailoring prompt.
            if re.search(rf"(?<![a-z0-9+#]){re.escape(alias.lower())}(?![a-z0-9+#])", jd_lower):
                found.append(canonical)
                break
    # Also pull soft / domain terms the JD explicitly names
    for term in re.findall(r'\b(?:CI/CD|REST(?:ful)?|GraphQL|microservices?|cloud|AWS|GCP|Azure|Docker|Kubernetes|Agile|Scrum|TDD|OOP)\b', jd, re.I):
        norm = term.strip()
        if norm and norm not in found:
            found.append(norm)
    return ", ".join(dict.fromkeys(found))  # dedupe, preserve order


def _compact_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def _profile_keyword_terms(profile: dict) -> set[str]:
    """Return canonical taxonomy terms evidenced somewhere in the profile graph."""
    from core.taxonomy import TECH_TAXONOMY

    chunks: list[str] = [
        str(profile.get("n", "")),
        str(profile.get("s", "")),
    ]
    for skill in profile.get("skills", []):
        chunks.append(str(skill.get("n", "")))
        chunks.append(str(skill.get("cat", "") or skill.get("category", "")))
    for project in profile.get("projects", []):
        chunks.extend([
            str(project.get("title", "")),
            str(project.get("impact", "")),
            _compact_value(project.get("stack", "")),
        ])
    for exp in profile.get("exp", []):
        chunks.extend([
            str(exp.get("role", "")),
            str(exp.get("co", "")),
            str(exp.get("d", "")),
        ])
    for key in ("certifications", "certs", "education", "achievements"):
        chunks.extend(str(item) for item in profile.get(key, []) or [])

    profile_text = "\n".join(chunks).lower()
    terms = {
        canonical
        for canonical, aliases in TECH_TAXONOMY.items()
        if any(_matches_alias(profile_text, alias.lower()) for alias in aliases)
    }
    # Scan the SAME extra vocabulary the JD side adds, so these terms are coverable.
    for canonical, aliases in _EXTRA_JD_TERMS.items():
        if any(_matches_alias(profile_text, alias) for alias in aliases):
            terms.add(canonical)
    return terms


def _job_keyword_terms(jd: str) -> list[str]:
    """Return JD keyword requirements in stable display order."""
    from core.taxonomy import TECH_TAXONOMY

    jd_lower = (jd or "").lower()
    found: list[str] = []
    for canonical, aliases in TECH_TAXONOMY.items():
        if any(_matches_alias(jd_lower, alias.lower()) for alias in aliases):
            found.append(canonical)

    for canonical, aliases in _EXTRA_JD_TERMS.items():
        if any(_matches_alias(jd_lower, alias) for alias in aliases):
            found.append(canonical)

    return list(dict.fromkeys(found))


def _keyword_coverage(profile: dict, lead: dict, resume_markdown: str = "") -> dict:
    jd = "\n".join([
        str(lead.get("title", "")),
        str(lead.get("company", "")),
        str(lead.get("description", "")),
        str(lead.get("reason", "")),
        "\n".join(str(x) for x in lead.get("match_points", []) or []),
        "\n".join(str(x) for x in lead.get("gaps", []) or []),
    ])
    jd_terms = _job_keyword_terms(jd)
    profile_terms = _profile_keyword_terms(profile)
    covered = [term for term in jd_terms if term in profile_terms]
    missing = [term for term in jd_terms if term not in profile_terms]
    resume_lower = (resume_markdown or "").lower()
    incorporated = [
        term for term in covered
        if re.search(rf"(?<![a-z0-9+#]){re.escape(term.lower())}(?![a-z0-9+#])", resume_lower)
    ]
    return {
        "jd_terms": jd_terms[:24],
        "covered_terms": covered[:18],
        "missing_terms": missing[:12],
        "incorporated_terms": incorporated[:18],
        # None (not a fake 100) when the JD extractor found no known keywords
        # (e.g. a non-tech role vs the software-only taxonomy) so no consumer
        # surfaces a fabricated "100% coverage".
        "coverage_pct": round((len(covered) / len(jd_terms)) * 100) if jd_terms else None,
    }


class KeywordsGenerator:
    name = "keywords"

    def generate(self, lead: dict, profile: dict, config: dict | None = None) -> GeneratedAsset:
        resume_markdown = (config or {}).get("resume_markdown", "")
        return {"type": self.name, "metadata": _keyword_coverage(profile, lead, resume_markdown)}
