"""Tests for graph-enriched profile matching."""
from __future__ import annotations

from unittest.mock import patch


# ── Skill expansion ──────────────────────────────────────────────────────

def test_expanded_skills_with_evidence(monkeypatch):
    from ranking import graph_enrichment as ge

    monkeypatch.setattr(ge, "_direct_skills", lambda: {
        "s1": {"n": "Python", "cat": "language"},
        "s2": {"n": "React", "cat": "framework"},
    })
    monkeypatch.setattr(ge, "_project_skills", lambda: {
        "s1": {"MyApp", "DataPipe"},
    })
    monkeypatch.setattr(ge, "_experience_skills", lambda: {
        "s1": {"Engineer at Acme"},
        "s2": {"Frontend at Startup"},
    })
    monkeypatch.setattr(ge, "_related_skills", lambda: {
        "s1": ["Django", "FastAPI"],
    })

    skills = ge.expanded_skills()
    assert len(skills) == 2

    python_skill = next(s for s in skills if s["n"] == "Python")
    assert python_skill["evidence_score"] == 1.0  # 0.3 + 0.35 (proj) + 0.35 (exp)
    assert len(python_skill["evidence_sources"]) == 3  # 2 projects + 1 experience
    assert python_skill["related_skills"] == ["Django", "FastAPI"]

    react_skill = next(s for s in skills if s["n"] == "React")
    assert react_skill["evidence_score"] == 0.65  # 0.3 + 0.35 (exp only)


def test_expanded_skills_no_evidence(monkeypatch):
    from ranking import graph_enrichment as ge

    monkeypatch.setattr(ge, "_direct_skills", lambda: {
        "s1": {"n": "Go", "cat": "language"},
    })
    monkeypatch.setattr(ge, "_project_skills", lambda: {})
    monkeypatch.setattr(ge, "_experience_skills", lambda: {})
    monkeypatch.setattr(ge, "_related_skills", lambda: {})

    skills = ge.expanded_skills()
    assert len(skills) == 1
    assert skills[0]["evidence_score"] == 0.3  # Base score only


def test_expanded_skills_empty_graph(monkeypatch):
    from ranking import graph_enrichment as ge

    monkeypatch.setattr(ge, "_direct_skills", lambda: {})
    monkeypatch.setattr(ge, "_project_skills", lambda: {})
    monkeypatch.setattr(ge, "_experience_skills", lambda: {})
    monkeypatch.setattr(ge, "_related_skills", lambda: {})

    skills = ge.expanded_skills()
    assert skills == []


# ── Domain inference ─────────────────────────────────────────────────────

def test_infer_domains_from_experience(monkeypatch):
    from ranking import graph_enrichment as ge

    monkeypatch.setattr(ge, "_safe_query", lambda q, p=None: {
        "MATCH (c:Candidate)-[:WORKED_AS]->(e:Experience) RETURN e.role, e.co, e.d": [
            ["Software Engineer", "FinTech Corp", "Built trading platform for equities"],
            ["Senior Developer", "HealthTech Inc", "Patient data management system"],
        ],
        "MATCH (c:Candidate)-[:BUILT]->(p:Project) RETURN p.title, p.impact": [
            ["PaymentGateway", "Real-time payment processing"],
        ],
    }.get(q, []))

    domains = ge.infer_domains()
    domain_names = [d["domain"] for d in domains]
    assert "fintech" in domain_names
    assert "healthcare" in domain_names


def test_infer_domains_empty_graph(monkeypatch):
    from ranking import graph_enrichment as ge

    monkeypatch.setattr(ge, "_safe_query", lambda q, p=None: [])
    domains = ge.infer_domains()
    assert domains == []


# ── Graph-enriched profile ───────────────────────────────────────────────

def test_graph_enriched_profile_merges_skills(monkeypatch):
    from ranking import graph_enrichment as ge

    monkeypatch.setattr(ge, "expanded_skills", lambda: [
        {"id": "s1", "n": "Python", "cat": "language", "evidence_score": 1.0, "evidence_sources": ["project: X"], "related_skills": ["Django"]},
    ])
    monkeypatch.setattr(ge, "infer_domains", lambda: [
        {"domain": "fintech", "confidence": 0.8, "evidence_count": 2, "evidence": []},
    ])

    candidate = {
        "n": "Alice",
        "s": "Developer",
        "skills": [
            {"n": "Python", "cat": "language"},
            {"n": "SQL", "cat": "database"},
        ],
        "projects": [],
        "exp": [],
    }

    enriched = ge.graph_enriched_profile(candidate)
    assert enriched["_graph_enriched"] is True
    assert len(enriched["_domains"]) == 1
    assert enriched["_domains"][0]["domain"] == "fintech"

    # Python should be enriched, SQL should be preserved, Django should be expanded
    skill_names = [s["n"] for s in enriched["skills"]]
    assert "Python" in skill_names
    assert "SQL" in skill_names
    assert "Django" in skill_names

    # Check expansion skills
    assert len(enriched["_expansion_skills"]) == 1
    assert enriched["_expansion_skills"][0]["n"] == "Django"
    assert enriched["_expansion_skills"][0]["cat"] == "graph_related"


