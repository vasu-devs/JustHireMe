"""Off-field pre-filter: the evaluator must NOT spend an LLM call on a lead the
cheap deterministic pass already ruled off-field for this candidate (a sales role
for an AI engineer, etc.). The wrong-field cap (15) is a hard ceiling the LLM
can't lift, so evaluating it only burns tokens — the exact waste that drained the
user's subscription.
"""

from __future__ import annotations

from ranking import evaluator as ev

_AI_PROFILE = {
    "n": "Asha", "s": "AI / ML engineer — LLMs, Python, RAG",
    "skills": [{"n": s} for s in ["Python", "PyTorch", "LangChain", "RAG", "FastAPI"]],
    "exp": [{"role": "AI Engineer", "co": "X", "d": "LLM pipelines", "s": ["Python"]}],
    "projects": [{"title": "Vaani", "stack": ["Python", "LangChain"], "impact": "voice AI"}],
}
_LLM_SETTINGS = {"evaluator_provider": "codex_cli"}


def test_off_field_prefilter_flags_wrong_field_only():
    assert ev._off_field_prefilter({"gaps": ["wrong-field cap: not technical"]}, {}) is True
    assert ev._off_field_prefilter({"gaps": ["stack cap: no exact evidence"]}, {}) is False
    assert ev._off_field_prefilter({"gaps": []}, {}) is False


def test_prefilter_can_be_disabled():
    base = {"gaps": ["wrong-field cap: x"]}
    assert ev._off_field_prefilter(base, {"prefilter_off_field": "false"}) is False
    assert ev._off_field_prefilter(base, {"prefilter_off_field": "true"}) is True


def test_score_skips_llm_for_off_field(monkeypatch):
    monkeypatch.setattr(ev, "_evaluator_llm_requested", lambda settings=None: True)
    calls = {"n": 0}

    def _must_not_run(*a, **k):
        calls["n"] += 1
        return {"score": 99, "reason": "ran", "scored_by": "llm", "match_points": [], "gaps": []}

    monkeypatch.setattr(ev, "_score_with_llm", _must_not_run)
    out = ev.score("Enterprise Sales Executive. Quota, CRM, cold calls, close deals.", _AI_PROFILE, _LLM_SETTINGS)
    assert out["scored_by"] == "prefiltered_off_field"
    assert out["score"] <= 15
    assert calls["n"] == 0, "the LLM must not be called for an off-field lead"
    assert "off-field" in out["reason"].lower()


def test_score_runs_llm_for_on_field(monkeypatch):
    monkeypatch.setattr(ev, "_evaluator_llm_requested", lambda settings=None: True)
    calls = {"n": 0}

    def _llm(jd, candidate_data, baseline, preferences=""):
        calls["n"] += 1
        return {**baseline, "score": 80, "reason": "good", "scored_by": "llm"}

    monkeypatch.setattr(ev, "_score_with_llm", _llm)
    out = ev.score("Senior AI Engineer. Python, PyTorch, LangChain, RAG, vector DBs.", _AI_PROFILE, _LLM_SETTINGS)
    assert calls["n"] == 1, "an on-field lead must still get the full evaluation"
    assert out["scored_by"] == "llm"
