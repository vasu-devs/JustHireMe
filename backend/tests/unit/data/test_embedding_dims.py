"""Embedding dimensionality stays consistent with the active provider (Tier-1).

Bug: when OpenAI (1536-dim) failed mid-session, embed_texts fell back to a
384-dim hash vector, which poisons / gets dropped from a 1536-dim table. The
fallback (and a defensive response check) now keep the provider's dimension.
"""
import data.vector.embeddings as emb


def _raise(*_a, **_k):
    raise RuntimeError("provider down")


def test_hash_embedding_respects_dims():
    assert len(emb.hash_embedding("python react fastapi", 1536)) == 1536
    assert len(emb.hash_embedding("python react fastapi", 384)) == 384


def test_openai_fallback_keeps_1536(monkeypatch):
    monkeypatch.setattr(emb, "active_provider", lambda: "openai")
    monkeypatch.setattr(emb, "_openai_embed", _raise)
    vecs = emb.embed_texts(["hello", "world"])
    assert len(vecs) == 2
    assert all(len(v) == emb.OPENAI_DIMS for v in vecs), "fallback must match OpenAI dim, not 384"


def test_openai_off_dimension_response_is_rejected(monkeypatch):
    # API returns a wrong-width vector -> treat as failure -> hash@1536, not the bad dim.
    monkeypatch.setattr(emb, "active_provider", lambda: "openai")
    monkeypatch.setattr(emb, "_openai_embed", lambda texts: [[0.0] * 384 for _ in texts])
    vecs = emb.embed_texts(["x"])
    assert len(vecs[0]) == emb.OPENAI_DIMS


def test_openai_success_passes_through(monkeypatch):
    monkeypatch.setattr(emb, "active_provider", lambda: "openai")
    monkeypatch.setattr(emb, "_openai_embed", lambda texts: [[0.1] * emb.OPENAI_DIMS for _ in texts])
    vecs = emb.embed_texts(["x", "y"])
    assert len(vecs) == 2 and all(len(v) == emb.OPENAI_DIMS for v in vecs)


def test_onnx_fallback_keeps_384(monkeypatch):
    monkeypatch.setattr(emb, "active_provider", lambda: "onnx")
    monkeypatch.setattr(emb, "_onnx_embed", _raise)
    vecs = emb.embed_texts(["a"])
    assert len(vecs[0]) == emb.ONNX_DIMS


def test_hash_provider_dims(monkeypatch):
    monkeypatch.setattr(emb, "active_provider", lambda: "hash")
    vecs = emb.embed_texts(["a", "b"])
    assert all(len(v) == emb.HASH_DIMS for v in vecs)


def test_incoming_vector_dim_helper():
    from data.graph.profile_vectors import _incoming_vector_dim
    assert _incoming_vector_dim([{"id": "x", "vector": [0.0] * 1536}]) == 1536
    assert _incoming_vector_dim([{"id": "x"}]) is None
    assert _incoming_vector_dim([]) is None
