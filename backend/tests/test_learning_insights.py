"""Learning-insights engine: gaps/strengths/themes mined from the lead corpus.

Pure-function tests â€” no DB, no LLM. The engine must stay deterministic,
recency-aware, near-miss-weighted, and field-agnostic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from learning import compute_learning_insights

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _lead(
    title: str,
    description: str,
    *,
    score: int = 70,
    days_ago: float = 1,
    status: str = "discovered",
    job_id: str = "",
    company: str = "Acme",
) -> dict:
    return {
        "job_id": job_id or title.lower().replace(" ", "-"),
        "title": title,
        "company": company,
        "description": description,
        "score": score,
        "status": status,
        "created_at": _iso(days_ago),
    }


TECH_PROFILE = {
    "n": "Test Candidate",
    "s": "Frontend engineer building React and TypeScript apps.",
    "skills": [{"n": "React"}, {"n": "TypeScript"}],
    "projects": [{"title": "Dash", "stack": ["React", "TypeScript"], "impact": "Shipped a dashboard"}],
    "exp": [],
}


def test_missing_market_skill_becomes_a_ranked_gap():
    leads = [
        _lead(f"Platform role {i}", "We need Kubernetes experience for our infra.", score=70, days_ago=2, job_id=f"k{i}")
        for i in range(3)
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    gap_skills = [g["skill"].lower() for g in out["gaps"]]
    assert "kubernetes" in gap_skills
    gap = next(g for g in out["gaps"] if g["skill"].lower() == "kubernetes")
    assert gap["postings"] == 3
    assert gap["first_step"]


def test_owned_skills_are_strengths_not_gaps():
    leads = [
        _lead(f"Frontend role {i}", "React and TypeScript product work.", score=88, days_ago=2, job_id=f"r{i}")
        for i in range(4)
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    assert all(g["skill"].lower() not in ("react", "typescript") for g in out["gaps"])
    strength_skills = {s["skill"].lower() for s in out["strengths"]}
    assert "react" in strength_skills


def test_near_miss_demand_outranks_equal_far_demand():
    # Same posting count and freshness; kubernetes appears in near-miss roles
    # (one skill from convertible), django only in already-strong matches.
    leads = [
        _lead("Infra role A", "Kubernetes required.", score=70, days_ago=2, job_id="a"),
        _lead("Infra role B", "Kubernetes required.", score=70, days_ago=2, job_id="b"),
        _lead("Backend role A", "Django required.", score=90, days_ago=2, job_id="c"),
        _lead("Backend role B", "Django required.", score=90, days_ago=2, job_id="d"),
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    order = [g["skill"].lower() for g in out["gaps"]]
    assert order.index("kubernetes") < order.index("django")


def test_fresh_demand_outranks_stale_demand():
    leads = [
        _lead("New role A", "Rust systems work.", score=70, days_ago=1, job_id="n1"),
        _lead("New role B", "Rust systems work.", score=70, days_ago=2, job_id="n2"),
        _lead("Old role A", "GraphQL API work.", score=70, days_ago=45, job_id="o1"),
        _lead("Old role B", "GraphQL API work.", score=70, days_ago=45, job_id="o2"),
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    order = [g["skill"].lower() for g in out["gaps"]]
    assert order.index("rust") < order.index("graphql")


def test_single_posting_skills_are_noise_not_gaps():
    leads = [
        _lead("One-off", "Needs COBOL.", score=70, days_ago=1, job_id="one"),
        _lead("Common A", "Needs Kubernetes.", score=70, days_ago=1, job_id="c1"),
        _lead("Common B", "Needs Kubernetes.", score=70, days_ago=1, job_id="c2"),
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    assert all(g["skill"].lower() != "cobol" for g in out["gaps"])


def test_discarded_leads_do_not_count_as_demand():
    leads = [
        _lead(f"Dead {i}", "Needs Kubernetes.", score=70, days_ago=1, status="discarded", job_id=f"d{i}")
        for i in range(5)
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    assert out["sample_size"] == 0
    assert out["gaps"] == []


def test_non_tech_profile_sees_its_own_market_demand():
    nurse = {
        "n": "Nurse Candidate",
        "s": "Registered nurse focused on ICU patient care.",
        "skills": [{"n": "patient care"}, {"n": "IV therapy"}],
        "projects": [],
        "exp": [{"role": "ICU Nurse", "co": "City Hospital", "period": "Jan 2020 - Jan 2026", "d": "Critical patient care", "s": []}],
    }
    leads = [
        _lead(f"ICU Nurse {i}", "ICU role: patient care and IV therapy required.", score=75, days_ago=2, job_id=f"n{i}")
        for i in range(3)
    ]
    out = compute_learning_insights(leads, nurse, now=NOW)
    strengths = {s["skill"].lower() for s in out["strengths"]}
    assert "patient care" in strengths


def test_small_sample_carries_an_honest_note():
    out = compute_learning_insights([], TECH_PROFILE, now=NOW)
    assert out["sample_size"] == 0
    assert "scan" in out["note"].lower()


def test_scrape_boilerplate_terms_never_count_as_demand():
    # Cloudflare block pages stored as descriptions read as "cloudflare demand"
    # without the noise guard (49% share in a real corpus).
    leads = [
        _lead(f"Blocked {i}", "Attention Required! Cloudflare Ray ID: abc.", score=70, days_ago=1, job_id=f"b{i}")
        for i in range(5)
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    mentioned = {g["skill"].lower() for g in out["gaps"]} | {s["skill"].lower() for s in out["strengths"]}
    assert "cloudflare" not in mentioned


def test_themes_surface_market_currents():
    leads = [
        _lead(f"AI role {i}", "Building AI agent and RAG retrieval systems.", score=70, days_ago=2, job_id=f"t{i}")
        for i in range(4)
    ]
    out = compute_learning_insights(leads, TECH_PROFILE, now=NOW)
    themes = {t["theme"] for t in out["themes"]}
    assert "ai agent" in themes
    assert "rag" in themes


# --- market-phrase mining: unknown-skill gaps beyond the tech taxonomy -------

NURSE_PROFILE = {
    "n": "Nurse Candidate",
    "s": "Registered nurse focused on ICU patient care.",
    "skills": [{"n": "patient care"}, {"n": "IV therapy"}],
    "projects": [],
    "exp": [{"role": "ICU Nurse", "co": "City Hospital", "period": "Jan 2020 - Jan 2026", "d": "Critical patient care", "s": []}],
}


def _semantic_stub(text: str) -> tuple[float, ...]:
    # Deterministic stand-in for real embeddings: posting boilerplate is
    # orthogonal to the nurse profile, everything else is on-field.
    lower = text.lower()
    if "opportunity" in lower or "employer" in lower:
        return (0.0, 1.0)
    return (1.0, 0.0)


def _patch_semantics(monkeypatch) -> None:
    # Phrase embeds go through the BATCHED seam; the profile embed through
    # _field_vector — both must be stubbed for deterministic mining tests.
    monkeypatch.setattr("learning.insights._field_vector", _semantic_stub)
    monkeypatch.setattr(
        "learning.insights._phrase_vectors",
        lambda phrases: {p: _semantic_stub(p) for p in phrases},
    )


def _icu_leads(companies: list[str], description: str = "Wound care for patients.") -> list[dict]:
    return [
        _lead(f"ICU Nurse {i}", description, score=75, days_ago=2, job_id=f"icu{i}", company=co)
        for i, co in enumerate(companies)
    ]


def test_recurring_market_phrase_surfaces_as_non_tech_gap(monkeypatch):
    # "wound care" is in no tech taxonomy and not in the nurse's profile, but
    # three independent hospitals keep asking for it.
    _patch_semantics(monkeypatch)
    leads = _icu_leads(["St Mary", "City General", "Lakeside Clinic"])
    out = compute_learning_insights(leads, NURSE_PROFILE, now=NOW)
    assert out["phrase_mining_skipped"] is False
    gap = next(g for g in out["gaps"] if g["skill"] == "wound care")
    assert gap["category"] == ""
    assert gap["adjacent"] is False
    assert gap["postings"] == 3
    assert "keeps appearing" in gap["first_step"]
    assert gap["example_roles"]


def test_hash_only_embeddings_skip_mining_and_flag_it(monkeypatch):
    # Hash cosine can't judge field relevance — no mined gaps may ship.
    monkeypatch.setattr("learning.insights._field_vector", lambda text: None)
    leads = _icu_leads(["St Mary", "City General", "Lakeside Clinic"])
    out = compute_learning_insights(leads, NURSE_PROFILE, now=NOW)
    assert out["phrase_mining_skipped"] is True
    assert all(g["skill"] != "wound care" for g in out["gaps"])


def test_boilerplate_phrases_fail_the_field_relevance_filter(monkeypatch):
    _patch_semantics(monkeypatch)
    leads = _icu_leads(
        ["St Mary", "City General", "Lakeside Clinic"],
        description="Wound care for patients. Equal opportunity employer statement.",
    )
    out = compute_learning_insights(leads, NURSE_PROFILE, now=NOW)
    skills = {g["skill"] for g in out["gaps"]}
    assert "wound care" in skills
    assert not any("opportunity" in s or "employer" in s for s in skills)


def test_phrases_from_a_single_company_are_boilerplate_not_gaps(monkeypatch):
    # Three postings but one employer: per-company boilerplate, not demand.
    _patch_semantics(monkeypatch)
    leads = _icu_leads(["Acme Health", "Acme Health", "Acme Health"])
    out = compute_learning_insights(leads, NURSE_PROFILE, now=NOW)
    assert out["phrase_mining_skipped"] is False
    assert all(g["skill"] != "wound care" for g in out["gaps"])


def test_mined_phrase_gaps_are_capped_at_four(monkeypatch):
    _patch_semantics(monkeypatch)
    desc = (
        "Wound care. Triage assessment. Ventilator management. "
        "Telemetry monitoring. Dialysis support. Catheter insertion."
    )
    leads = _icu_leads(["St Mary", "City General", "Lakeside Clinic"], description=desc)
    out = compute_learning_insights(leads, NURSE_PROFILE, now=NOW)
    mined = [g for g in out["gaps"] if "keeps appearing" in g["first_step"]]
    assert 0 < len(mined) <= 4


