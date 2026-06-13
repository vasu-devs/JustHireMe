"""
Deterministic scoring engine for lead-candidate fit.

The evaluators used to delegate judgment to an LLM prompt. That made scores noisy:
the same lead could land in different bands depending on model/provider mood. This
module keeps the model out of the rating loop and scores each lead through a fixed
rubric with visible criteria, caps, and evidence.
"""

from __future__ import annotations
import logging

import re
from datetime import datetime, timezone
from dataclasses import dataclass
from collections.abc import Iterable

from core.types import CandidateEvidence, CriterionScore, ScoreResult
from core.logging import get_logger
from ranking.taxonomy import (
    COMMERCIAL_TERMS,
    DELIVERABLE_KEYWORDS,
    RED_FLAGS,
    ROLE_KEYWORDS,
    TECH_CATEGORY,
    TECH_TAXONOMY,
    WRONG_FIELD_TERMS,
    _MONTHS,
)

_log = get_logger(__name__)


@dataclass
class PostingSignals:
    title: str
    company: str
    text: str
    terms: set[str]
    primary_terms: set[str]
    role_tags: set[str]
    deliverables: set[str]
    wrong_field: bool
    wrong_field_terms: list[str]
    max_years: int
    seniority_flags: set[str]
    entry_level: bool
    remote: bool
    onsite: bool
    location_limited: bool
    budget_amount: int | None
    budget_present: bool
    commercial_intent: bool
    red_flags: list[str]
    quality_features: list[str]
















def clamp(n: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, round(n)))


def build_proof_text(candidate_data: dict) -> str:
    parts: list[str] = []
    for proj in candidate_data.get("projects", []) or []:
        stack = proj.get("stack", [])
        if isinstance(stack, list):
            stack = ", ".join(str(x) for x in stack if str(x).strip())
        title = proj.get("title", "")
        impact = proj.get("impact", "")
        if title:
            parts.append(f"Project: {title} | Stack: {stack} | Impact: {impact}")
    for exp in candidate_data.get("exp", []) or []:
        role = exp.get("role", "")
        co = exp.get("co", "")
        period = exp.get("period", "")
        desc = exp.get("d", "")
        stack = exp.get("s", [])
        stack_text = ", ".join(stack) if isinstance(stack, list) else str(stack or "")
        if role:
            parts.append(f"Role: {role} at {co} ({period}) | Stack: {stack_text} | {desc}")
    skills = [str(s.get("n", "")).strip() for s in candidate_data.get("skills", []) or [] if s.get("n")]
    if skills:
        parts.append(f"Skills: {', '.join(skills)}")
    return "\n".join(parts) if parts else "No profile data found."




def _period_months(period: str) -> int:
    """Estimate the number of months an experience period covers."""
    if not period:
        return 0
    text = str(period).lower()
    # An ongoing role ends today, not at some far-future sentinel; a sentinel
    # like 2099 would credit a brand-new hire with decades of experience.
    now = datetime.now(timezone.utc).strftime("%b %Y").lower()
    text = re.sub(r"\bpresent\b|\bcurrent\b|\bnow\b|\btoday\b", now, text)
    pairs = re.findall(
        r"([a-z]{3,4})?\s*(\d{4})\s*(?:to|-|–|—|->|→)\s*([a-z]{3,4})?\s*(\d{4})",
        text,
    )
    months = 0
    for sm, sy, em, ey in pairs:
        try:
            sy_i, ey_i = int(sy), int(ey)
        except ValueError:
            continue
        s_m = _MONTHS.get((sm or "jan")[:4], 1)
        e_m = _MONTHS.get((em or "dec")[:4], 12)
        delta = (ey_i - sy_i) * 12 + (e_m - s_m) + 1
        if delta > 0:
            months += min(delta, 600)
    if not pairs:
        years = re.search(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)", text)
        if years:
            months = int(years.group(1)) * 12
    return months


