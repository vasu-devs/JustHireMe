"""Evaluation harness for the deterministic ranking engine.

Turns ranking quality from an opinion into a measured, regression-guarded number.
Labeled ``(profile, job) -> expected band`` cases live in ``evals/cases/*.jsonl``;
:mod:`evals.harness` runs them through :func:`ranking.scoring_engine.score_job_lead`
and ``tests/test_ranking_evals.py`` turns the report into CI gates.

Human-readable report:  ``uv run python -m evals.harness``

Import the API from :mod:`evals.harness` (``from evals.harness import run_evals``).
"""
