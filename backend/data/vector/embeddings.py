"""Three-tier embedding system for semantic matching.

Tier 1 — ONNX local (all-MiniLM-L6-v2, ~23 MB, default, fully offline)
Tier 2 — OpenAI API (text-embedding-3-small, 1536-dim, user opts in)
Tier 3 — Hash fallback (BLAKE2b token hashing, always available)

The active provider is read from the ``embedding_provider`` setting:
  "onnx"   → Tier 1
  "openai" → Tier 2
  "hash"   → Tier 3  (or any unrecognised value)

When the preferred provider fails at runtime the system cascades down
automatically: onnx → hash, openai → hash.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import threading
from pathlib import Path
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)

# STABILITY: thread-safe lazy embedding model initialization
# ── Thread-safe lazy state ───────────────────────────────────────────────
_lock = threading.RLock()
_onnx_session: Any = None
_onnx_tokenizer: Any = None
_onnx_error: str = ""
_onnx_loaded: bool = False
# Set when a runtime embedding call falls back to hash (openai: network/401/429/off-dim;
# onnx: an inference/session error after the model loaded); cleared on the next success.
# Lets status honestly report degraded semantic matching instead of claiming the
# provider while actually serving hash vectors.
_openai_runtime_error: str = ""
_onnx_runtime_error: str = ""

ONNX_MODEL_NAME = "all-MiniLM-L6-v2"
ONNX_DIMS = 384
OPENAI_MODEL = "text-embedding-3-small"
OPENAI_DIMS = 1536
HASH_DIMS = 384


# ── Tier 3: hash embedding (always available) ───────────────────────────

def hash_embedding(text: str, dims: int = HASH_DIMS) -> list[float]:
    """Deterministic BLAKE2b token-hash embedding. Not semantic but never fails."""
    vec = [0.0] * dims
    tokens = re.findall(r"[a-z0-9+#.-]{2,}", (text or "").lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % dims
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


# ── Tier 1: ONNX local embedding ────────────────────────────────────────

def _onnx_model_dir() -> Path:
    """Return the directory where the ONNX model files are stored."""
    from core.paths import app_data_dir
    return Path(app_data_dir()) / "models" / ONNX_MODEL_NAME


def _onnx_model_ready() -> bool:
    model_dir = _onnx_model_dir()
    return (model_dir / "model.onnx").exists() and (model_dir / "tokenizer.json").exists()


def download_onnx_model(*, force: bool = False) -> dict:
    """Download the ONNX model from Hugging Face Hub into the local cache.

    Returns a status dict. This is safe to call multiple times; it skips if
    the model already exists (unless ``force=True``).
    """
    model_dir = _onnx_model_dir()
    if not force and _onnx_model_ready():
        return {"status": "exists", "path": str(model_dir)}

    model_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        # Fallback: try downloading with urllib directly
        return _download_onnx_urllib(model_dir)

    repo_id = f"sentence-transformers/{ONNX_MODEL_NAME}"
    files = ["model.onnx", "tokenizer.json", "tokenizer_config.json", "config.json"]

    for filename in files:
        try:
            downloaded = hf_hub_download(
                repo_id=repo_id,
                filename=filename if filename != "model.onnx" else "onnx/model.onnx",
                local_dir=str(model_dir),
                local_dir_use_symlinks=False,
            )
            # hf_hub_download may place in subdirectory; move to model_dir root
            downloaded_path = Path(downloaded)
            target = model_dir / filename
            if downloaded_path != target and downloaded_path.exists():
                import shutil
                shutil.move(str(downloaded_path), str(target))
        except Exception as exc:
            _log.warning("ONNX model file %s download failed: %s", filename, exc)
            return {"status": "error", "error": str(exc)}

    return {"status": "ok", "path": str(model_dir)}


def _download_onnx_urllib(model_dir: Path) -> dict:
    """Fallback downloader using only stdlib urllib."""
    import urllib.request

    base = f"https://huggingface.co/sentence-transformers/{ONNX_MODEL_NAME}/resolve/main"
    files = {
        "model.onnx": f"{base}/onnx/model.onnx",
        "tokenizer.json": f"{base}/tokenizer.json",
        "tokenizer_config.json": f"{base}/tokenizer_config.json",
        "config.json": f"{base}/config.json",
    }

    for filename, url in files.items():
        target = model_dir / filename
        if target.exists() and filename != "model.onnx":
            continue
        try:
            _log.info("Downloading %s from %s", filename, url)
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=60) as resp, open(str(target), "wb") as fout:
                import shutil
                shutil.copyfileobj(resp, fout)
        except Exception as exc:
            _log.warning("ONNX model download failed for %s: %s", filename, exc)
            return {"status": "error", "error": str(exc)}

    return {"status": "ok", "path": str(model_dir)}


def _load_onnx_session():
    """Load the ONNX runtime session and tokenizer. Thread-safe, lazy."""
    global _onnx_session, _onnx_tokenizer, _onnx_error, _onnx_loaded

    if _onnx_loaded:
        return _onnx_session is not None

    with _lock:
        if _onnx_loaded:
            return _onnx_session is not None

        if not _onnx_model_ready():
            _onnx_error = "ONNX model not downloaded"
            _onnx_loaded = True
            _log.info("ONNX model not found at %s; use download_onnx_model() first", _onnx_model_dir())
            return False

        model_dir = _onnx_model_dir()
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            _onnx_tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
            _onnx_tokenizer.enable_truncation(max_length=128)
            _onnx_tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=128)

            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = min(os.cpu_count() or 1, 4)

            _onnx_session = ort.InferenceSession(
                str(model_dir / "model.onnx"),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
            _onnx_error = ""
            _onnx_loaded = True
            _log.info("ONNX embedding model loaded successfully from %s", model_dir)
            return True

        except ImportError as exc:
            _onnx_error = f"Missing dependency: {exc.name or exc}"
            _onnx_loaded = True
            _log.info("ONNX runtime not available: %s; will fall back", exc)
            return False
        except Exception as exc:
            _onnx_error = str(exc)
            _onnx_loaded = True
            _log.warning("ONNX model load failed: %s", exc)
            return False


def _onnx_embed(texts: list[str]) -> list[list[float]]:
    """Embed texts using the local ONNX model. Returns list of 384-dim vectors."""
    import numpy as np

    if _onnx_session is None or _onnx_tokenizer is None:
        raise RuntimeError(_onnx_error or "ONNX session not loaded")

    # Tokenize in batch
    encodings = _onnx_tokenizer.encode_batch(texts)
    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

    outputs = _onnx_session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )

    # Mean pooling over token embeddings
    token_embeddings = outputs[0]  # (batch, seq_len, hidden_dim)
    mask_expanded = np.expand_dims(attention_mask, axis=-1).astype(np.float32)
    summed = np.sum(token_embeddings * mask_expanded, axis=1)
    counts = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    pooled = summed / counts

    # L2 normalize
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    norms = np.clip(norms, a_min=1e-9, a_max=None)
    normalized = pooled / norms

    return normalized.tolist()


# ── Tier 2: OpenAI API embedding ─────────────────────────────────────────

def _openai_api_key() -> str | None:
    """Read the OpenAI API key from settings."""
    try:
        from data.sqlite.settings import get_setting
        key = get_setting("openai_api_key", "")
        return key if key else None
    except Exception:
        return os.environ.get("OPENAI_API_KEY")


def _openai_embed(texts: list[str]) -> list[list[float]]:
    """Embed texts using the OpenAI API. Returns list of 1536-dim vectors."""
    api_key = _openai_api_key()
    if not api_key:
        raise RuntimeError("OpenAI API key not configured")

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
    except ImportError:
        # Fallback: use urllib
        return _openai_embed_urllib(texts, api_key)

    response = client.embeddings.create(
        model=OPENAI_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _openai_embed_urllib(texts: list[str], api_key: str) -> list[list[float]]:
    """Embed via OpenAI REST API using only stdlib."""
    import json
    import urllib.request

    payload = json.dumps({"model": OPENAI_MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    return [item["embedding"] for item in body["data"]]


# ── Provider selection ───────────────────────────────────────────────────

# Tracks the last ONNX-fallback reason we logged, so a single ingest (which makes
# many embed calls) doesn't spam the same "falling back to hash" line hundreds of
# times — we log only when the state actually changes.
_last_onnx_fallback_error: str | None = None


def _configured_provider() -> str:
    """Read the user's embedding provider preference from settings."""
    try:
        from data.sqlite.settings import get_setting
        provider = get_setting("embedding_provider", "onnx")
        return str(provider or "onnx").strip().lower()
    except Exception:
        return "onnx"


