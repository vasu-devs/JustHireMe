from __future__ import annotations

import itertools
import random


TECH_STACKS = [
    ("Frontend Engineer", ["React", "TypeScript", "Node.js"]),
    ("Backend Engineer", ["Python", "FastAPI", "PostgreSQL"]),
    ("Applied AI Engineer", ["Python", "LLM", "RAG", "LangGraph"]),
    ("DevOps Engineer", ["Docker", "Kubernetes", "AWS"]),
]


def _profile(stack: list[str], *, period: str = "", role: str = "Software Engineer") -> dict:
    profile = {
        "n": "Candidate",
        "s": f"{role} with shipped work in {', '.join(stack)}.",
        "skills": [{"n": term} for term in stack],
        "projects": [
            {
                "title": f"{stack[0]} Platform",
                "stack": stack,
                "impact": f"Built production workflows using {', '.join(stack)}.",
            },
            {
                "title": f"{stack[-1]} Automation",
                "stack": stack,
                "impact": "Shipped reliable internal automation with measurable usage.",
            },
        ],
        "exp": [],
    }
    if period:
        profile["exp"] = [{
            "role": role,
            "co": "Acme",
            "period": period,
            "s": stack,
            "d": f"Built and maintained systems using {', '.join(stack)}.",
        }]
    return profile


def _job(role: str, stack: list[str], *, years: int = 0, extra: str = "") -> str:
    requirement = f" Requires {years}+ years of professional experience." if years else ""
    return (
        f"Job Title: {role}\n"
        "Company: NimbusWorks\n"
        f"Description: We are hiring for production software work with {', '.join(stack)}."
        f"{requirement} Remote role with clear apply process. {extra}"
    )


def _score(job: str, profile: dict, monkeypatch) -> int:
    import ranking.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_semantic_criterion", lambda *_args, **_kwargs: None)
    return scoring_engine.ScoringEngine().score(job, profile).score


def test_scoring_engine_scores_are_always_bounded_for_generated_inputs(monkeypatch):
    rng = random.Random(104729)
    roles = [role for role, _stack in TECH_STACKS]
    stacks = [stack for _role, stack in TECH_STACKS]
    periods = ["", "Jan 2025 to Dec 2025", "Jan 2024 to Dec 2025", "Jan 2020 to Dec 2025"]

    for index in range(120):
        role = rng.choice(roles)
        job_stack = rng.choice(stacks)
        profile_stack = rng.choice(stacks)
        years = rng.choice([0, 1, 2, 3, 5, 7])
        period = rng.choice(periods)

        score = _score(_job(role, job_stack, years=years), _profile(profile_stack, period=period), monkeypatch)

        assert isinstance(score, int), f"score #{index} should be an int"
        assert 0 <= score <= 100, f"score #{index} was out of range: {score}"


def test_seniority_caps_hold_across_generated_stacks(monkeypatch):
    for role, stack in TECH_STACKS:
        zero_experience = _profile(stack)
        one_year = _profile(stack, period="Jan 2025 to Dec 2025")
        two_years = _profile(stack, period="Jan 2024 to Dec 2025")

        assert _score(_job(f"Senior {role}", stack, years=3), zero_experience, monkeypatch) <= 30
        assert _score(_job(f"Lead {role}", stack, years=5), zero_experience, monkeypatch) <= 30
        assert _score(_job(role, stack, years=3), one_year, monkeypatch) <= 45
        assert _score(_job(role, stack, years=5), one_year, monkeypatch) <= 38
        assert _score(_job(role, stack, years=7), two_years, monkeypatch) <= 48


def test_wrong_field_and_thin_posting_caps_hold_for_many_profiles(monkeypatch):
    wrong_field_jobs = [
        "Job Title: Registered Nurse\nDescription: Patient care, triage, and clinic support.",
        "Job Title: Marketing Manager\nDescription: SEO campaigns, copywriting, social media, and brand planning.",
        "Job Title: Embedded Systems Engineer\nDescription: RTOS, ARM Cortex, CAN bus, and AUTOSAR firmware.",
        "Job Title: Accountant\nDescription: Tax preparation, bookkeeping, audits, and monthly close.",
    ]

    for wrong_job, (_role, stack) in itertools.product(wrong_field_jobs, TECH_STACKS):
        assert _score(wrong_job, _profile(stack, period="Jan 2020 to Dec 2025"), monkeypatch) <= 15

    for role, stack in TECH_STACKS:
        assert _score(f"Job Title: {role}\nDescription: Nice team.", _profile(stack), monkeypatch) <= 68