def _total_work_months(candidate_data: dict) -> int:
    """Return total months of non-intern professional experience."""
    exp_entries = candidate_data.get("exp", []) or []
    real_roles = []
    for entry in exp_entries:
        role = str(entry.get("role", "")).lower()
        if not role:
            continue
        if any(kw in role for kw in ("intern", "trainee", "student", "assistant only")):
            continue
        real_roles.append(entry)
    return sum(_period_months(e.get("period", "")) for e in real_roles)


def infer_experience_level(candidate_data: dict) -> str:
    """Estimate seniority from experience periods, role titles, and projects.

    Looks at total months of non-intern experience plus shipped project count so
    that someone with 3 strong projects but only 2 months of paid work doesn't
    get treated identically to a true zero-experience fresher.
    """
    exp_entries = candidate_data.get("exp", []) or []
    real_roles = []
    for entry in exp_entries:
        role = str(entry.get("role", "")).lower()
        if not role:
            continue
        if any(kw in role for kw in ("intern", "trainee", "student", "assistant only")):
            continue
        real_roles.append(entry)

    total_months = sum(_period_months(e.get("period", "")) for e in real_roles)
    senior_titles = sum(
        1 for e in real_roles
        if any(kw in str(e.get("role", "")).lower() for kw in ("senior", "lead", "principal", "staff", "head of", "manager"))
    )
    project_count = len(candidate_data.get("projects", []) or [])

    if senior_titles >= 1 and total_months >= 36:
        return "senior"
    if total_months >= 60:
        return "senior"
    if total_months >= 24 or len(real_roles) >= 2:
        return "mid"
    if real_roles or project_count >= 2:
        return "junior"
    return "fresher"


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _alias_regex(alias: str) -> re.Pattern[str]:
    alias = alias.lower().strip()
    escaped = re.escape(alias)
    escaped = escaped.replace(r"\ ", r"[\s\-_/.]+")
    escaped = escaped.replace(r"\.", r"[.\s\-_]?")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.I)


_ALIAS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (canonical, _alias_regex(alias))
    for canonical, aliases in TECH_TAXONOMY.items()
    for alias in aliases
]


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(_alias_regex(phrase).search(text.lower()))


def _find_terms(text: str) -> set[str]:
    lower = str(text or "").lower()
    found: set[str] = set()
    for canonical, pattern in _ALIAS_PATTERNS:
        if pattern.search(lower):
            found.add(canonical)
    return found


def _find_tags(text: str, taxonomy: dict[str, tuple[str, ...]]) -> set[str]:
    lower = str(text or "").lower()
    return {
        label
        for label, aliases in taxonomy.items()
        if any(_contains_phrase(lower, alias) for alias in aliases)
    }


def _split_stack(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,;/|]", str(value)) if part.strip()]


def _candidate_location(summary: str) -> str:
    lower = summary.lower()
    for loc in ("india", "united states", "usa", "us", "canada", "uk", "europe"):
        if re.search(rf"\b{re.escape(loc)}\b", lower):
            return "US" if loc in {"usa", "us", "united states"} else loc.title()
    return ""


def _profile_text(candidate_data: dict) -> str:
    return "\n".join(
        [
            str(candidate_data.get("s", "")),
            build_proof_text(candidate_data),
        ]
    )


