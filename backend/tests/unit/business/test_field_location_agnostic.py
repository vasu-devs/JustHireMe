"""Field- and location-agnostic guarantees.

JustHireMe must work for ANY profession in ANY region, not just software/remote.
These lock in the generalization: non-tech candidates score on their own merits
(no "not a software job" floor), the discovery quality gate keeps real non-tech
postings, and discovery queries target the user's actual location.
"""

from __future__ import annotations

from core.config import discovery_location, profile_for_discovery, profile_x_queries
from discovery.lead_intel import signal_quality
from discovery.normalizer import looks_role_like
from discovery.query_gen import _location_clause
from ranking.scoring_engine import score_job_lead

_NURSE = {
    "s": "Registered Nurse with 6 years in acute and ICU care.",
    "skills": [{"n": "IV Therapy"}, {"n": "ACLS"}, {"n": "Patient Assessment"}, {"n": "Wound Care"}],
    "exp": [{"role": "Registered Nurse", "co": "City Hospital", "period": "Jan 2019 - Present",
             "d": "ICU patient care, IV therapy, medication administration"}],
    "certifications": [{"title": "BLS Certification"}],
}
_NURSE_JD = (
    "Job Title: ICU Registered Nurse\nCompany: Mercy Health\n"
    "Description: Seeking an experienced ICU nurse for patient assessment, IV therapy, "
    "wound care, and medication administration. ACLS required. 4+ years acute care."
)
_SWE = {
    "s": "Senior software engineer",
    "skills": [{"n": "Python"}, {"n": "React"}, {"n": "AWS"}],
    "exp": [{"role": "Senior Engineer", "co": "Acme", "period": "Jan 2018 - Present", "d": "backend python"}],
}


def test_in_field_non_tech_is_not_floored():
    # A nurse applying to a nursing job must score on merit, not be hard-capped
    # to the old "non-technical field" 15.
    score = score_job_lead(_NURSE_JD, _NURSE).as_dict()["score"]
    assert score >= 55, f"in-field nurse scored {score}, expected a real (non-floored) score"


def test_cross_field_still_capped():
    # A software engineer applying to a nursing job SHOULD be penalized as a
    # genuine field mismatch — the generalization must not make everything match.
    result = score_job_lead(_NURSE_JD, _SWE).as_dict()
    assert result["score"] <= 40, f"cross-field SWE->nursing scored {result['score']}, expected low"


def test_tech_in_field_unchanged():
    swe_jd = ("Job Title: Senior Backend Engineer\nDescription: Python, FastAPI, AWS. "
              "Build backend services. 5+ years.")
    score = score_job_lead(swe_jd, _SWE).as_dict()["score"]
    assert score >= 55


def test_quality_gate_keeps_non_tech_postings():
    nurse_post = ("We are hiring an ICU Registered Nurse. Full-time, competitive salary, "
                  "apply now. Responsibilities include patient care.")
    welder_post = "Hiring a Structural Welder for MIG/TIG welding. Full-time position, apply today."
    assert signal_quality(nurse_post)["score"] >= 60
    assert signal_quality(welder_post)["score"] >= 60
    # Noise still rejected.
    assert signal_quality("Free crypto airdrop giveaway newsletter, subscribe for memes")["score"] < 40


def test_role_detection_is_field_agnostic():
    assert looks_role_like("Registered Nurse | Berlin | full-time")
    assert looks_role_like("Licensed Electrician needed")
    assert looks_role_like("Senior Accountant, full-time position")
    assert not looks_role_like("a personal blog post about my weekend")


def test_location_resolved_from_explicit_setting():
    loc = discovery_location({"job_location": "Berlin, Germany"}, {"s": "Nurse"})
    assert loc == "Berlin, Germany"


def test_location_resolved_from_profile_identity():
    # Just ingesting a CV with a city should drive regional discovery.
    loc = discovery_location({}, {"s": "Chef", "identity": {"city": "Lagos, Nigeria"}})
    assert loc == "Lagos, Nigeria"


def test_india_market_focus_backward_compatible():
    assert discovery_location({"job_market_focus": "india"}, {}) == "India"


def test_location_clause_targets_any_region():
    q = _location_clause('site:linkedin.com/jobs "nurse"', "Toronto", "any")
    assert "Toronto" in q
    remote = _location_clause('site:lever.co "designer"', "", "remote")
    assert "remote" in remote.lower()


def test_profile_for_discovery_carries_location_and_remote():
    d = profile_for_discovery(
        {"s": "Welder", "identity": {"city": "Houston"}},
        {"remote_preference": "onsite"},
    )
    assert d["_discovery_location"] == "Houston"
    assert d["_remote_preference"] == "onsite"


def test_x_queries_include_user_region():
    d = profile_for_discovery({"s": "Chef", "identity": {"city": "Lagos"}}, {})
    queries = profile_x_queries(d)
    assert "Lagos" in queries


_NURSE_CV = """Jane Smith
jane@example.com | Berlin, Germany

Summary
Registered Nurse with 6 years of ICU and acute care experience.

Skills
IV Therapy, ACLS, Patient Assessment, Wound Care, EHR Charting

Experience
Registered Nurse at City Hospital
Jan 2019 - Present
- Provided ICU patient care including IV therapy
- Performed patient assessment and wound care

Staff Nurse at Mercy Clinic
2016 - 2019
- Managed EHR charting and patient intake
"""


def test_deterministic_fallback_parses_non_tech_resume():
    # The no-LLM parser must capture non-tech roles/skills, not just software.
    from profile.ingest_parse import _parse_resume_heuristic

    p = _parse_resume_heuristic(_NURSE_CV)
    skill_names = {s.n.lower() for s in p.skills}
    assert "iv therapy" in skill_names
    roles = [e.role for e in p.exp]
    assert any("Registered Nurse" in r for r in roles)
    assert any("Staff Nurse" in r for r in roles)
    # Periods attach to the role, not parsed as separate phantom experiences.
    nurse_role = next(e for e in p.exp if "Registered Nurse" in e.role)
    assert "2019" in nurse_role.period
    # Per-role skills are matched from the candidate's own listed skills.
    assert any("iv therapy" in s.lower() for s in nurse_role.s)


def test_llm_fallback_returns_valid_model_not_broken_construct():
    # When the LLM is unavailable, the fallback must be a VALID model. A bare
    # model_construct() omits required fields and crashes downstream with
    # "'C' object has no attribute 'n'".
    from llm.client import _parse_fallback
    from models.schema import C

    fb = _parse_fallback("ignored", C)
    assert fb.n == ""          # accessible, not missing
    assert fb.skills == []
    assert fb.loc == ""


def test_deterministic_fallback_still_parses_tech_resume():
    from profile.ingest_parse import _parse_resume_heuristic

    cv = ("Alex Dev\n\nSkills\nPython, React, FastAPI\n\nExperience\n"
          "Senior Backend Engineer at Acme Corp\nJan 2020 - Present\n"
          "- Built Python and FastAPI services\n")
    p = _parse_resume_heuristic(cv)
    assert any("Backend Engineer" in e.role for e in p.exp)
    eng = next(e for e in p.exp if "Engineer" in e.role)
    assert eng.co == "Acme Corp"
    assert any("python" in s.lower() for s in eng.s)
