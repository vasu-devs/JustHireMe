from __future__ import annotations

import re

from data.sqlite.leads import (
    get_feedback_training_examples as _get_sqlite_feedback_training_examples,
)


def get_feedback_training_examples(limit: int = 300, db_path: str | None = None) -> list[dict]:
    if db_path is None:
        return _get_sqlite_feedback_training_examples(limit)
    return _get_sqlite_feedback_training_examples(limit, db_path)


def rank_lead_by_feedback(lead: dict, db_path: str | None = None) -> dict:
    out = dict(lead)
    out.setdefault("base_signal_score", int(out.get("signal_score") or 0))
    out.setdefault("learning_delta", 0)
    out.setdefault("learning_reason", "")
    return out


def _without_learning_suffix(reason: str) -> str:
    return re.sub(r"(?:;\s*)?feedback learning [+-]\d+", "", reason or "").strip(" ;")


def recompute_learning_scores(limit: int = 500, db_path: str | None = None) -> int:
    return 0
