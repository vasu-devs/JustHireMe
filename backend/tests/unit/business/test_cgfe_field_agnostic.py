"""Field-agnostic correctness proof for the Coverage-Grounded Fit Engine (CGFE).

These are the invariants that matter for "always correct across every role": the same
mechanism must score same-field pairs HIGH and cross-field pairs LOW for nursing,
welding, law, teaching, accounting, sales AND software — with no profession list.

Every invariant is checked TWICE: once in the ambient embedding mode, and once with the
semantic facet forced off (``no_embeddings``) to prove the keyless/hash flagship path
carries cross-field correctness on its own (design §1.2). Ordering locks are the
primary, mode-invariant guarantee; absolute bands are generous to hold across modes.
"""
from __future__ import annotations

from typing import ClassVar

import pytest

from ranking.fit import engine, score_fit

# ── candidate profiles across many fields ────────────────────────────────────────
NURSE = {
    "s": "Registered Nurse with 6 years ICU experience.",
    "skills": [{"n": "IV Therapy"}, {"n": "ACLS"}, {"n": "Patient Assessment"}, {"n": "Wound Care"}],
    "exp": [{"role": "Registered Nurse", "co": "City Hospital", "period": "2019 - Present",
             "d": "ICU patient care, wound care, medication administration, patient assessment"}],
}
WELDER = {
    "s": "Structural welder with 7 years experience.",
    "skills": [{"n": "MIG Welding"}, {"n": "TIG Welding"}, {"n": "Blueprint Reading"}, {"n": "Fabrication"}],
    "exp": [{"role": "Structural Welder", "co": "FabCo", "period": "2018 - Present",
             "d": "MIG and TIG welding, metal fabrication from blueprints"}],
}
LAWYER = {
    "s": "Corporate lawyer, 8 years, M&A and contracts.",
    "skills": [{"n": "Contract Drafting"}, {"n": "Legal Research"}, {"n": "Litigation"}, {"n": "Due Diligence"}],
    "exp": [{"role": "Corporate Attorney", "co": "Firm LLP", "period": "2016 - Present",
             "d": "contract drafting, mergers and acquisitions, legal research, litigation support"}],
}
TEACHER = {
    "s": "High school mathematics teacher, 5 years.",
    "skills": [{"n": "Lesson Planning"}, {"n": "Classroom Management"}, {"n": "Curriculum Design"}],
    "exp": [{"role": "Mathematics Teacher", "co": "Lincoln High", "period": "2019 - Present",
             "d": "lesson planning, classroom management, curriculum design, student assessment"}],
}
SWE = {
    "s": "Senior software engineer, 8 years backend.",
    "skills": [{"n": "Python"}, {"n": "FastAPI"}, {"n": "AWS"}, {"n": "PostgreSQL"}],
    "exp": [{"role": "Senior Engineer", "co": "Acme", "period": "Jan 2017 - Present",
             "d": "backend python fastapi microservices on aws with postgresql"}],
    "projects": [{"title": "Orders API", "stack": ["Python", "FastAPI", "AWS", "PostgreSQL"],
                  "impact": "Processed 1M orders per month", "repo": "https://x"}],
}

# ── jobs across the same fields ──────────────────────────────────────────────────
J_NURSE = ("Job Title: ICU Registered Nurse\nDescription: Seeking an experienced ICU nurse for "
           "patient assessment, IV therapy, wound care, and medication administration. 4+ years acute care.")
J_WELD = ("Job Title: Structural Welder\nDescription: MIG and TIG welding and metal fabrication from "
          "blueprints. 3+ years welding experience.")
J_LAW = ("Job Title: Corporate Attorney\nDescription: Contract drafting, mergers and acquisitions, "
         "legal research and litigation support. 5+ years.")
J_TEACH = ("Job Title: Mathematics Teacher\nDescription: Lesson planning, classroom management and "
           "curriculum design for high school students.")
J_SWE = ("Job Title: Backend Engineer\nDescription: Build Python and FastAPI services with PostgreSQL "
         "on AWS for our platform.")

SAME_FIELD = [
    ("nurse", NURSE, J_NURSE), ("welder", WELDER, J_WELD), ("lawyer", LAWYER, J_LAW),
    ("teacher", TEACHER, J_TEACH), ("swe", SWE, J_SWE),
]
# (candidate, own-field job, foreign-field job) for ordering locks
CROSS_PAIRS = [
    ("nurse", NURSE, J_NURSE, J_SWE), ("welder", WELDER, J_WELD, J_LAW),
    ("lawyer", LAWYER, J_LAW, J_WELD), ("swe", SWE, J_SWE, J_NURSE),
    ("teacher", TEACHER, J_TEACH, J_WELD),
]


