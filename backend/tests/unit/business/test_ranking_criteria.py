from ranking.criteria import DEFAULT_CRITERIA, criteria_by_key, criteria_by_name
from ranking.scoring_engine import ScoringEngine, score_job_lead


def test_default_criteria_registry_matches_roadmap():
    keys = [criterion.key for criterion in DEFAULT_CRITERIA]
    weights = {criterion.key: criterion.max_weight for criterion in DEFAULT_CRITERIA}

    assert keys == [
        "role_alignment",
        "stack_coverage",
        "evidence",
        "seniority_fit",
        "logistics",
        "learning_curve",
    ]
    assert weights == {
        "role_alignment": 15,
        "stack_coverage": 22,
        "evidence": 20,
        "seniority_fit": 25,
        "logistics": 13,
        "learning_curve": 5,
    }
    assert criteria_by_key()["stack_coverage"].name == "Stack overlap"
    assert criteria_by_name()["Proof of work"].key == "evidence"


def test_wrong_field_cap_message_is_candidate_relative_for_semantic_trigger():
    from ranking.scoring_engine import _apply_caps, analyze_candidate, analyze_posting

    posting = analyze_posting("Job Title: Financial Analyst\nDescription: Build budget models and quarterly forecasts.")
    candidate = analyze_candidate({"skills": [{"n": "IV Therapy"}], "exp": [], "projects": []})
    posting.wrong_field = True
    posting.wrong_field_semantic = True

    _final, notes, cap, kinds = _apply_caps(50, posting, candidate, set(), set())
    assert cap == 15
    assert kinds[0] == "wrong-field"
    assert "different profession than this profile" in notes[0]

    # Blocklist trigger keeps the tech-specific wording.
    posting.wrong_field_semantic = False
    _final, notes, _cap, _kinds = _apply_caps(50, posting, candidate, set(), set())
    assert "not a technical/software opportunity" in notes[0]


def test_score_result_carries_structural_cap_kinds():
    result = score_job_lead(
        "Job Title: Registered Nurse\nDescription: ICU nurse needed for patient care.",
        {"s": "Software engineer", "skills": [{"n": "Python"}], "exp": [], "projects": []},
    )
    assert "wrong-field" in result.cap_kinds
    assert result.as_dict()["cap_kinds"] == result.cap_kinds


def test_scoring_engine_facade_matches_function():
    jd = "Job Title: Junior Python Engineer\nDescription: Build FastAPI services with React dashboards."
    profile = {
        "s": "Junior Python developer",
        "skills": [{"n": "Python"}, {"n": "FastAPI"}, {"n": "React"}],
        "projects": [{"title": "API Dashboard", "stack": ["Python", "FastAPI", "React"], "impact": "Built dashboards"}],
        "exp": [],
    }

    direct = score_job_lead(jd, profile)
    via_engine = ScoringEngine().score(jd, profile)

    assert via_engine.score == direct.score
    assert via_engine.reason == direct.reason
