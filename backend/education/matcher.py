"""Education Matcher — core logic for pairing job leads with Master programs."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from education.city_extractor import extract_city, get_city_search_terms
from education.domain_classifier import classify_domain
from education.mon_master_client import query_mon_master


class MatchedProgram(BaseModel):
    program_id: str = ""
    program_title: str = ""
    university: str = ""
    city: str = ""
    uai_code: str = ""
    domain: str = ""
    modalities: list[str] = []
    capacity: int = 0
    program_url: Optional[str] = None
    match_score: float = 0.0
    match_reason: str = ""
    alternance_eligible: bool = False
    user_approved: bool = False


def _extract_id_from_program(program: dict) -> str:
    """Build a stable ID from program fields."""
    uai = program.get("etab_uai") or ""
    intitule = program.get("for_intitule") or ""
    return f"{uai}-{intitule}".replace(" ", "_").replace("/", "_")[:120]


def _normalize_modalities(raw: str | list | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(m).strip() for m in raw if str(m).strip()]
    return [m.strip() for m in str(raw).split(",") if m.strip()]


def _rank_programs(programs: list[dict], job_description: str, classified_domain: str | None = None) -> MatchedProgram | None:
    """Rank programs by keyword overlap with job description."""
    if not programs:
        return None

    job_words = set(
        re.findall(
            r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}",
            job_description.lower(),
        )
    )
    # Remove common stop words
    stop = {
        "and", "the", "with", "for", "from", "that", "this", "you", "are",
        "job", "role", "engineer", "developer", "company", "team", "will",
        "have", "has", "using", "build", "work", "your", "their", "chez",
        "poste", "recherche", "recrute", "alternance", "apprentissage",
    }
    job_words -= stop

    scored: list[tuple[float, dict]] = []
    for prog in programs:
        title = str(prog.get("for_intitule") or "").lower()
        domain_text = str(prog.get("for_dom") or "").lower()
        program_words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", f"{title} {domain_text}"))
        overlap = len(job_words & program_words)
        score = overlap

        # Boost if domain matches the classified domain (partial match, handles accents)
        if classified_domain and classified_domain.lower() in domain_text:
            score += 10

        # Boost if "informatique" or related terms in program title when job is tech
        tech_program_indicators = ["informatique", "data", "développement", "developpement", "software", "numérique", "numerique"]
        if any(t in title for t in tech_program_indicators):
            # Boost if job description contains tech terms
            tech_job_terms = ["développeur", "developpeur", "software", "fullstack", "backend", "frontend", "devops", "react", "node", "python", "data", "web", "mobile"]
            if any(t in job_description.lower() for t in tech_job_terms):
                score += 5

        scored.append((score, prog))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    best_score = scored[0][0]

    modalities = _normalize_modalities(best.get("for_modalite"))
    alternance_eligible = any("alternance" in m.lower() for m in modalities)

    return MatchedProgram(
        program_id=_extract_id_from_program(best),
        program_title=best.get("for_intitule") or "",
        university=best.get("etab_nom") or "",
        city=best.get("etab_ville") or "",
        uai_code=best.get("etab_uai") or "",
        domain=best.get("for_dom") or "",
        modalities=modalities,
        capacity=int(best.get("for_capacite") or 0),
        program_url=best.get("for_lien_fiche_principal") or None,
        match_score=float(best_score),
        match_reason=f"Keyword overlap: {int(best_score)} matching terms between job description and program title/domain",
        alternance_eligible=alternance_eligible,
    )


class EducationMatcher:
    """Matches a job lead to the best French Master program in the same city."""

    def match(self, lead: dict, profile: dict | None = None) -> MatchedProgram | None:
        """Find the best matching Master program for a job lead.

        Steps:
        1. Extract city from lead location/description.
        2. Classify domain from job title/description.
        3. Query Mon Master API for programs in that city with Alternance.
        4. If none found, query without Alternance filter.
        5. Rank by keyword overlap.
        6. Return best match.
        """
        location = lead.get("location") or ""
        description = lead.get("description") or ""
        title = lead.get("title") or ""

        city = extract_city(location, description)
        if not city:
            return None

        domain = classify_domain(title, description)

        # Primary search: with alternance
        search_terms = get_city_search_terms(city)
        all_programs: list[dict] = []
        for term in search_terms:
            programs = query_mon_master(city=term, domain=domain, modalities=["Alternance"])
            all_programs.extend(programs)

        alternance_eligible = True
        if not all_programs:
            # Fallback: search without alternance filter
            alternance_eligible = False
            for term in search_terms:
                programs = query_mon_master(city=term, domain=domain)
                all_programs.extend(programs)

        if not all_programs:
            return None

        # Deduplicate by (UAI + intitule)
        seen: set[str] = set()
        deduped: list[dict] = []
        for p in all_programs:
            key = f"{p.get('etab_uai')}-{p.get('for_intitule')}"
            if key not in seen:
                seen.add(key)
                deduped.append(p)

        best = _rank_programs(deduped, description, domain)
        if best:
            best.alternance_eligible = alternance_eligible
        return best