def analyze_candidate(candidate_data: dict) -> CandidateEvidence:
    skill_terms: set[str] = set()
    project_terms: set[str] = set()
    experience_terms: set[str] = set()
    project_by_term: dict[str, list[str]] = {}
    experience_by_term: dict[str, list[str]] = {}
    project_texts: list[tuple[str, str, set[str]]] = []
    experience_texts: list[tuple[str, str, set[str]]] = []

    for skill in candidate_data.get("skills", []) or []:
        skill_terms |= _find_terms(skill.get("n", ""))

    for project in candidate_data.get("projects", []) or []:
        title = _squash(project.get("title", ""))
        stack = ", ".join(_split_stack(project.get("stack", [])))
        text = _squash(f"{title} {stack} {project.get('impact', '')}")
        terms = _find_terms(text)
        project_terms |= terms
        project_texts.append((title or "Unnamed project", text, terms))
        for term in terms:
            project_by_term.setdefault(term, [])
            if title and title not in project_by_term[term]:
                project_by_term[term].append(title)

    for exp in candidate_data.get("exp", []) or []:
        title = _squash(f"{exp.get('role', '')} at {exp.get('co', '')}".strip())
        stack = ", ".join(_split_stack(exp.get("s", [])))
        text = _squash(f"{title} {exp.get('period', '')} {stack} {exp.get('d', '')}")
        terms = _find_terms(text)
        experience_terms |= terms
        experience_texts.append((title or "Experience", text, terms))
        for term in terms:
            experience_by_term.setdefault(term, [])
            if title and title not in experience_by_term[term]:
                experience_by_term[term].append(title)

    summary = _profile_text(candidate_data)
    all_terms = skill_terms | project_terms | experience_terms | _find_terms(summary)
    role_tags = _find_tags(summary, ROLE_KEYWORDS)
    role_tags |= {TECH_CATEGORY[t] for t in all_terms if t in TECH_CATEGORY and TECH_CATEGORY[t] in ROLE_KEYWORDS}
    deliverables = _find_tags(summary, DELIVERABLE_KEYWORDS)

    return CandidateEvidence(
        skills=skill_terms,
        project_terms=project_terms,
        experience_terms=experience_terms,
        all_terms=all_terms,
        project_by_term=project_by_term,
        experience_by_term=experience_by_term,
        project_texts=project_texts,
        experience_texts=experience_texts,
        role_tags=role_tags,
        deliverables=deliverables,
        level=infer_experience_level(candidate_data),
        work_months=_total_work_months(candidate_data),
        summary=summary,
        location=_candidate_location(summary),
    )


def _field(text: str, name: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(name)}\s*:\s*(.+)$", text or "")
    return _squash(match.group(1)) if match else ""


def _title_from_text(text: str, fallback: str) -> str:
    title = _field(text, "Job Title") or _field(text, "Gig Title") or _field(text, "Title")
    if title:
        return title[:180]
    for line in str(text or "").splitlines():
        line = _squash(line)
        if not line or len(line) > 180:
            continue
        lower = line.lower()
        if lower.startswith(("url:", "description:", "budget:", "company:", "client:")):
            continue
        if lower.startswith(("http://", "https://", "www.")):
            continue
        return line
    return fallback


def _company_from_text(text: str) -> str:
    return _field(text, "Company") or _field(text, "Client")


def _extract_years(text: str) -> int:
    years: list[int] = []
    for pattern in (
        r"(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)",
        r"(\d{1,2})\s*-\s*(\d{1,2})\s*(?:years|yrs|yoe)",
    ):
        for match in re.finditer(pattern, text or "", flags=re.I):
            nums = [int(g) for g in match.groups() if g and g.isdigit()]
            if nums:
                years.append(max(nums))
    return max(years) if years else 0


def _budget_amount(text: str) -> int | None:
    amounts: list[int] = []
    for raw in re.findall(r"\$\s?(\d[\d,]*)", text or ""):
        try:
            amounts.append(int(raw.replace(",", "")))
        except ValueError:
            pass
    return max(amounts) if amounts else None


def _quality_features(text: str, terms: set[str], title: str, company: str) -> list[str]:
    clean = _squash(text)
    out: list[str] = []
    if title:
        out.append("clear title")
    if company:
        out.append("company/client named")
    if len(clean) >= 240:
        out.append("substantive description")
    if len(terms) >= 2:
        out.append("specific stack")
    if re.search(r"\b(remote|hybrid|onsite|salary|budget|apply|email|dm|proposal)\b", clean, re.I):
        out.append("next-step/context present")
    return out


