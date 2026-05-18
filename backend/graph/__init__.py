from __future__ import annotations
import logging

import warnings
from typing import Any, TypedDict

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change in a future version.*",
        category=LangChainPendingDeprecationWarning,
        module=r"langgraph\.cache\.base",
    )
except Exception as log_exc:
    logging.getLogger(__name__).warning('suppressed exception in backend/graph/__init__.py:<module>: %s', log_exc)
    pass

from langgraph.graph import END, StateGraph

from core.logging import get_logger

_log = get_logger(__name__)


class PipelineState(TypedDict):
    job_id: str
    lead: dict[str, Any]
    profile: dict[str, Any]
    cfg: dict[str, Any]
    score: int
    reason: str
    match_points: list[str]
    gaps: list[str]
    asset_path: str
    cover_letter_path: str
    error: str | None


def _job_eval_document(lead: dict) -> str:
    desc = (lead.get("description") or "").strip()
    return (
        f"Job Title: {lead.get('title','')}\n"
        f"Company: {lead.get('company','')}\n"
        f"URL: {lead.get('url','')}\n"
        + (f"Description: {desc}" if desc else "")
    )


def evaluate_node(state: PipelineState) -> dict:
    try:
        from ranking.evaluator import score

        result = score(_job_eval_document(state["lead"]), state["profile"])
        return {
            "score": int(result.get("score") or 0),
            "reason": str(result.get("reason") or ""),
            "match_points": list(result.get("match_points") or []),
            "gaps": list(result.get("gaps") or []),
            "error": None,
        }
    except Exception as exc:
        _log.error("evaluate failed for %s: %s", state.get("job_id", "?"), exc)
        return {
            "score": 0,
            "reason": "eval failed",
            "match_points": [],
            "gaps": [],
            "error": str(exc),
        }


def generate_node(state: PipelineState) -> dict:
    threshold = int(state.get("cfg", {}).get("auto_generate_threshold") or 60)
    if int(state.get("score") or 0) < threshold:
        return {"asset_path": "", "cover_letter_path": "", "error": None}
    try:
        from core.generation_readiness import lead_generation_blocker

        blocked_reason = lead_generation_blocker(state["lead"])
        if blocked_reason:
            return {"asset_path": "", "cover_letter_path": "", "error": blocked_reason}
        from generation.generator import run_package

        template = str(state.get("cfg", {}).get("resume_template") or "")
        package = run_package({**state["lead"], **state}, template=template)
        return {
            "asset_path": package.get("resume", ""),
            "cover_letter_path": package.get("cover_letter", ""),
            "error": None,
        }
    except Exception as exc:
        _log.error("generate failed for %s: %s", state.get("job_id", "?"), exc)
        return {"asset_path": "", "cover_letter_path": "", "error": str(exc)}


def persist_node(state: PipelineState) -> dict:
    from data.repository import create_repository

    repo = create_repository()

    try:
        repo.leads.update_lead_score(
            state["job_id"],
            int(state.get("score") or 0),
            state.get("reason") or "",
            state.get("match_points") or [],
            state.get("gaps") or [],
        )
        if state.get("asset_path") or state.get("cover_letter_path"):
            repo.leads.save_asset_package(
                state["job_id"],
                state.get("asset_path") or "",
                state.get("cover_letter_path") or "",
            )
    except Exception as exc:
        _log.warning("pipeline persistence skipped for %s: %s", state.get("job_id", "?"), exc)
    return {}


def build_eval_graph():
    g = StateGraph(PipelineState)
    g.add_node("evaluate", evaluate_node)
    g.add_node("generate", generate_node)
    g.add_node("persist", persist_node)

    g.set_entry_point("evaluate")
    g.add_edge("evaluate", "generate")
    g.add_edge("generate", "persist")
    g.add_edge("persist", END)

    return g.compile()


eval_graph = build_eval_graph()
