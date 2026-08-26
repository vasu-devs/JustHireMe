from __future__ import annotations

from generation.generators.cover_letter import CoverLetterGenerator
from generation.generators.founder_message import FounderMessageGenerator
from generation.generators.keywords import KeywordsGenerator
from generation.generators.linkedin_message import LinkedInMessageGenerator
from generation.generators.outreach_email import OutreachEmailGenerator
from generation.generators.resume import ResumeGenerator


def test_generation_generators_expose_expected_assets():
    profile = {
        "candidate": {"name": "Vasu", "summary": "Builds AI products."},
        "skills": [{"n": "FastAPI"}, {"n": "React"}],
        "projects": [{"title": "Agent CRM", "stack": ["FastAPI", "React"], "impact": "Shipped workflows."}],
    }
    lead = {
        "title": "AI Engineer",
        "company": "Acme",
        "description": "Build FastAPI and React AI workflows.",
    }

    assert ResumeGenerator().generate(lead, profile)["text"]
    assert CoverLetterGenerator().generate(lead, profile)["text"]
    assert FounderMessageGenerator().generate(lead, profile)["text"]
    assert LinkedInMessageGenerator().generate(lead, profile)["text"]
    assert OutreachEmailGenerator().generate(lead, profile)["text"]
    assert KeywordsGenerator().generate(lead, profile)["metadata"]["jd_terms"]


def test_resume_fallback_prioritizes_jd_keywords_and_evidence():
    from generation.generators.resume import _fallback_package

    profile = {
        "n": "Vasu DevS",
        "s": "Full-stack AI engineer building local-first agents and production React/FastAPI systems.",
        "skills": [
            {"n": "Python", "cat": "technical"},
            {"n": "FastAPI", "cat": "technical"},
            {"n": "React", "cat": "technical"},
            {"n": "PostgreSQL", "cat": "technical"},
            {"n": "Docker", "cat": "technical"},
            {"n": "LangGraph", "cat": "technical"},
            {"n": "RAG", "cat": "technical"},
        ],
        "projects": [{
            "title": "JustHireMe",
            "stack": ["React", "FastAPI", "PostgreSQL", "LangGraph"],
            "impact": "Built a local-first AI job intelligence workbench with graph ranking and resume generation.",
        }],
        "exp": [],
    }
    lead = {
        "title": "Applied AI Engineer",
        "company": "Acme AI",
        "description": "Build Python, FastAPI, React, PostgreSQL, Docker, RAG, and LangGraph workflow automation.",
    }

    resume = _fallback_package(profile, lead).resume_markdown

    assert "## SUMMARY" in resume
    assert "**Languages:** Python" in resume
    assert "**Frameworks & Libraries:** FastAPI, React, LangGraph" in resume
    assert "**Databases & Data Tools:** PostgreSQL" in resume
    assert "**Tools & Platforms:** Docker" in resume
    assert "JustHireMe" in resume
    assert "RAG" in resume


def test_resume_fallback_scrubs_contact_summary_and_project_noise():
    from generation.generators.resume import _fallback_package

    profile = {
        "n": "Casey Example",
        "s": (
            "Email: casey@example.test. Phone: +1 555 010 0001. "
            "Links: https://github.com/example-candidate/Vanta, https://github.com/example-candidate/SOMA"
        ),
        "identity": {
            "email": "casey@example.test",
            "github_url": "https://github.com/example-candidate",
        },
        "skills": [{"n": "Python", "cat": "language"}, {"n": "FastAPI", "cat": "framework"}, {"n": "React", "cat": "framework"}],
        "projects": [
            {"title": "conditioning.", "stack": ["FastAPI"], "repo": "https://github.com/example-candidate/Vanta", "impact": "Deployed FastAPI backend."},
            {"title": "Vanta", "stack": ["FastAPI", "React"], "repo": "https://github.com/example-candidate/Vanta", "impact": "Deployed backend and frontend for an AI application."},
        ],
        "exp": [],
        "certifications": ["Social Networks - NPTEL Jan 2025 - Apr 2025", "Certificate Link"],
    }
    lead = {
        "title": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
        "company": "Wellfound",
        "url": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
        "description": "AI research intern role using Python and FastAPI for data science workflows.",
    }

    resume = _fallback_package(profile, lead).resume_markdown
    summary = resume.split("## SUMMARY", 1)[1].split("## SKILLS", 1)[0]

    assert "Email:" not in summary
    assert "Phone:" not in summary
    assert "Links:" not in summary
    assert "wellfound.com/jobs" not in summary
    assert "Targeting" not in summary
    assert "### Vanta - FastAPI, React" in resume
    assert "conditioning" not in resume
    assert "Applied FastAPI" not in resume
    assert "Certificate Link" not in resume
