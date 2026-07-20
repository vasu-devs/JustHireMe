"""Extract a field-agnostic RequirementSet (from a job) and CapabilitySet (from a
candidate) in a shared, taxonomy-optional phrase space.

No profession list and no tech-only vocabulary: a requirement or capability is any
short phrase drawn from the job's or candidate's OWN text. Tech phrases additionally
canonicalize through ``SKILL_CANONICAL`` (k8s→Kubernetes), but that is a bonus, not a
gate — a nurse's "phlebotomy" or a welder's "TIG welding" flows through unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from data.skill_taxonomy import SKILL_CANONICAL
from ranking.fit.text import (
    importance_of,
    normalize_phrase,
    split_phrases,
    strip_identity,
    tokens,
)

# Evidence tiers (design §4.3) — how strongly the candidate has DEMONSTRATED a
# capability. Field-agnostic: a nurse's clinical placement and a dev's shipped repo
# both count as "experience"/"project".
TIER_PROJECT_STRONG = 1.00   # project with repo + measurable impact
TIER_PROJECT = 0.88          # project with a real stack
TIER_EXPERIENCE = 0.80       # named in employment
TIER_CREDENTIAL = 0.70       # certification / licence held
TIER_LISTED = 0.55           # listed skill, no corroboration

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def canon(phrase: str) -> str:
    """Canonical key for a phrase: a known tech alias maps to its canonical form,
    everything else is its own normalized text. Field-agnostic — non-tech phrases are
    their own canon, so matching still works with no taxonomy entry."""
    norm = normalize_phrase(phrase)
    return SKILL_CANONICAL.get(norm, norm)


@dataclass
class Capability:
    canon: str
    display: str
    tier: float
    sources: list[str] = field(default_factory=list)


@dataclass
class CapabilitySet:
    by_canon: dict[str, Capability]
    role_tokens: set[str]        # occupation signature (candidate role titles)
    credential_tokens: set[str]  # tokens of held certs/licences
    work_months: int
    profile_text: str            # identity-neutralized, for the semantic facet

    def phrases(self) -> list[Capability]:
        return list(self.by_canon.values())


@dataclass
class Requirement:
    canon: str
    display: str
    importance: float
    is_credential: bool = False


@dataclass
class RequirementSet:
    items: list[Requirement]
    title: str
    title_tokens: set[str]       # occupation signature (job title)
    req_years: int
    hard_licence: bool           # a licence/registration is explicitly REQUIRED
    licence_tokens: set[str]
    jd_text: str                 # identity-neutralized, for the semantic facet
    thin: bool


# ── candidate side ─────────────────────────────────────────────────────────────
def _add(caps: dict[str, Capability], phrase: str, tier: float, source: str) -> None:
    key = canon(phrase)
    disp = phrase.strip()
    if not key or len(key) < 2:
        return
    existing = caps.get(key)
    if existing is None:
        caps[key] = Capability(canon=key, display=disp, tier=tier, sources=[source])
    else:
        existing.tier = max(existing.tier, tier)   # strongest evidence wins
        if source not in existing.sources:
            existing.sources.append(source)


def _split_stack(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if not value:
        return []
    return [p.strip() for p in re.split(r"[,;/|]", str(value)) if p.strip()]


def _period_months(period: str) -> int:
    if not period:
        return 0
    text = str(period).lower()
    now = datetime.now(timezone.utc).strftime("%b %Y").lower()
    text = re.sub(r"\bpresent\b|\bcurrent\b|\bnow\b|\btoday\b", now, text)
    pairs = re.findall(r"([a-z]{3,4})?\s*(\d{4})\s*(?:to|-|–|—|->|→)\s*([a-z]{3,4})?\s*(\d{4})", text)
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
        m = re.search(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)", text)
        if m:
            months = int(m.group(1)) * 12
    return months


def build_capability_set(cand: dict) -> CapabilitySet:
    cand = cand if isinstance(cand, dict) else {}
    caps: dict[str, Capability] = {}

    for skill in cand.get("skills", []) or []:
        name = skill.get("n") or skill.get("name") if isinstance(skill, dict) else skill
        if name:
            _add(caps, str(name), TIER_LISTED, "skills")

    for proj in cand.get("projects", []) or []:
        if not isinstance(proj, dict):
            continue
        has_repo = bool(str(proj.get("repo") or "").strip())
        has_impact = len(str(proj.get("impact") or "").split()) >= 6
        tier = TIER_PROJECT_STRONG if (has_repo and has_impact) else TIER_PROJECT
        title = str(proj.get("title") or "project")
        for item in _split_stack(proj.get("stack") or proj.get("s")):
            _add(caps, item, tier, f"project: {title}")

    for exp in cand.get("exp", []) or []:
        if not isinstance(exp, dict):
            continue
        label = str(exp.get("role") or exp.get("co") or "experience")
        for item in _split_stack(exp.get("s") or exp.get("stack")):
            _add(caps, item, TIER_EXPERIENCE, f"experience: {label}")
        # Harvest competency phrases from the role description itself (field-agnostic —
        # a nurse's "ICU patient care" or a lawyer's "contract drafting" is real
        # evidence even when not itemized in a skills list). This also UPGRADES a
        # listed skill's tier when it recurs here (_add keeps the strongest tier).
        for phrase in split_phrases(exp.get("d") or "", cap=12):
            _add(caps, phrase, TIER_EXPERIENCE, f"experience: {label}")
        _add(caps, exp.get("role") or "", TIER_EXPERIENCE, f"role: {label}")

    for proj in cand.get("projects", []) or []:
        if not isinstance(proj, dict):
            continue
        title = str(proj.get("title") or "project")
        for phrase in split_phrases(proj.get("impact") or "", cap=8):
            _add(caps, phrase, TIER_PROJECT, f"project: {title}")

    for phrase in split_phrases(cand.get("s") or "", cap=10):
        _add(caps, phrase, TIER_LISTED, "summary")

    credential_tokens: set[str] = set()
    for key in ("certifications", "certs", "achievements", "education"):
        for item in cand.get(key, []) or []:
            title = item.get("title") or item.get("name") if isinstance(item, dict) else item
            title = str(title or "").strip()
            if title:
                _add(caps, title, TIER_CREDENTIAL, key)
                credential_tokens |= tokens(title)

    role_tokens: set[str] = set()
    real_roles: list[dict] = []
    for exp in cand.get("exp", []) or []:
        if not isinstance(exp, dict):
            continue
        role = str(exp.get("role") or "")
        if not role:
            continue
        if any(kw in role.lower() for kw in ("intern", "trainee", "student")):
            continue
        real_roles.append(exp)
        role_tokens |= tokens(role)
    role_tokens |= tokens(cand.get("desired_position") or "")

    # Work months: dated periods, floored by any explicit "N years" in prose.
    dated = sum(_period_months(e.get("period", "")) for e in real_roles)
    prose = " ".join([str(cand.get("s") or ""), *[str(e.get("d") or "") for e in real_roles]]).lower()
    stated = [int(m) for m in re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)", prose)]
    work_months = max(dated, (max(stated) * 12) if stated else 0)

    profile_parts = [str(cand.get("s") or "")]
    for exp in real_roles:
        profile_parts.append(f"{exp.get('role','')} {exp.get('d','')}")
    for proj in cand.get("projects", []) or []:
        if isinstance(proj, dict):
            profile_parts.append(f"{proj.get('title','')} {proj.get('impact','')}")
    profile_text = strip_identity(" ".join(p for p in profile_parts if p))

    return CapabilitySet(
        by_canon=caps,
        role_tokens=role_tokens,
        credential_tokens=credential_tokens,
        work_months=work_months,
        profile_text=profile_text,
    )


# ── job side ────────────────────────────────────────────────────────────────────
_FIELD_RE = {
    "title": re.compile(r"(?im)^\s*(?:job\s+title|gig\s+title|title)\s*:\s*(.+)$"),
    "desc": re.compile(r"(?im)^\s*description\s*:\s*(.+)$"),
}
# Licence cues — the ACT of being licensed/registered, not a profession list. Paired
# with a "required/must" cue before the gate fires (see build_requirement_set).
_LICENCE_CUES = (
    "license", "licence", "licensed", "licensure", "registered nurse", "board certified",
    "board-certified", "chartered", "accredited", "certification required",
    "certified public accountant", "cpa", "bar admission", "member of the bar",
    "cdl", "pe license", "professional engineer license", "must be certified",
    "valid certification", "state license", "rn license", "practising certificate",
)
_YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?|yoe)", re.I)

# Credential-MARKER tokens: the words that denote holding a licence/registration, as
# opposed to the profession itself. The credential gate is satisfied only when the
# candidate carries one of THESE (e.g. "registered", an "RN"), not merely the
# occupation noun ("nurse") — so an aspiring/unlicensed practitioner is still gated.
_CREDENTIAL_MARKERS = frozenset({
    "registered", "licensed", "licence", "license", "licensure", "certified",
    "certification", "certificate", "chartered", "accredited", "board", "rn", "lpn",
    "cpa", "cfa", "cdl", "bar", "esq", "pe", "pmp", "cissp", "cna", "emt", "paramedic",
})

# Requirement phrases that are about SENIORITY or hiring boilerplate, not a competency.
# Excluded from the coverage/occupation facets (φ_sen already scores years of
# experience) so they don't read as an unmet skill and wrongly trip the cross-field
# gate for an in-field junior. Field-neutral: these are generic hiring words.
_REQ_NOISE_TOKENS = frozenset({
    "professional", "requires", "require", "required", "seeking", "looking", "hiring",
    "join", "build", "building", "help", "helping", "strong", "proven", "demonstrated",
    "ability", "responsible", "responsibilities", "opportunity", "position", "company",
    "seeker", "applicant", "please", "apply", "salary", "benefits", "location",
})


def _is_noise_requirement(phrase: str) -> bool:
    if _YEARS_RE.search(phrase):
        return True
    content = tokens(phrase)
    return not content or content <= _REQ_NOISE_TOKENS


_MARKER_LINE_RE = re.compile(r"(?im)^\s*(?:company|url|client)\s*:.*$")
_MARKER_PREFIX_RE = re.compile(r"(?im)^\s*(?:job\s+title|gig\s+title|title|description)\s*:\s*")


def _clean_body(jd: str) -> str:
    """Strip the assembled-JD field markers ("Job Title:", "Description:") and the
    Company/URL lines so they are not mistaken for competency requirements."""
    text = _MARKER_LINE_RE.sub(" ", jd or "")
    return _MARKER_PREFIX_RE.sub("", text)


def _title_of(jd: str) -> str:
    m = _FIELD_RE["title"].search(jd or "")
    if m:
        return m.group(1).strip()[:180]
    for line in (jd or "").splitlines():
        line = line.strip()
        low = line.lower()
        if line and not low.startswith(("company:", "url:", "description:", "http")):
            return line[:180]
    return ""


def build_requirement_set(jd: str) -> RequirementSet:
    jd = jd or ""
    title = _title_of(jd)
    clean = _clean_body(jd)
    body = strip_identity(clean)
    low = body.lower()

    reqs: dict[str, Requirement] = {}
    default_imp = 0.7  # "weak-must": the field-agnostic default when no cue is present
    for clause in re.split(r"[\n.;]", clean):
        clause = clause.strip()
        if not clause:
            continue
        imp = importance_of(clause, default_imp)
        for phrase in split_phrases(clause):
            key = canon(phrase)
            if len(key) < 2 or _is_noise_requirement(phrase):
                continue
            existing = reqs.get(key)
            if existing is None or imp > existing.importance:
                reqs[key] = Requirement(canon=key, display=phrase.strip(), importance=imp)
    # Title phrases are strong requirements too.
    for phrase in split_phrases(title):
        key = canon(phrase)
        if key and (key not in reqs or reqs[key].importance < 1.0):
            reqs[key] = Requirement(canon=key, display=phrase.strip(), importance=1.0)

    licence_tokens: set[str] = set()
    hard_licence = False
    for cue in _LICENCE_CUES:
        if cue in low:
            # Keep only the credential-marker tokens (so "registered nurse" contributes
            # "registered", not the generic "nurse" that any nurse-adjacent CV mentions).
            licence_tokens |= (tokens(cue) & _CREDENTIAL_MARKERS)
            # Only a HARD gate when the licence is stated as required/must-have.
            idx = low.find(cue)
            window = low[max(0, idx - 60):idx + 60]
            if any(w in window for w in ("required", "must", "mandatory", "need", "essential")):
                hard_licence = True
            for r in reqs.values():
                if tokens(cue) & tokens(r.display):
                    r.is_credential = True

    years = [int(m) for m in _YEARS_RE.findall(jd)]
    # senior/lead/principal/manager imply a years floor even when unstated
    senior_floor = 0
    if re.search(r"\b(senior|sr\.?|lead|staff|principal)\b", low):
        senior_floor = 5
    if re.search(r"\b(manager|head of|director)\b", low):
        senior_floor = max(senior_floor, 6)
    req_years = max([*years, senior_floor]) if (years or senior_floor) else 0

    thin = len(re.sub(r"\s+", " ", body)) < 160 or len(reqs) < 2

    return RequirementSet(
        items=list(reqs.values()),
        title=title,
        title_tokens=tokens(title),
        req_years=req_years,
        hard_licence=hard_licence,
        licence_tokens=licence_tokens,
        jd_text=body,
        thin=thin,
    )
