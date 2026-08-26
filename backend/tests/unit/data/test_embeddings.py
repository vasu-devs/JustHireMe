"""Tests for the three-tier embedding system."""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch


# ── Tier 3: hash embedding (always works) ────────────────────────────────

def test_hash_embedding_returns_correct_dims():
    from data.vector.embeddings import hash_embedding

    vec = hash_embedding("python developer")
    assert len(vec) == 384


def test_hash_embedding_is_normalized():
    from data.vector.embeddings import hash_embedding

    vec = hash_embedding("react typescript node")
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-6


def test_hash_embedding_deterministic():
    from data.vector.embeddings import hash_embedding

    a = hash_embedding("machine learning engineer")
    b = hash_embedding("machine learning engineer")
    assert a == b


def test_hash_embedding_different_inputs_differ():
    from data.vector.embeddings import hash_embedding

    a = hash_embedding("python developer")
    b = hash_embedding("java architect")
    assert a != b


def test_hash_embedding_empty_string():
    from data.vector.embeddings import hash_embedding

    vec = hash_embedding("")
    assert len(vec) == 384
    # All zeros normalized → uniform or zero
    assert all(isinstance(v, float) for v in vec)


def test_hash_embedding_custom_dims():
    from data.vector.embeddings import hash_embedding

    vec = hash_embedding("test", dims=128)
    assert len(vec) == 128


# ── Provider selection ───────────────────────────────────────────────────

def test_configured_provider_defaults_to_onnx(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "onnx")
    monkeypatch.setattr(embeddings, "_load_onnx_session", lambda: False)
    # ONNX not loaded → falls back to hash
    provider = embeddings.active_provider()
    assert provider == "hash"


def test_configured_provider_openai_without_key(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "openai")
    monkeypatch.setattr(embeddings, "_openai_api_key", lambda: None)
    monkeypatch.setattr(embeddings, "_load_onnx_session", lambda: False)
    provider = embeddings.active_provider()
    assert provider == "hash"


def test_configured_provider_openai_with_key(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "openai")
    monkeypatch.setattr(embeddings, "_openai_api_key", lambda: "sk-test-key")
    provider = embeddings.active_provider()
    assert provider == "openai"


def test_configured_provider_hash(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "hash")
    provider = embeddings.active_provider()
    assert provider == "hash"


def test_configured_provider_onnx_loaded(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "onnx")
    monkeypatch.setattr(embeddings, "_load_onnx_session", lambda: True)
    provider = embeddings.active_provider()
    assert provider == "onnx"


# ── embed_texts fallback behavior ────────────────────────────────────────

def test_embed_texts_falls_back_to_hash_on_onnx_failure(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "active_provider", lambda: "onnx")
    monkeypatch.setattr(embeddings, "_onnx_embed", lambda texts: (_ for _ in ()).throw(RuntimeError("ONNX failed")))

    result = embeddings.embed_texts(["test text"])
    assert len(result) == 1
    assert len(result[0]) == 384  # hash dims


def test_embed_texts_falls_back_to_hash_on_openai_failure(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "active_provider", lambda: "openai")
    monkeypatch.setattr(embeddings, "_openai_embed", lambda texts: (_ for _ in ()).throw(RuntimeError("API error")))

    result = embeddings.embed_texts(["test text"])
    assert len(result) == 1
    # The OpenAI table is 1536-wide, so the hash fallback must also be 1536 — a
    # 384-dim fallback here would corrupt/drop into that table (Tier-1 fix).
    assert len(result[0]) == embeddings.OPENAI_DIMS


def test_embed_texts_hash_mode(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "active_provider", lambda: "hash")
    result = embeddings.embed_texts(["python", "java"])
    assert len(result) == 2
    assert len(result[0]) == 384
    assert len(result[1]) == 384


def test_embed_texts_empty_list():
    from data.vector.embeddings import embed_texts

    result = embed_texts([])
    assert result == []


# ── embedding_status ─────────────────────────────────────────────────────

def test_embedding_status_hash_mode(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "active_provider", lambda: "hash")
    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "hash")

    status = embeddings.embedding_status()
    assert status["mode"] == "hashing"
    assert status["active_provider"] == "hash"
    assert status["dims"] == 384


def test_embedding_status_onnx_mode(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "active_provider", lambda: "onnx")
    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "onnx")

    status = embeddings.embedding_status()
    assert status["mode"] == "onnx"
    assert status["dims"] == 384


def test_embedding_status_openai_mode(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "active_provider", lambda: "openai")
    monkeypatch.setattr(embeddings, "_configured_provider", lambda: "openai")

    status = embeddings.embedding_status()
    assert status["mode"] == "openai"
    assert status["dims"] == 1536


# ── embedding_dims ───────────────────────────────────────────────────────

def test_embedding_dims_by_provider(monkeypatch):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "active_provider", lambda: "hash")
    assert embeddings.embedding_dims() == 384

    monkeypatch.setattr(embeddings, "active_provider", lambda: "onnx")
    assert embeddings.embedding_dims() == 384

    monkeypatch.setattr(embeddings, "active_provider", lambda: "openai")
    assert embeddings.embedding_dims() == 1536


# ── reset_onnx_session ──────────────────────────────────────────────────

def test_reset_onnx_session():
    from data.vector import embeddings

    # Set some state
    embeddings._onnx_loaded = True
    embeddings._onnx_error = "test error"

    embeddings.reset_onnx_session()

    assert embeddings._onnx_loaded is False
    assert embeddings._onnx_error == ""
    assert embeddings._onnx_session is None


# ── ONNX model readiness ────────────────────────────────────────────────

def test_onnx_model_ready_false_when_no_files(monkeypatch, tmp_path):
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "_onnx_model_dir", lambda: tmp_path / "nonexistent")
    assert embeddings._onnx_model_ready() is False


def test_onnx_model_ready_true_when_files_exist(monkeypatch, tmp_path):
    from data.vector import embeddings

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.onnx").write_text("fake")
    (model_dir / "tokenizer.json").write_text("fake")

    monkeypatch.setattr(embeddings, "_onnx_model_dir", lambda: model_dir)
    assert embeddings._onnx_model_ready() is True
