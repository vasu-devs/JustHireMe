from __future__ import annotations
import logging

import hashlib
import math
import re
import threading
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)
_st: Any = None
_st_error = ""
# STABILITY: thread-safe lazy embedding model initialization
_st_lock = threading.RLock()


def hash_embedding(text: str, dims: int = 384) -> list[float]:
    vec = [0.0] * dims
    tokens = re.findall(r"[a-z0-9+#.-]{2,}", (text or "").lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % dims
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


def embed_texts(texts: list[str]) -> list:
    global _st, _st_error
    if _st is None:
        with _st_lock:
            if _st is None:
                result = [None]
                exc_holder = [None]

                def _load():
                    try:
                        from sentence_transformers import SentenceTransformer

                        result[0] = SentenceTransformer("all-MiniLM-L6-v2")
                    except Exception as exc:
                        logging.getLogger(__name__).warning('suppressed exception in backend/data/vector/embeddings.py:_load: %s', exc)
                        exc_holder[0] = exc

                thread = threading.Thread(target=_load, daemon=True)
                thread.start()
                thread.join(timeout=120)
                if thread.is_alive():
                    _st_error = "SentenceTransformer load timed out"
                    _log.warning("SentenceTransformer unavailable; using built-in local embedder")
                    _st = "hashing"
                elif exc_holder[0] or result[0] is None:
                    _st_error = str(exc_holder[0] or "SentenceTransformer returned no model")
                    _log.warning("SentenceTransformer unavailable; using built-in local embedder")
                    _st = "hashing"
                else:
                    _st_error = ""
                    _st = result[0]
    if _st == "hashing":
        return [hash_embedding(text) for text in texts]
    return _st.encode(texts).tolist()


def embedding_status() -> dict:
    with _st_lock:
        if _st is None:
            return {"status": "ok", "mode": "lazy", "model": "all-MiniLM-L6-v2"}
        if _st == "hashing":
            return {
                "status": "degraded",
                "mode": "hashing",
                "model": "built-in hashing embedder",
                "error": _st_error or "SentenceTransformer unavailable",
            }
        return {"status": "ok", "mode": "sentence-transformer", "model": "all-MiniLM-L6-v2"}
