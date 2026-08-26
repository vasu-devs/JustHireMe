"""Exercise BOTH embedding modes end-to-end: ONNX (default) and hash fallback.

These tests drive the public API (``embed_texts`` / ``active_provider`` /
``embedding_dims``) rather than the private tier helpers. The seam for forcing
a mode is the same one ``test_embeddings.py`` uses: patch
``embeddings._configured_provider`` (which is what reads the
``embedding_provider`` setting through the settings/``get_setting`` layer).

onnxruntime is installed, but the all-MiniLM-L6-v2 model file is NOT downloaded
in the test environment (that ships via the on-demand vector-runtime pack), so
the ONNX path cascades down to the deterministic BLAKE2b hash fallback. These
tests assert whichever path is active is graceful and yields usable, correctly-
dimensioned vectors — and, when the ONNX model IS present, that it is 384-dim.

Sample texts are intentionally non-tech and not English-only.
"""
from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.integration


# Non-tech, multilingual sample texts.
SAMPLE_TEXTS = [
    "enfermera de cuidados intensivos registrada",  # Spanish: registered ICU nurse
    "soudeur mig tig expérimenté",  # French: experienced mig/tig welder
]

_ONNXRUNTIME_AVAILABLE = importlib.util.find_spec("onnxruntime") is not None


def _force_provider(monkeypatch, provider: str):
    """Force the configured embedding_provider, resetting cached ONNX state.

    ``active_provider()`` caches the ONNX load attempt in module globals, so we
    reset it to make each mode-forcing test independent.
    """
    from data.vector import embeddings

    monkeypatch.setattr(embeddings, "_configured_provider", lambda: provider)
    embeddings.reset_onnx_session()
    return embeddings


# ── HASH mode ─────────────────────────────────────────────────────────────

def test_hash_mode_correct_and_consistent_dims(monkeypatch):
    embeddings = _force_provider(monkeypatch, "hash")
    assert embeddings.active_provider() == "hash"

    dims = embeddings.embedding_dims()
    vecs = embeddings.embed_texts(SAMPLE_TEXTS)

    assert len(vecs) == len(SAMPLE_TEXTS)
    for vec in vecs:
        assert len(vec) == dims
        assert all(isinstance(v, float) for v in vec)
    # Consistent dimensionality across every vector in the batch.
    assert len({len(vec) for vec in vecs}) == 1


def test_hash_mode_deterministic(monkeypatch):
    embeddings = _force_provider(monkeypatch, "hash")

    first = embeddings.embed_texts(SAMPLE_TEXTS)
    second = embeddings.embed_texts(SAMPLE_TEXTS)

    assert first == second  # same input -> byte-identical vectors


def test_hash_mode_nonzero(monkeypatch):
    embeddings = _force_provider(monkeypatch, "hash")

    vecs = embeddings.embed_texts(SAMPLE_TEXTS)

    # The hash scheme is NOT semantic, so we assert only that real content
    # yields a non-degenerate (nonzero) vector — no similarity claims.
    for vec in vecs:
        assert any(abs(v) > 0.0 for v in vec)


def test_hash_mode_empty_input(monkeypatch):
    embeddings = _force_provider(monkeypatch, "hash")
    assert embeddings.embed_texts([]) == []


# ── ONNX mode (graceful fallback when the ONNX model isn't downloaded) ─────

def test_onnx_mode_returns_usable_vectors(monkeypatch):
    embeddings = _force_provider(monkeypatch, "onnx")

    # The ONNX MiniLM model file isn't downloaded in CI, so active_provider()
    # cascades down to hash without crashing — either way embed_texts must succeed.
    dims = embeddings.embedding_dims()
    vecs = embeddings.embed_texts(SAMPLE_TEXTS)

    assert len(vecs) == len(SAMPLE_TEXTS)
    for vec in vecs:
        assert len(vec) == dims
        assert all(isinstance(v, float) for v in vec)
        assert any(abs(v) > 0.0 for v in vec)


def test_onnx_mode_dims_match_runtime_availability(monkeypatch):
    embeddings = _force_provider(monkeypatch, "onnx")

    provider = embeddings.active_provider()
    dims = embeddings.embedding_dims()

    if _ONNXRUNTIME_AVAILABLE and provider == "onnx":
        # Genuine ONNX path active → all-MiniLM-L6-v2 is 384-dim.
        assert dims == embeddings.ONNX_DIMS == 384
    else:
        # onnxruntime absent (or model not downloaded) → graceful hash fallback.
        assert provider == "hash"
        assert dims == embeddings.HASH_DIMS

    # Regardless of which path won, vectors must come out at the active dims.
    vecs = embeddings.embed_texts(SAMPLE_TEXTS)
    assert all(len(vec) == dims for vec in vecs)


def test_onnx_mode_empty_input(monkeypatch):
    embeddings = _force_provider(monkeypatch, "onnx")
    assert embeddings.embed_texts([]) == []
