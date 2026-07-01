# Ranking evaluation harness

Makes ranking quality a **measured, regression-guarded number** instead of an
opinion. Labeled `(profile, job) -> expected band` cases are scored through the
real `ranking.scoring_engine.score_job_lead`, and CI fails when a change
regresses a labeled case.

Why this exists: the ranking engine is a weighted rubric + hard caps
(`scoring_engine.py`). Before this harness there was no way to tell an
improvement from a lucky change. This is the foundation the feedback-learning and
rubric-tuning work builds on — you can now prove a change helps.

## Run it

```bash
cd backend
uv run python -m evals.harness        # human-readable report (scores, per-field, failures)
uv run python -m pytest tests/test_ranking_evals.py -q   # the CI gates
```

The harness runs deterministically: the semantic criterion self-disables when the
vector store / embedding model is absent (as in CI), so scores are stable.

## Layout

```
evals/
  harness.py            # load cases, score, report; `python -m evals.harness`
  cases/
    tech.jsonl          # one JSON object per line (blank lines / # comments ok)
    healthcare.jsonl
    trades.jsonl
    business.jsonl
    cross_field.jsonl   # mismatches that must stay capped
    seniority.jsonl
```

`tests/test_ranking_evals.py` turns the report into two gates: **invariants must
hold** and **aggregate accuracy >= floor**.

## Add a case

Append a line to the relevant `cases/*.jsonl`:

```json
{"id": "trades-plumber-match", "field": "trades",
 "profile": {"s": "Licensed plumber, 5 years.",
             "skills": [{"n": "Pipe Fitting"}, {"n": "Soldering"}],
             "exp": [{"role": "Plumber", "co": "PipeCo", "period": "2020 - Present", "d": "residential plumbing"}]},
 "jd": "Job Title: Plumber\nDescription: Pipe fitting and soldering. 3+ years.",
 "expect": {"min": 55, "max": 82, "capped": false},
 "note": "plumber in-field"}
```

**Fields**

- `id` (unique), `field` (grouping label), `profile` (a candidate dict exactly as
  `score_job_lead` receives: `s`, `skills[{n}]`, `exp[{role,co,period,d}]`,
  `projects[{title,stack,impact}]`, `certifications[{title}]`), `jd` (job text;
  the engine parses `Job Title:` / `Company:` / `Description:`).
- `expect`: any of
  - `band`: `strong` (68–100), `solid` (52–100), `weak` (30–74), `reject` (0–40) — shorthand for a range;
  - `min` / `max`: explicit score bounds (override the band bound);
  - `capped`: `true`/`false` — assert whether a hard cap (wrong-field / seniority / thin-stack) fired.
- `invariant`: `true` marks a **product guarantee** — its failure fails CI outright
  (use for the guarantees that must never regress: in-field non-tech not floored,
  cross-field/seniority mismatches capped).
- `note`: why this case exists.

## Calibrating expectations

New in-field cases: set a **`min`** (the regression you fear is the score
dropping) with a generous `max`. Mismatch cases: set a **`max`** + `capped: true`
(the regression you fear is a mismatch creeping up). Get the current number from
`uv run python -m evals.harness`, then set the band with a few points of headroom
so benign tuning doesn't trip it but a real regression does.
