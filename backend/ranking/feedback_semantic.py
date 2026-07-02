"""Content-based feedback for the MATCH score: "jobs like ones you liked score higher".

The metadata feedback model (feedback_ranker) nudges the discovery signal_score by
board/company/stack. This nudges the score the user actually ranks and applies on —
the evaluator MATCH score — by MEANING: it builds a preference direction from the
embeddings of liked-minus-disliked postings and shifts each open lead's score by how
well it aligns. Field-agnostic (a nurse's "good" ratings teach nursing fit, a lawyer's
teach legal fit), and inert when only the hash embedder is available (its cosine is
unreliable) so it never fabricates a delta from noise.
"""

from __future__ import annotations

import logging
import math

from ranking.feedback_ranker import NEGATIVE_LABELS, POSITIVE_LABELS

_log = logging.getLogger(__name__)


def _text(item: dict) -> str:
    return f"{item.get('title', '')} {item.get('description', '')}".strip()


def _polarity(feedback) -> float:
    fb = str(feedback or "").strip().lower()
    if fb in POSITIVE_LABELS:
        return POSITIVE_LABELS[fb]
    if fb in NEGATIVE_LABELS:
        return NEGATIVE_LABELS[fb]
    return 0.0


def _unit(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def preference_deltas(examples: list[dict], leads: list[dict], *, max_delta: int = 12) -> dict[str, int]:
    """Map job_id -> a bounded [-max_delta, +max_delta] match-score delta.

    Returns {} (no change) when there is no polarised feedback or real embeddings are
    unavailable. Deterministic and idempotent: a fresh call reproduces the same deltas.
    """
    try:
        from data.vector.embeddings import active_provider, embed_texts

        if active_provider() == "hash":
            return {}
        weighted = [(_text(e), _polarity(e.get("feedback"))) for e in examples or []]
        weighted = [(t, w) for t, w in weighted if t and w != 0.0]
        if not weighted:
            return {}
        lead_texts = [_text(lead) for lead in leads]
        example_texts = [t for t, _ in weighted]
        vectors = embed_texts(example_texts + lead_texts)
        if not vectors or len(vectors) != len(example_texts) + len(lead_texts):
            return {}

        example_vecs = [_unit(v) for v in vectors[: len(example_texts)]]
        lead_vecs = [_unit(v) for v in vectors[len(example_texts):]]

        dim = len(example_vecs[0])
        preference = [0.0] * dim
        for (_text_i, weight), vec in zip(weighted, example_vecs, strict=False):
            for i in range(dim):
                preference[i] += weight * vec[i]
        preference = _unit(preference)
        if not any(preference):
            return {}

        out: dict[str, int] = {}
        for lead, lvec in zip(leads, lead_vecs, strict=False):
            job_id = str(lead.get("job_id") or "").strip()
            if not job_id:
                continue
            sim = sum(a * b for a, b in zip(preference, lvec, strict=False))  # [-1, 1]
            delta = round(max(-1.0, min(1.0, sim)) * max_delta)
            if delta:
                out[job_id] = delta
        return out
    except Exception as exc:
        _log.debug("semantic feedback preference skipped: %s", exc)
        return {}