def analyze_posting(raw_text: str, default_title: str = "Lead") -> PostingSignals:
    text = str(raw_text or "")
    lower = text.lower()
    title = _title_from_text(text, default_title)
    company = _company_from_text(text)
    terms = _find_terms(text)
    title_terms = _find_terms(title)
    first_chunk_terms = _find_terms(text[:700])
    primary = title_terms | first_chunk_terms
    if not primary:
        primary = set(terms)
    role_tags = _find_tags(f"{title}\n{text}", ROLE_KEYWORDS)
    deliverables = _find_tags(f"{title}\n{text}", DELIVERABLE_KEYWORDS)
    wrong_terms = [term for term in WRONG_FIELD_TERMS if _contains_phrase(lower, term)]
    tech_role = bool(terms or role_tags & {"ai", "backend", "frontend", "fullstack", "data", "devops", "desktop", "testing"})
    wrong_field = bool(wrong_terms and not tech_role)
    max_years = _extract_years(text)
    seniority_flags = {
        flag
        for flag, aliases in {
            "senior": ("senior", "sr.", "sr ", "lead", "staff", "principal"),
            "manager": ("manager", "director", "head of"),
        }.items()
        if any(_contains_phrase(lower, alias) for alias in aliases)
    }
    entry_level = any(_contains_phrase(lower, alias) for alias in ("junior", "entry level", "entry-level", "fresher", "graduate", "intern", "0-2 years", "0 to 2 years"))
    remote = any(_contains_phrase(lower, alias) for alias in ("remote", "work from home", "wfh", "anywhere"))
    onsite = any(_contains_phrase(lower, alias) for alias in ("onsite", "on-site", "in office", "relocation"))
    location_limited = any(_contains_phrase(lower, alias) for alias in ("us only", "u.s. only", "usa only", "must be in us", "us-based", "europe only", "uk only"))
    budget = _budget_amount(text)
    commercial_intent = any(_contains_phrase(lower, term) for term in COMMERCIAL_TERMS)
    red_flags = [flag for flag in RED_FLAGS if _contains_phrase(lower, flag)]

    return PostingSignals(
        title=title,
        company=company,
        text=text,
        terms=terms,
        primary_terms=primary,
        role_tags=role_tags,
        deliverables=deliverables,
        wrong_field=wrong_field,
        wrong_field_terms=wrong_terms,
        max_years=max_years,
        seniority_flags=seniority_flags,
        entry_level=entry_level,
        remote=remote,
        onsite=onsite,
        location_limited=location_limited,
        budget_amount=budget,
        budget_present=budget is not None or bool(re.search(r"\b(budget|salary|rate)\b", lower)),
        commercial_intent=commercial_intent,
        red_flags=red_flags,
        quality_features=_quality_features(text, terms, title, company),
    )


def _category_set(terms: Iterable[str]) -> set[str]:
    return {TECH_CATEGORY[t] for t in terms if t in TECH_CATEGORY}


def _sorted_terms(terms: Iterable[str]) -> list[str]:
    return sorted(set(terms), key=lambda x: x.lower())


def _fmt_terms(terms: Iterable[str], empty: str = "none") -> str:
    values = _sorted_terms(terms)
    return ", ".join(values[:8]) if values else empty


# Categories that are tightly coupled to specific tech where transferability is
# weak. A Python dev is not, for hiring purposes, "adjacent" to a Java role even
# though both are in the language category. Same for frontend/mobile/desktop.
_ADJACENCY_BLOCKLIST = {"language", "frontend", "mobile", "desktop", "cms", "enterprise"}


_PHRASE_STOPWORDS = {
    "and", "or", "the", "with", "for", "of", "in", "to", "a", "an", "skills",
    "experience", "proficient", "proficiency", "knowledge", "strong", "excellent",
    "ability", "etc", "various", "other", "general", "basic", "advanced",
}