@pytest.fixture
def no_embeddings(monkeypatch):
    """Force the keyless/hash flagship path: the semantic facet contributes nothing."""
    monkeypatch.setattr(engine, "_semantic", lambda *a, **k: (0.0, 0.0, "none"))


def _score(prof, jd) -> int:
    return score_fit(jd, prof).score


class TestSameFieldScoresHigh:
    @pytest.mark.parametrize("name,prof,jd", SAME_FIELD)
    def test_ambient_mode(self, name, prof, jd):
        r = score_fit(jd, prof)
        assert r.score >= 68, f"{name} own-field scored only {r.score}"
        assert "wrong-field" not in r.cap_kinds

    @pytest.mark.parametrize("name,prof,jd", SAME_FIELD)
    def test_keyless_mode(self, name, prof, jd, no_embeddings):
        r = score_fit(jd, prof)
        assert r.score >= 62, f"{name} own-field scored only {r.score} keyless"
        assert "wrong-field" not in r.cap_kinds


class TestCrossFieldScoresLow:
    @pytest.mark.parametrize("name,prof,own,foreign", CROSS_PAIRS)
    def test_ambient_mode(self, name, prof, own, foreign):
        r = score_fit(foreign, prof)
        assert r.score <= 35, f"{name} cross-field scored {r.score}"
        assert "wrong-field" in r.cap_kinds

    @pytest.mark.parametrize("name,prof,own,foreign", CROSS_PAIRS)
    def test_keyless_mode(self, name, prof, own, foreign, no_embeddings):
        assert _score(prof, foreign) <= 35


class TestOrderingLocks:
    """The load-bearing, mode-invariant guarantee: own field must outrank foreign field."""

    @pytest.mark.parametrize("name,prof,own,foreign", CROSS_PAIRS)
    def test_own_outranks_foreign_ambient(self, name, prof, own, foreign):
        assert _score(prof, own) > _score(prof, foreign) + 25

    @pytest.mark.parametrize("name,prof,own,foreign", CROSS_PAIRS)
    def test_own_outranks_foreign_keyless(self, name, prof, own, foreign, no_embeddings):
        assert _score(prof, own) > _score(prof, foreign) + 25


class TestSeniorityIsNotWrongField:
    """An in-field junior applying to a senior role is a seniority mismatch, never a
    wrong-field one."""

    JUNIOR: ClassVar[dict] = {
        "s": "Junior Python developer, 1 year experience.",
        "skills": [{"n": "Python"}, {"n": "FastAPI"}, {"n": "PostgreSQL"}],
        "exp": [{"role": "Junior Developer", "co": "Startup", "period": "2025 - Present",
                 "d": "python fastapi postgresql services"}],
        "projects": [{"title": "API", "stack": ["Python", "FastAPI"], "impact": "internal tool", "repo": "x"}],
    }
    FRESHER: ClassVar[dict] = {"s": "Recent CS graduate.", "skills": [{"n": "Python"}, {"n": "FastAPI"}],
               "projects": [{"title": "Course Project", "stack": ["Python", "FastAPI"], "impact": "class assignment"}]}
    J_SENIOR = ("Job Title: Senior Backend Engineer\nDescription: Build Python and FastAPI services. "
                "Requires 5+ years professional experience.")
    J_JUNIOR = ("Job Title: Python Developer\nDescription: Build Python and FastAPI services with "
                "PostgreSQL for our analytics platform.")

    def test_in_field_junior_to_junior_role_high(self):
        r = score_fit(self.J_JUNIOR, self.JUNIOR)
        assert r.score >= 60 and "wrong-field" not in r.cap_kinds

    def test_junior_to_senior_is_seniority_not_wrong_field(self):
        r = score_fit(self.J_SENIOR, self.JUNIOR)
        assert "seniority" in r.cap_kinds
        assert "wrong-field" not in r.cap_kinds

    def test_fresher_to_senior_capped_low(self):
        r = score_fit(self.J_SENIOR, self.FRESHER)
        assert r.score <= 45
        assert "wrong-field" not in r.cap_kinds


class TestCredentialGate:
    # In-field and skill-covering, but NOT licensed — isolates the credential gate from
    # the cross-field gate (coverage + occupation are high, so only credential fires).
    UNLICENSED: ClassVar[dict] = {"s": "Nursing graduate, completed clinical rotations.",
                  "skills": [{"n": "Patient Assessment"}, {"n": "IV Therapy"}, {"n": "Wound Care"},
                             {"n": "Medication Administration"}],
                  "exp": [{"role": "Nursing Extern", "co": "General Hospital", "period": "2023 - Present",
                           "d": "patient assessment, iv therapy, wound care, medication administration"}]}
    J_RN = ("Job Title: ICU Registered Nurse\nDescription: Patient assessment, IV therapy, wound care "
            "and medication administration. Active RN license required. Registered nurse licensure mandatory.")

    def test_unlicensed_hits_credential_gate(self):
        r = score_fit(self.J_RN, self.UNLICENSED)
        assert "credential" in r.cap_kinds
        assert "wrong-field" not in r.cap_kinds  # they DO the work; they just lack the licence

    def test_licensed_practitioner_clears_credential_gate(self):
        r = score_fit(self.J_RN, NURSE)
        assert "credential" not in r.cap_kinds
        assert r.score >= 60


