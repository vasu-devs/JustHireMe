"""Coverage-Grounded Fit Engine (CGFE) — field-agnostic candidate↔job scoring.

See docs/FIT_EVALUATION_ALGORITHM.md. ``score_fit`` is a drop-in for
``ranking.scoring_engine.score_job_lead`` returning the same ScoreResult contract.
"""
from ranking.fit.engine import FitResult, evaluate_fit, score_fit

__all__ = ["FitResult", "evaluate_fit", "score_fit"]
