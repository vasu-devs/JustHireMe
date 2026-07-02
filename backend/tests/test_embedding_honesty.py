"""A runtime OpenAI embedding failure must be reported honestly, not as healthy.

Before the fix, embed_texts silently fell back to hash while active_provider()/
embedding_status() kept reporting 'openai', so semantic scoring applied the wide
'real embeddings' stretch to hash vectors and /diagnostics looked healthy.
"""

from __future__ import annotations

import data.vector.embeddings as emb


def test_openai_runtime_failure_reports_hashing_then_recovers(monkeypatch):
    monkeypatch.setattr(emb, "_configured_provider", lambda: "openai")
    monkeypatch.setattr(emb, "_openai_api_key", lambda: "sk-test-key")

    def boom(_texts):
        raise RuntimeError("network down")

    monkeypatch.setattr(emb, "_openai_embed", boom)
    emb._openai_runtime_error = ""  # clean start
    try:
        vecs = emb.embed_texts(["hello world"])
        # Fallback hash must be at the OpenAI dim so it doesn't corrupt the table.
        assert len(vecs) == 1 and len(vecs[0]) == emb.OPENAI_DIMS

        status = emb.embedding_status()
        assert status["mode"] == "hashing", status
        assert status.get("degraded") is True
        assert "openai_error" in status

        # A subsequent SUCCESS clears the degraded state (self-healing).
        monkeypatch.setattr(emb, "_openai_embed", lambda texts: [[0.0] * emb.OPENAI_DIMS for _ in texts])
        emb.embed_texts(["ok now"])
        assert emb.embedding_status()["mode"] == "openai"
        assert emb.embedding_status().get("degraded") is not True
    finally:
        emb._openai_runtime_error = ""


def test_onnx_runtime_failure_reports_hashing_then_recovers(monkeypatch):
    # ONNX session loaded but inference fails at runtime -> falls back to hash; status
    # must report it (parallel to the openai case), not keep claiming 'onnx'.
    monkeypatch.setattr(emb, "_configured_provider", lambda: "onnx")
    monkeypatch.setattr(emb, "active_provider", lambda: "onnx")

    def boom(_texts):
        raise RuntimeError("ORT inference error")

    monkeypatch.setattr(emb, "_onnx_embed", boom)
    emb._onnx_runtime_error = ""
    try:
        vecs = emb.embed_texts(["hello"])
        assert len(vecs[0]) == emb.ONNX_DIMS

        status = emb.embedding_status()
        assert status["mode"] == "hashing", status
        assert status.get("degraded") is True

        monkeypatch.setattr(emb, "_onnx_embed", lambda texts: [[0.0] * emb.ONNX_DIMS for _ in texts])
        emb.embed_texts(["ok now"])
        assert emb.embedding_status()["mode"] == "onnx"
    finally:
        emb._onnx_runtime_error = ""