class TestCareerChangerEvidenceOverride:
    """A career-changer whose skills genuinely cover the job must NOT be hard
    wrong-field capped — the cross-field penalty is evidence-overridable."""

    def test_covering_skills_relax_cross_field(self):
        # A data analyst (adjacent) with real Python/SQL evidence applying to a
        # data-engineering job should not be treated as wrong-field.
        analyst = {"s": "Data analyst with Python and SQL.",
                   "skills": [{"n": "Python"}, {"n": "SQL"}, {"n": "PostgreSQL"}, {"n": "Data Pipelines"}],
                   "exp": [{"role": "Data Analyst", "co": "Corp", "period": "2020 - Present",
                            "d": "python sql data pipelines etl reporting"}]}
        jd = ("Job Title: Data Engineer\nDescription: Build data pipelines in Python and SQL with "
              "PostgreSQL. ETL and reporting.")
        r = score_fit(jd, analyst)
        assert "wrong-field" not in r.cap_kinds
        assert r.score >= 55


class TestDiscrimination:
    """Proof depth and JD specificity must separate candidates (design discrimination
    locks), and a singular 'year' form must still seniority-cap a fresher."""

    BARE: ClassVar[dict] = {"s": "Developer.", "skills": [{"n": "Python"}, {"n": "FastAPI"}, {"n": "PostgreSQL"}],
            "exp": [], "projects": []}
    DEEP: ClassVar[dict] = {"s": "Python developer.", "skills": [{"n": "Python"}, {"n": "FastAPI"}, {"n": "PostgreSQL"}],
            "exp": [{"role": "Python Developer", "co": "Acme", "period": "Jan 2023 - Present",
                     "d": "Built Python FastAPI services backed by PostgreSQL"}],
            "projects": [{"title": "Metrics API", "stack": ["Python", "FastAPI", "PostgreSQL"], "impact": "Live metrics service"},
                         {"title": "ETL Runner", "stack": ["Python", "PostgreSQL"], "impact": "Nightly data loads"}]}
    J_NOYEARS = ("Job Title: Python Developer\nDescription: Build Python and FastAPI services with "
                 "PostgreSQL for our analytics platform.")
    STRONG: ClassVar[dict] = {"s": "Backend engineer, 5 years Python.",
              "skills": [{"n": "Python"}, {"n": "FastAPI"}, {"n": "PostgreSQL"}, {"n": "AWS"}, {"n": "Docker"}, {"n": "Redis"}],
              "exp": [{"role": "Backend Engineer", "co": "Acme", "period": "Jan 2021 - Present",
                       "d": "Python FastAPI services on AWS with PostgreSQL, Redis caching, Docker deploys"}],
              "projects": [{"title": "Orders API", "stack": ["Python", "FastAPI", "PostgreSQL", "Redis"], "impact": "1M orders per month", "repo": "x"}]}
    J_GENERIC = ("Job Title: Backend Developer\nDescription: Backend developer comfortable with Python "
                 "and PostgreSQL. 3+ years experience required.")
    J_SPECIFIC = ("Job Title: Backend Developer\nDescription: Build Python, FastAPI, PostgreSQL, Redis, "
                  "Docker and AWS services. 3+ years experience required.")
    FRESHER: ClassVar[dict] = {"s": "Recent graduate.", "skills": [{"n": "Python"}, {"n": "FastAPI"}],
               "projects": [{"title": "Course Project", "stack": ["Python", "FastAPI"], "impact": "class assignment"}]}
    J_SINGULAR_YEAR = ("Job Title: Python Developer\nDescription: Build Python and FastAPI services. "
                       "Requires 3+ year of professional experience; 1+ year with FastAPI preferred.")

    def test_proof_depth_beats_bare_skills(self):
        assert score_fit(self.J_NOYEARS, self.DEEP).score > score_fit(self.J_NOYEARS, self.BARE).score

    def test_specific_jd_beats_generic_coverage(self):
        assert score_fit(self.J_SPECIFIC, self.STRONG).score >= score_fit(self.J_GENERIC, self.STRONG).score

    def test_singular_year_seniority_caps_fresher(self):
        r = score_fit(self.J_SINGULAR_YEAR, self.FRESHER)
        assert r.score <= 38
        assert "seniority" in r.cap_kinds
        assert "wrong-field" not in r.cap_kinds


