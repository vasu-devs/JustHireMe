"""The symmetric semantic off-field gate: a low candidate-vs-JD similarity caps a
posting as off-field for ANY field pair (not just the tech blocklist), and never
fires when real embeddings are unavailable."""

from __future__ import annotations

from ranking import scoring_engine as se

_NURSE = {
    "n": "Jane",
    "s": "Registered Nurse, ICU, 6 years critical care",
    "skills": [{"n": "patient care"}, {"n": "IV therapy"}, {"n": "ACLS"}],
    "exp": [{"role": "ICU Staff Nurse", "co": "Mercy"}],
    "certifications": ["RN", "BLS"],
}
# A field no blocklist enumerates for a nurse — must still be caught semantically.
_FINANCE_JD = ("Financial Analyst at BankCo. Financial modeling, investment analysis, "
               "Excel, forecasting, budgeting, variance analysis, quarterly reporting.")


def test_low_similarity_caps_unblocklisted_off_field(monkeypatch):
    monkeypatch.setattr(se, "_semantic_field_similarity", lambda cand, jd: 0.10)
    capped = se.score_job_lead(_FINANCE_JD, _NURSE).score

    monkeypatch.setattr(se, "_semantic_field_similarity", lambda cand, jd: 0.60)
    uncapped = se.score_job_lead(_FINANCE_JD, _NURSE).score

    assert capped < uncapped, (capped, uncapped)
    assert capped <= 25, capped  # hard off-field cap engaged


def test_gate_is_inert_without_real_embeddings(monkeypatch):
    # Hash mode -> similarity is None -> the gate must NOT change the outcome.
    monkeypatch.setattr(se, "_semantic_field_similarity", lambda cand, jd: None)
    none_score = se.score_job_lead(_FINANCE_JD, _NURSE).score
    monkeypatch.setattr(se, "_semantic_field_similarity", lambda cand, jd: 0.60)
    high_sim_score = se.score_job_lead(_FINANCE_JD, _NURSE).score
    # A None (unavailable) result behaves like a non-off-field high-sim result here:
    # neither imposes the off-field cap, so scores match.
    assert none_score == high_sim_score


def test_field_vector_returns_none_under_hash(monkeypatch):
    import data.vector.embeddings as emb
    monkeypatch.setattr(emb, "active_provider", lambda: "hash")
    se._field_vector.cache_clear()
    assert se._field_vector("registered nurse icu critical care unit") is None
