"""Content-based feedback for the MATCH score: liked-like jobs get a positive delta,
opposite jobs a negative one, and it's inert without real embeddings."""

from __future__ import annotations

from unittest import mock

import data.vector.embeddings as emb
from ranking import feedback_semantic as fs

_EXAMPLES = [{"title": "ICU Nurse", "description": "critical care", "feedback": "good"}]
_LEADS = [
    {"job_id": "like", "title": "Staff Nurse", "description": "icu unit"},
    {"job_id": "ortho", "title": "Chef", "description": "kitchen"},
    {"job_id": "anti", "title": "Something", "description": "else"},
]
# example(good)=[1,0]; like aligns, ortho orthogonal, anti opposite.
_VECS = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]


def test_preference_deltas_direction():
    with mock.patch.object(emb, "active_provider", return_value="onnx"), \
         mock.patch.object(emb, "embed_texts", return_value=_VECS):
        deltas = fs.preference_deltas(_EXAMPLES, _LEADS, max_delta=12)
    assert deltas.get("like", 0) > 0, deltas
    assert deltas.get("anti", 0) < 0, deltas
    assert "ortho" not in deltas  # orthogonal -> 0 delta, omitted
    assert abs(deltas["like"]) <= 12 and abs(deltas["anti"]) <= 12  # bounded


def test_preference_deltas_inert_without_real_embeddings():
    with mock.patch.object(emb, "active_provider", return_value="hash"), \
         mock.patch.object(emb, "embed_texts") as embed:
        assert fs.preference_deltas(_EXAMPLES, _LEADS) == {}
    embed.assert_not_called()


def test_preference_deltas_no_polarised_feedback():
    neutral = [{"title": "X", "description": "y", "feedback": ""}]
    with mock.patch.object(emb, "active_provider", return_value="onnx"), \
         mock.patch.object(emb, "embed_texts") as embed:
        assert fs.preference_deltas(neutral, _LEADS) == {}
    embed.assert_not_called()