def _normalize_phrase(value: str) -> str:
    text = re.sub(r"[^a-z0-9+#./ -]", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def candidate_domain_phrases(candidate_data: dict) -> set[str]:
    """Field-agnostic skill phrases drawn from the candidate's OWN profile.

    The deterministic rubric otherwise matches everything against a fixed tech
    taxonomy, so a nurse/welder/teacher scores blanks. Here we collect the
    candidate's literal skill names (and credential titles) as matchable
    phrases. Phrases that already resolve to a canonical tech term are dropped —
    the taxonomy handles those — so a software candidate's effective vocabulary
    (and score) is unchanged, while non-tech domains gain real signal.
    """
    phrases: set[str] = set()

    def _consider(raw: str) -> None:
        phrase = _normalize_phrase(raw)
        if not (3 <= len(phrase) <= 48):
            return
        if phrase in _PHRASE_STOPWORDS:
            return
        if _find_terms(raw):
            return  # already a canonical tech term; taxonomy covers it
        phrases.add(phrase)

    def _name(item, *keys: str) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for key in keys:
                if item.get(key):
                    return str(item[key])
        return ""

    for skill in candidate_data.get("skills", []) or []:
        _consider(_name(skill, "n", "name"))
    for cert in candidate_data.get("certifications", []) or []:
        _consider(_name(cert, "title", "name", "n"))
    return phrases


def apply_domain_generalization(posting: PostingSignals, candidate: CandidateEvidence, candidate_data: dict, jd: str) -> set[str]:
    """Match the candidate's own domain vocabulary against the posting and fold
    the hits into the keyword rubric, then make the wrong-field judgement
    relative to the candidate instead of relative to "is this software?".

    Returns the set of matched domain phrases (for callers that want it).
    """
    phrases = candidate_domain_phrases(candidate_data)
    matched = {phrase for phrase in phrases if _contains_phrase(jd, phrase)}
    if matched:
        # Both sides genuinely share these terms, so direct-overlap logic credits
        # them just like a shared tech stack would.
        posting.terms = posting.terms | matched
        candidate.all_terms = candidate.all_terms | matched

    if posting.wrong_field:
        # "Wrong field" must mean wrong *for this candidate*, not "not tech".
        # If the candidate works in the posting's profession (their skills show
        # up in the JD, or their profile names the same profession), it's the
        # RIGHT field and the hard cap must not fire.
        cand_text = _profile_text(candidate_data).lower()
        same_profession = any(_contains_phrase(cand_text, term) for term in posting.wrong_field_terms)
        if matched or same_profession:
            posting.wrong_field = False
    return matched


def _direct_and_adjacent(posting: PostingSignals, candidate: CandidateEvidence) -> tuple[set[str], set[str], set[str]]:
    required = posting.terms
    direct = required & candidate.all_terms
    candidate_categories = _category_set(candidate.all_terms)
    adjacent: set[str] = set()
    for term in required - direct:
        category = TECH_CATEGORY.get(term)
        if not category or category in _ADJACENCY_BLOCKLIST:
            continue
        if category in candidate_categories:
            adjacent.add(term)
    missing = required - direct - adjacent
    return direct, adjacent, missing












def _weighted_total(criteria: list[CriterionScore]) -> int:
    total_weight = sum(c.weight for c in criteria) or 1
    return clamp(sum(c.score * c.weight for c in criteria) / total_weight)


def _seniority_cap(posting: PostingSignals, candidate: CandidateEvidence) -> tuple[int, str] | None:
    effective_required = posting.max_years
    if "senior" in posting.seniority_flags:
        effective_required = max(effective_required, 5)
    if "manager" in posting.seniority_flags:
        effective_required = max(effective_required, 6)
    # Zero or near-zero professional experience vs any seniority requirement
    # is always a hard mismatch, regardless of project count.
    if candidate.work_months < 6 and effective_required >= 3:
        return 30, (
            f"seniority cap: {candidate.work_months} months professional experience "
            f"vs {effective_required}+ year requirement"
        )
    if candidate.level == "fresher" and effective_required >= 3:
        return 30, f"seniority cap: fresher profile vs {effective_required}+ year requirement"
    if candidate.level == "junior" and effective_required >= 5:
        return 38, f"seniority cap: junior profile vs {effective_required}+ year requirement"
    if candidate.level == "junior" and effective_required >= 3:
        return 45, f"seniority cap: junior profile vs {effective_required}+ year requirement"
    if candidate.level == "mid" and effective_required >= 7:
        return 48, f"seniority cap: mid profile vs {effective_required}+ year requirement"
    return None


def _apply_caps(
    score: int,
    posting: PostingSignals,
    candidate: CandidateEvidence,
    direct: set[str],
    adjacent: set[str],
) -> tuple[int, list[str], int | None]:
    caps: list[tuple[int, str]] = []
    if posting.wrong_field:
        caps.append((15, "wrong-field cap: posting is not a technical/software opportunity"))
    seniority = _seniority_cap(posting, candidate)
    if seniority:
        caps.append(seniority)
    if posting.terms and not direct and len(posting.terms) >= 2:
        cap = 52 if adjacent else 42
        caps.append((cap, "stack cap: no exact evidence for requested primary stack"))
    if not posting.terms and len(_squash(posting.text)) < 160:
        caps.append((68, "confidence cap: posting is too thin for a high rating"))
    if not caps:
        return score, [], None
    cap, _reason = min(caps, key=lambda item: item[0])
    limit_notes = [reason for _limit, reason in sorted(caps, key=lambda item: item[0])]
    return min(score, cap), limit_notes, cap


def _evidence_line(candidate: CandidateEvidence, terms: set[str]) -> str:
    chunks: list[str] = []
    for term in _sorted_terms(terms):
        projects = candidate.project_by_term.get(term, [])[:2]
        exps = candidate.experience_by_term.get(term, [])[:1]
        if projects:
            chunks.append(f"{term} in {', '.join(projects)}")
        elif exps:
            chunks.append(f"{term} in {', '.join(exps)}")
    return "; ".join(chunks[:4])


def _result(
    final_score: int,
    criteria: list[CriterionScore],
    posting: PostingSignals,
    candidate: CandidateEvidence,
    direct: set[str],
    adjacent: set[str],
    missing: set[str],
    caps: list[str],
    applied_cap: int | None = None,
) -> ScoreResult:
    ordered = sorted(criteria, key=lambda c: c.weight, reverse=True)
    breakdown = ", ".join(f"{c.name.split()[0]} {c.score}" for c in ordered)
    reason_bits = [f"Custom deterministic score from weighted criteria: {breakdown}."]
    if direct:
        reason_bits.append("Strongest evidence: " + (_evidence_line(candidate, direct) or _fmt_terms(direct)) + ".")
    if missing:
        reason_bits.append("Main gaps: " + _fmt_terms(missing) + ".")
    if caps:
        reason_bits.append("Limit noted: " + caps[0] + ".")
    reason = " ".join(reason_bits)[:500]

    match_points = [
        f"{c.name} {c.score}/100 (weight {c.weight}%): {c.reason}"
        for c in criteria
        if c.score >= 58
    ]
    if adjacent:
        match_points.append("Adjacent transferable stack: " + _fmt_terms(adjacent))
    gaps = [
        f"{c.name} {c.score}/100: {c.reason}"
        for c in criteria
        if c.score < 58
    ]
    if missing:
        gaps.insert(0, "Missing or weak evidence for: " + _fmt_terms(missing))
    gaps.extend(caps)
    return ScoreResult(
        score=final_score,
        reason=reason,
        match_points=match_points[:7],
        gaps=list(dict.fromkeys(gaps))[:8],
        criteria=criteria,
        applied_cap=applied_cap,
    )


def _with_weight(c: CriterionScore, weight: int) -> CriterionScore:
    """Return a copy of ``c`` with a different weight (CriterionScore is frozen)."""
    return CriterionScore(c.name, c.score, weight, c.reason)


def _semantic_criterion(jd: str, candidate_data: dict, weight: int) -> CriterionScore | None:
    """Build a Semantic-fit CriterionScore from embedding similarity.

    Returns ``None`` when embeddings or the vector store are unavailable so the
    caller can fall back to pure keyword scoring without changing weights.
    """
    try:
        from ranking.semantic import semantic_fit
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/scoring_engine.py:_semantic_criterion: %s', log_exc)
        return None
    try:
        result = semantic_fit(jd, candidate_data=candidate_data)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/scoring_engine.py:_semantic_criterion: %s', log_exc)
        return None
    if not result:
        return None
    score = int(result.get("score", 0))
    skill_matches = result.get("skill_matches") or []
    project_matches = result.get("project_matches") or []
    experience_matches = result.get("experience_matches") or []
    credential_matches = result.get("credential_matches") or []
    profile_matches = result.get("profile_matches") or []
    parts: list[str] = []
    if project_matches:
        parts.append(
            "projects: "
            + ", ".join(f"{name} ({sim:.2f})" for name, sim in project_matches[:2])
        )
    if experience_matches:
        parts.append(
            "experience: "
            + ", ".join(f"{name} ({sim:.2f})" for name, sim in experience_matches[:2])
        )
    if skill_matches:
        parts.append(
            "skills: "
            + ", ".join(f"{name} ({sim:.2f})" for name, sim in skill_matches[:3])
        )
    if credential_matches:
        parts.append(
            "credentials: "
            + ", ".join(f"{name} ({sim:.2f})" for name, sim in credential_matches[:2])
        )
    if profile_matches:
        parts.append(
            "profile: "
            + ", ".join(f"{name} ({sim:.2f})" for name, sim in profile_matches[:1])
        )
    source = result.get("source") or (result.get("raw") or {}).get("source") or "semantic"
    mode = result.get("mode") or (result.get("raw") or {}).get("mode") or ""
    descriptor = f"{source}, {mode}" if mode else source
    reason = f"embedding similarity vs current profile ({descriptor})"
    if parts:
        reason += " - " + "; ".join(parts)
    # Make degraded scoring legible: a hash-fallback score means the local
    # embedding runtime pack isn't installed, so matching is approximate.
    from ranking.semantic import _is_semantic_provider

    if mode and not _is_semantic_provider(mode):
        reason += " [degraded: local embedding runtime not installed, scores approximate]"
    return CriterionScore("Semantic fit", score, weight, reason)


def score_job_lead(jd: str, candidate_data: dict) -> ScoreResult:
    from ranking.criteria.evidence import evaluate_evidence
    from ranking.criteria.logistics import evaluate_logistics
    from ranking.criteria.role_alignment import evaluate_role_alignment
    from ranking.criteria.seniority_fit import evaluate_seniority_fit
    from ranking.criteria.stack_coverage import evaluate_stack_coverage

    candidate = analyze_candidate(candidate_data)
    posting = analyze_posting(jd, "Job lead")
    # Field-agnostic step: credit the candidate's own domain vocabulary and make
    # the wrong-field judgement relative to the candidate (must run before the
    # criteria and caps read posting.terms / posting.wrong_field).
    apply_domain_generalization(posting, candidate, candidate_data, jd)
    role = evaluate_role_alignment(posting, candidate)
    seniority = evaluate_seniority_fit(posting, candidate)
    constraints = evaluate_logistics(posting, candidate)

    semantic = _semantic_criterion(jd, candidate_data, weight=15)
    if semantic is not None:
        # Hybrid weighting: semantic acts as a tiebreaker, keyword/rubric still leads.
        stack = evaluate_stack_coverage(posting, candidate, 20)
        proof = evaluate_evidence(posting, candidate, 18)
        criteria = [
            _with_weight(role, 15),
            stack,
            proof,
            _with_weight(seniority, 20),
            _with_weight(constraints, 12),
            semantic,
        ]
    else:
        stack = evaluate_stack_coverage(posting, candidate, 27)
        proof = evaluate_evidence(posting, candidate, 20)
        criteria = [role, stack, proof, _with_weight(seniority, 20), constraints]

    direct, adjacent, missing = _direct_and_adjacent(posting, candidate)
    raw = _weighted_total(criteria)
    final, caps, applied_cap = _apply_caps(raw, posting, candidate, direct, adjacent)
    result = _result(final, criteria, posting, candidate, direct, adjacent, missing, caps, applied_cap)
    if semantic is None:
        result.gaps.append("Semantic matching unavailable; used deterministic keyword/rubric scoring.")
    return result


class ScoringEngine:
    """Thin orchestrator facade for the deterministic ranking rubric."""

    def score(self, job: str, candidate: dict) -> ScoreResult:
        return score_job_lead(job, candidate)