def test_graph_enriched_profile_fails_gracefully(monkeypatch):
    from ranking import graph_enrichment as ge

    monkeypatch.setattr(ge, "expanded_skills", lambda: (_ for _ in ()).throw(RuntimeError("graph down")))

    candidate = {"n": "Bob", "skills": [{"n": "Java"}]}
    result = ge.graph_enriched_profile(candidate)

    assert result["_graph_enriched"] is False
    assert result["n"] == "Bob"


def test_graph_enriched_profile_none_input():
    from ranking.graph_enrichment import graph_enriched_profile

    with patch("ranking.graph_enrichment.expanded_skills", return_value=[]), \
         patch("ranking.graph_enrichment.infer_domains", return_value=[]):
        result = graph_enriched_profile(None)
        assert result["_graph_enriched"] is False


# ── Enriched profile text ────────────────────────────────────────────────

def test_enriched_profile_text_includes_evidence():
    from ranking.graph_enrichment import enriched_profile_text

    enriched = {
        "n": "Alice",
        "s": "Full-stack developer",
        "_enriched_skills": [
            {"n": "Python", "evidence_score": 1.0, "evidence_sources": ["project: MyApp", "experience: Engineer at Acme"]},
            {"n": "SQL", "evidence_score": 0.3, "evidence_sources": []},
        ],
        "_expansion_skills": [
            {"n": "Django"},
        ],
        "_domain_text": "Domain experience: fintech (confidence: 0.8)",
        "projects": [{"title": "MyApp", "stack": ["Python", "React"], "impact": "10k users"}],
        "exp": [{"role": "Engineer", "co": "Acme", "period": "2020-2023", "d": "Built services"}],
    }

    text = enriched_profile_text(enriched)
    assert "Alice" in text
    assert "Strongly evidenced skills: Python" in text
    assert "Core skills: SQL" in text
    assert "Related/adjacent skills: Django" in text
    assert "fintech" in text
    assert "MyApp" in text


def test_enriched_profile_text_empty_enriched():
    from ranking.graph_enrichment import enriched_profile_text

    text = enriched_profile_text({})
    assert isinstance(text, str)


# ── Semantic.py integration ──────────────────────────────────────────────

def test_is_semantic_provider():
    from ranking.semantic import _is_semantic_provider

    assert _is_semantic_provider("onnx") is True
    assert _is_semantic_provider("openai") is True
    assert _is_semantic_provider("sentence-transformer") is True
    assert _is_semantic_provider("hashing") is False
    assert _is_semantic_provider("") is False
    assert _is_semantic_provider("lazy") is False


def test_graph_busy_error_is_raised_on_lock_timeout():
    """GraphBusyError should be a RuntimeError subclass for backward compat."""
    from data.graph.connection import GraphBusyError

    assert issubclass(GraphBusyError, RuntimeError)
    exc = GraphBusyError("test timeout")
    assert str(exc) == "test timeout"


def test_safe_execute_catches_graph_busy(monkeypatch):
    """_safe_execute in profile.py must catch GraphBusyError and return None."""
    from data.graph import profile as gp
    from data.graph.connection import GraphBusyError

    def raise_busy(query, params=None):
        raise GraphBusyError("lock timed out")

    from data.graph import profile_base

    monkeypatch.setattr(profile_base, "execute_query", raise_busy)
    result = gp._safe_execute("MATCH (n) RETURN n")
    assert result is None


def test_local_profile_rows_with_graph_enrichment(monkeypatch):
    from ranking import semantic

    # Mock graph enrichment to add domain context
    def mock_enrich(data):
        return {**data, "_graph_enriched": True, "_domain_text": "Domain: fintech"}

    monkeypatch.setattr(semantic, "_try_graph_enrich", mock_enrich)

    candidate = {
        "n": "Alice",
        "s": "Developer",
        "skills": [{"n": "Python", "cat": "language"}],
        "projects": [],
        "exp": [],
    }

    rows = semantic._local_profile_rows(candidate)
    profile_row = next(r for r in rows if r["kind"] == "profile")
    assert "fintech" in profile_row["text"]