def active_provider() -> str:
    """Return the provider that will actually be used right now.

    Takes into account both the configured preference and runtime
    availability (e.g. ONNX model not downloaded, OpenAI key missing).
    """
    pref = _configured_provider()
    if pref == "openai":
        if _openai_api_key():
            return "openai"
        _log.info("OpenAI embedding requested but no API key; falling back")
        # Try ONNX as intermediate fallback
        if _load_onnx_session():
            return "onnx"
        return "hash"
    if pref == "hash":
        return "hash"
    # Default: onnx
    if _load_onnx_session():
        return "onnx"
    global _last_onnx_fallback_error
    if _onnx_error != _last_onnx_fallback_error:
        _log.info("ONNX embedding unavailable (%s); falling back to hash", _onnx_error)
        _last_onnx_fallback_error = _onnx_error
    return "hash"


# ── Public API ───────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using the best available provider.

    Always returns a list of vectors, one per input text.
    Falls through to hash embedding on any failure.
    """
    if not texts:
        return []

    provider = active_provider()

    if provider == "onnx":
        global _onnx_runtime_error
        try:
            vecs = _onnx_embed(texts)
            _onnx_runtime_error = ""  # success: clear any prior degraded state
            return vecs
        except Exception as exc:
            # Record the fallback so status/semantic don't keep claiming 'onnx'
            # while actually serving non-semantic hash vectors.
            _onnx_runtime_error = str(exc) or "onnx embedding call failed"
            _log.warning("ONNX embedding failed, falling back to hash@%d: %s", ONNX_DIMS, exc)
            return [hash_embedding(t, ONNX_DIMS) for t in texts]

    if provider == "openai":
        global _openai_runtime_error
        try:
            vecs = _openai_embed(texts)
            # Never let an off-dimension API response poison a table sized for
            # OPENAI_DIMS — treat it as a failure and fall back at the right dim.
            if vecs and len(vecs[0]) != OPENAI_DIMS:
                raise RuntimeError(f"OpenAI returned dim {len(vecs[0])}, expected {OPENAI_DIMS}")
            _openai_runtime_error = ""  # success: clear any prior degraded state
            return vecs
        except Exception as exc:
            # Critical: the OpenAI table is OPENAI_DIMS-wide, so the fallback hash
            # MUST be OPENAI_DIMS too — a 384-dim hash here silently corrupts it.
            # Record the fallback so status/semantic don't keep claiming 'openai'.
            _openai_runtime_error = str(exc) or "openai embedding call failed"
            _log.warning("OpenAI embedding failed, falling back to hash@%d: %s", OPENAI_DIMS, exc)
            return [hash_embedding(t, OPENAI_DIMS) for t in texts]

    # Tier 3: hash
    return [hash_embedding(t, HASH_DIMS) for t in texts]


def embedding_dims() -> int:
    """Return the vector dimensionality of the active provider."""
    provider = active_provider()
    if provider == "openai":
        return OPENAI_DIMS
    if provider == "onnx":
        return ONNX_DIMS
    return HASH_DIMS


def embedding_status() -> dict:
    """Return diagnostic info about the current embedding system."""
    provider = active_provider()
    configured = _configured_provider()

    base = {
        "status": "ok",
        "configured_provider": configured,
        "active_provider": provider,
    }

    if provider == "onnx":
        base["dims"] = ONNX_DIMS
        base["model_path"] = str(_onnx_model_dir())
        if _onnx_runtime_error:
            # Session loaded but inference fell back to hash at runtime — report the
            # truth so semantic scoring uses the hash-baseline window and the user
            # is told matching is degraded, not silently 'healthy'.
            base["model"] = "built-in hashing embedder (ONNX unavailable)"
            base["mode"] = "hashing"
            base["degraded"] = True
            base["onnx_error"] = _onnx_runtime_error
        else:
            base["model"] = ONNX_MODEL_NAME
            base["mode"] = "onnx"
    elif provider == "openai":
        base["dims"] = OPENAI_DIMS
        if _openai_runtime_error:
            # The provider is openai but its last runtime call fell back to hash;
            # report the truth so semantic scoring uses the hash-baseline window and
            # the user is told matching is degraded, not silently 'healthy'.
            base["model"] = "built-in hashing embedder (OpenAI unavailable)"
            base["mode"] = "hashing"
            base["degraded"] = True
            base["openai_error"] = _openai_runtime_error
        else:
            base["model"] = OPENAI_MODEL
            base["mode"] = "openai"
    else:
        base["model"] = "built-in hashing embedder"
        base["dims"] = HASH_DIMS
        base["mode"] = "hashing"
        if _onnx_error:
            base["onnx_error"] = _onnx_error

    # Backward compat: semantic.py checks mode == "hashing" to detect degraded
    return base


def ensure_onnx_model() -> bool:
    """Make real ONNX semantics the default with zero manual setup: if the ONNX
    provider is preferred but the model isn't downloaded yet, fetch it and reload the
    session. No-op when the user chose hash, when a keyed OpenAI provider is set, or
    when the model is already present. Safe to call at startup on a background thread —
    an offline/failed download just leaves the hashing fallback in place. Returns True
    when ONNX is active afterward.
    """
    pref = _configured_provider()
    if pref == "hash":
        return False
    if pref == "openai" and _openai_api_key():
        return False  # a keyed OpenAI provider is in use; don't pull the local model
    if _onnx_model_ready():
        return _load_onnx_session()
    try:
        result = download_onnx_model()
    except Exception as exc:
        _log.info("auto-download of ONNX embedding model skipped: %s", exc)
        return False
    if str((result or {}).get("status")) in ("ok", "exists", "downloaded"):
        reset_onnx_session()
        return _load_onnx_session()
    _log.info("auto-download of ONNX embedding model did not complete: %s", (result or {}).get("error"))
    return False


def reset_onnx_session() -> None:
    """Force reload of the ONNX session on next use. Useful after model download."""
    global _onnx_session, _onnx_tokenizer, _onnx_error, _onnx_loaded, _last_onnx_fallback_error, _openai_runtime_error, _onnx_runtime_error
    with _lock:
        _onnx_session = None
        _onnx_tokenizer = None
        _onnx_error = ""
        _onnx_loaded = False
        _last_onnx_fallback_error = None
        # Clear the runtime degraded flags too — a provider switch / reset is a fresh start.
        _openai_runtime_error = ""
        _onnx_runtime_error = ""