def test_marketing_title_cannot_be_laundered_by_ai_body_copy(monkeypatch):
    profile = _profile(
        ["Python", "FastAPI", "LLM", "RAG", "TypeScript"],
        period="Jun 2026 - Present",
        role="AI Engineer",
    )
    job = (
        "Job Title: Senior Account Based Marketing Manager\n"
        "Company: Dropbox\n"
        "Description: Own ABM campaigns, account personalization, digital advertising, "
        "sales outreach, pipeline creation, and marketing analytics. Requires 6+ years "
        "of B2B marketing experience. Use generative AI tools for campaign research and "
        "support GTM motions for AI products. Remote role."
    )

    import ranking.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_semantic_criterion", lambda *_args, **_kwargs: None)
    result = scoring_engine.ScoringEngine().score(job, profile)

    assert result.score <= 15
    assert "wrong-field" in result.cap_kinds
    assert any("different occupation" in gap or "wrong-field cap" in gap for gap in result.gaps)


def test_non_technical_title_cannot_be_laundered_by_technical_modifiers(monkeypatch):
    profile = _profile(
        ["Python", "FastAPI", "LLM", "RAG", "TypeScript"],
        period="Jun 2026 - Present",
        role="AI Engineer",
    )
    import ranking.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_semantic_criterion", lambda *_args, **_kwargs: None)
    for title in (
        "Generative AI Marketing Manager",
        "Python Marketing Manager",
        "Machine Learning Content Writer",
    ):
        result = scoring_engine.ScoringEngine().score(
            f"Job Title: {title}\nDescription: Own campaigns and content using AI tools.",
            profile,
        )
        assert result.score <= 15, title
        assert "wrong-field" in result.cap_kinds, title


def test_non_technical_title_is_cleared_for_a_genuine_same_field_candidate(monkeypatch):
    profile = {
        "s": "Growth marketer with 4 years in B2B demand generation.",
        "skills": [
            {"n": "Account Based Marketing"},
            {"n": "Demand Generation"},
            {"n": "Campaign Strategy"},
            {"n": "Google Analytics"},
        ],
        "exp": [{
            "role": "Growth Marketing Specialist",
            "co": "SaaSCo",
            "period": "Jan 2022 - Present",
            "d": "Owned account based marketing, demand generation, campaign strategy, and analytics.",
        }],
    }
    job = (
        "Job Title: Account Based Marketing Manager\n"
        "Description: Own account based marketing, demand generation, campaign strategy, "
        "and Google Analytics. 3+ years."
    )

    import ranking.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_semantic_criterion", lambda *_args, **_kwargs: None)
    result = scoring_engine.ScoringEngine().score(job, profile)

    assert result.score > 15
    assert "wrong-field" not in result.cap_kinds


def test_one_incidental_domain_phrase_cannot_clear_a_non_technical_title(monkeypatch):
    profile = _profile(
        ["Python", "FastAPI", "LLM", "RAG", "TypeScript"],
        period="Jun 2026 - Present",
        role="AI Engineer",
    )
    profile["skills"].append({"n": "GTM Strategy"})
    job = (
        "Job Title: Generative AI Marketing Manager\n"
        "Description: Own campaigns and GTM strategy using generative AI tools."
    )

    import ranking.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_semantic_criterion", lambda *_args, **_kwargs: None)
    result = scoring_engine.ScoringEngine().score(job, profile)

    assert result.score <= 15
    assert "wrong-field" in result.cap_kinds


def test_responsibility_words_do_not_fabricate_seniority_requirements(monkeypatch):
    profile = {
        "s": "Software engineer",
        "skills": [{"n": "Python"}, {"n": "FastAPI"}],
        "exp": [
            {"role": "Software Engineer", "co": "A", "period": "Jan 2025 - Sep 2025", "d": "Built APIs"},
            {"role": "Backend Engineer", "co": "B", "period": "Oct 2025 - Jun 2026", "d": "Built services"},
        ],
        "projects": [{"title": "API", "stack": ["Python", "FastAPI"], "impact": "Shipped an API"}],
    }
    import ranking.scoring_engine as scoring_engine

    monkeypatch.setattr(scoring_engine, "_semantic_criterion", lambda *_args, **_kwargs: None)
    for description in (
        "Build Python and FastAPI services. Interview with the hiring manager.",
        "Build Python and FastAPI services and lead API design.",
    ):
        result = scoring_engine.ScoringEngine().score(
            f"Job Title: Software Engineer\nDescription: {description}", profile
        )
        assert "seniority" not in result.cap_kinds, description


def test_stack_caps_hold_when_exact_requested_terms_are_missing(monkeypatch):
    profile = _profile(["React", "TypeScript", "Node.js"], period="Jan 2020 to Dec 2025")
    adjacent_miss_jobs = [
        _job("Backend Engineer", ["Python", "FastAPI", "PostgreSQL"]),
        _job("Mobile Engineer", ["Swift", "iOS", "Firebase"]),
    ]

    for job in adjacent_miss_jobs:
        assert _score(job, profile, monkeypatch) <= 52

    unrelated_enterprise_job = _job("Enterprise Engineer", ["SAP", "ABAP", "ServiceNow"])
    assert _score(unrelated_enterprise_job, profile, monkeypatch) <= 42
