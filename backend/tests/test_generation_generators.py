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