class TestReviewRegressions:
    """Concrete defects found by the adversarial review — each must stay fixed."""

    def test_company_history_years_do_not_fabricate_seniority(self):
        # "served the community for over 20 years" must not become a 20-year requirement.
        barista = {"s": "Barista", "skills": [{"n": "coffee"}, {"n": "customer service"}],
                   "exp": [{"role": "Barista", "co": "Cafe", "period": "2024-2025", "d": "Made coffee and served customers"}]}
        jd = ("Job Title: Junior Barista\nDescription: Make coffee and serve customers. Our cafe has "
              "proudly served the community for over 20 years.")
        r = score_fit(jd, barista)
        assert "seniority" not in r.cap_kinds
        assert r.score >= 60

    def test_credential_gate_not_bypassed_by_incidental_tokens(self):
        # A "progress bar" project must not satisfy a "bar admission" requirement.
        lawgrad = {"s": "Law graduate: legal research, contract drafting, litigation",
                   "skills": [{"n": "legal research"}, {"n": "contract drafting"}, {"n": "litigation"}],
                   "exp": [{"role": "Legal Assistant", "co": "Firm", "period": "2021-2024",
                            "d": "legal research, drafted contracts, litigated cases"}],
                   "projects": [{"title": "Personal site", "stack": "HTML",
                                 "impact": "Added a progress bar and status bar to the reading view"}]}
        jd = "Job Title: Attorney\nDescription: Bar admission required. Draft contracts, conduct legal research, litigate."
        assert "credential" in score_fit(jd, lawgrad).cap_kinds

    def test_generic_shared_words_do_not_defeat_cross_field(self):
        # SWE vs a terse RN posting: shared generic tokens (care/communication/
        # documentation) must not lift occupation above the cross-field floor.
        swe = {"s": "Software engineer, patient documentation systems and communication",
               "skills": [{"n": "communication"}, {"n": "documentation"}, {"n": "python"}, {"n": "java"}],
               "exp": [{"role": "Software Engineer", "co": "HealthTech", "period": "2019-2024",
                        "d": "Built patient documentation and communication tools"}]}
        jd = "Job Title: Registered Nurse\nDescription: Provide patient care and documentation. Communication essential."
        r = score_fit(jd, swe)
        assert "wrong-field" in r.cap_kinds
        assert r.score <= 40

    def test_non_string_role_does_not_crash(self):
        prof = {"skills": [{"n": "python"}], "exp": [{"role": 123, "co": "Acme", "period": "2020-2024", "d": "built things"}]}
        assert 0 <= score_fit("Job Title: Developer\nDescription: python required", prof).score <= 100

    def test_year_only_period_not_inflated(self):
        from ranking.fit.extract import _period_months
        assert 44 <= _period_months("2020 to 2024") <= 52   # ~4 years, not 60 months

    def test_richer_profile_not_penalized_on_own_field(self):
        # More real nursing evidence must not LOWER the own-field score vs a sparse nurse.
        sparse = {"s": "Nurse", "skills": [{"n": "Patient Care"}],
                  "exp": [{"role": "Registered Nurse", "co": "H", "period": "2019 - Present", "d": "patient care"}]}
        rich = {"s": "Registered Nurse, 6 years ICU",
                "skills": [{"n": "IV Therapy"}, {"n": "ACLS"}, {"n": "Patient Assessment"}, {"n": "Wound Care"}, {"n": "Triage"}],
                "exp": [{"role": "Registered Nurse", "co": "City Hospital", "period": "2019 - Present",
                         "d": "ICU patient care wound care medication administration"}]}
        jd = "Job Title: Registered Nurse\nDescription: Provide patient care and documentation. Communication essential."
        assert score_fit(jd, rich).score >= score_fit(jd, sparse).score - 8


class TestRobustness:
    def test_deterministic(self):
        a = score_fit(J_NURSE, NURSE).score
        b = score_fit(J_NURSE, NURSE).score
        assert a == b

    def test_thin_posting_not_auto_zeroed(self):
        # A terse but on-field stub should reach REVIEW, not be crushed to discard.
        r = engine.evaluate_fit("Job Title: ICU Nurse\nDescription: ICU nurse needed.", NURSE)
        assert r.band in {"advance", "review"}
        assert r.score >= 45

    def test_empty_inputs_do_not_crash(self):
        assert 0 <= score_fit("", {}).score <= 100
        assert 0 <= score_fit("Job Title: X", {"skills": []}).score <= 100
