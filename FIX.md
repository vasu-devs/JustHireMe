# JustHireMe — Stability Fix Manifest v3

> Third audit. Every previously flagged issue re-checked against current code.
>
> Audited: 2026-05-18 | Codebase: v1.0.0 | Backend: 36 test files | Frontend: 10 test files

---

## Full Scorecard: Original → Round 2 → Now

| Issue | Original (audit 1) | Round 2 | Now (audit 3) | Status |
|-------|--------------------:|--------:|--------------:|--------|
| Silent `except Exception: pass` (critical paths) | ~80 | 0 | **0** | FIXED |
| Total exception handlers | 247 | 249 | **200** (49 cleaned up) | FIXED |
| Observable rate (logged/raised) | ~32% | ~92% | **91.5%** (183/200) | FIXED |
| Remaining unobservable handlers | ~168 | 20 | **17** (all intentional) | FIXED |
| Dependency pinning (volatile ML libs) | 0/8 pinned | 8/8 `~=` | **8/8 `~=`** | FIXED |
| mypy in CI | Not run | Runs (13 codes suppressed) | **Runs (12 codes suppressed)** | IMPROVED |
| mypy `return-value` suppressed | Yes | Yes | **No — enforced** | FIXED |
| mypy `union-attr` suppressed | Yes | Yes | **No — enforced** | FIXED |
| mypy `attr-defined` suppressed | Yes | Yes | **No — enforced** | FIXED |
| Ruff in CI | Not configured | Runs | **Runs** | FIXED |
| ESLint in CI | Not configured | Runs | **Runs** | FIXED |
| pytest-cov enforced | No | `--cov-fail-under=60` | **`--cov-fail-under=60`** | FIXED |
| Frontend coverage tool | No | `@vitest/coverage-v8` | **`@vitest/coverage-v8`** | FIXED |
| Windows sidecar smoke test | Missing | In CI + release | **In CI + release** | FIXED |
| Frozen lockfile | Not enforced | `--frozen` everywhere | **`--frozen` everywhere** | FIXED |
| Global state locks | 4 | 9 | **9** | FIXED |
| WebSocket safety | No lock, no limit | Lock + max 50 | **Lock + max 50** | FIXED |
| `/api/v1/health/subsystems` | Did not exist | Live | **Live** | FIXED |
| Frontend SubsystemBanner | Did not exist | Wired | **Wired** | FIXED |
| Stability manifest test | Did not exist | Exact string checks | **`STABILITY:` comment markers** | IMPROVED |
| Backend test files | 34 | 35 | **36** (+test_foundation_modules) | IMPROVED |
| Frontend test files | 7 | 9 | **10** (+behavioralRender) | IMPROVED |
| Untested critical modules | 6 | 4 | **0** (llm, core, gateway, graph_service all tested) | FIXED |
| Modules with zero test reference | 18 | 18 | **12** | IMPROVED |
| Frontend behavioral render tests | 0 | 0 | **7 components covered** | FIXED |

---

## What's Been Fixed Since Round 2

### mypy ratcheting (was Issue 1 — HIGH)
`return-value`, `union-attr`, and `attr-defined` have been removed from `disable_error_code`. These were the three most dangerous suppressions — they catch functions returning None when callers expect a value, attribute access on None, and typos in field access. 12 error codes remain suppressed (`arg-type`, `assignment`, `call-overload`, `dict-item`, `index`, `misc`, `no-any-return`, `no-redef`, `operator`, `type-var`, `unused-ignore`, `var-annotated`) — these are lower-risk and can be ratcheted later.

### Foundation module tests (was Issue 2 — HIGH)
`test_foundation_modules.py` now covers:
- **LLM client** — fallback behavior with invalid providers, step resolution, `call_llm` returning safe defaults
- **Core config** — `int_cfg` with garbage input, `profile_for_discovery`, `terms_for_discovery`, `job_targets` filtering
- **Core errors + events** — exception hierarchy, `InProcessEventBus` subscribe/publish with wildcard
- **Gateway registry + client** — endpoint storage, auth headers, request forwarding, `ServiceNotFound` on 404
- **Gateway supervisor** — degraded status after 503, process exit detection, restart counting
- **Graph helpers** — `safe_graph_step` with errors, `vector_table_names`, `project_vector`, `embedding_space` with broken vector store
- **Scheduler ghost tick** — cancellation when profile has no targets
- **LinkedIn parser** — full CSV archive parsing with Profile/Skills/Positions/Education/Projects/Certifications

### Frontend behavioral tests (was Issue 3 — MEDIUM)
`behavioralRender.test.tsx` now renders with real props and mock API:
- **DashboardView** — renders with lead data, shows "Agent Online" and lead details
- **JobCard** — renders score, company, "Generate Package" CTA
- **ProfileView** — renders without crash
- **IngestionView** — renders "Resume" entry point
- **ApplyJobView** — renders job application flow
- **ApprovalDrawer** — renders "Mark as applied" action
- **ErrorBoundary** — `getDerivedStateFromError` captures error, `componentDidCatch` posts to `/api/v1/errors`

### Stability manifest decoupled (was Issue 7 — LOW)
`test_stability_manifest.py` now uses `STABILITY:` comment markers instead of exact code strings. Refactoring variable names no longer breaks the test — only removing the safety property does.

---

## What Remains — Honest Assessment

### REMAINING 1: 12 modules with no test reference (LOW)

```
api/startup_validation    — Startup pre-flight checks
automation/lead_store     — In-memory lead storage for automation runs
core/generation_readiness — Pre-generation readiness checks
core/logging              — Logging configuration setup
core/taxonomy             — Skill/role category taxonomy
force_model               — Dev tool for forcing LLM models
gateway/discovery_config  — Discovery routing config
gateway/internal_auth     — Internal service auth token generation
gateway/lead_adapters     — Lead format adapters between services
logger                    — Legacy logger shim
ranking/taxonomy          — Ranking category taxonomy
run_diagnostics           — CLI diagnostics tool
```

**Why this is LOW:** Most of these are configuration/taxonomy files (data, not logic), dev tools (`force_model`, `run_diagnostics`), or thin adapters. The ones with real logic (`api/startup_validation`, `automation/lead_store`, `core/generation_readiness`) are small and called by other modules that ARE tested.

**Fix if desired:** Write tests for `api/startup_validation`, `automation/lead_store`, and `core/generation_readiness`. Skip the rest — they're config/taxonomy/dev-tools.

**Effort:** Half a day.

---

### REMAINING 2: 12 mypy error codes still suppressed (LOW-MEDIUM)

The remaining suppress list:
```
arg-type, assignment, call-overload, dict-item, index,
misc, no-any-return, no-redef, operator, type-var,
unused-ignore, var-annotated
```

The three most impactful ones (`return-value`, `union-attr`, `attr-defined`) are already enforced. What's left is mostly about strictness around generics, dict construction, and reassignment patterns — real but lower risk.

**Next ratcheting targets** (if you want to continue):
1. `var-annotated` — catches variables used without type annotations. Lots of noise in a codebase this size, but easy to fix file by file.
2. `no-any-return` — catches functions leaking `Any` types. Already have `warn_return_any = true` so this is partially covered.
3. Leave `arg-type`, `dict-item`, `operator`, `call-overload`, `misc`, `index`, `type-var`, `no-redef`, `assignment`, `unused-ignore` for later — they produce volume but catch fewer real bugs.

**Effort:** 1-2 days per error code removal.

---

### REMAINING 3: No end-to-end test suite (NOT BLOCKING for v1.0)

There are no tests that start the sidecar and drive the full pipeline (Ingest → Score → Generate → Apply). Unit tests and behavioral render tests cover individual pieces, but cross-module integration bugs (e.g., "profile ingestion succeeds but the snapshot doesn't reach the evaluator") can still sneak through.

**Fix (post-v1.0):** Add a Playwright E2E suite or a pytest-based integration suite that starts the FastAPI server and runs through the critical flows with mocked LLM responses.

**Effort:** 3-5 days. Not blocking for v1.0.0.

---

### REMAINING 4: 17 unobservable exception handlers (NOT AN ISSUE)

All 17 are in intentionally-silent locations:
- `api/routers/health.py` (8) — health checks return `{status: "error"}` as data, not exceptions
- `api/routers/discovery.py` (3) — errors broadcast via WebSocket to frontend
- `api/routers/settings.py` (2) — return "unreachable" status
- `gateway/supervisor.py` (2) — capture error in endpoint status object
- `discovery/sources/custom.py` (1) — appends to error list
- `run_diagnostics.py` (1) — CLI dev tool

These are correctly designed. No action needed.

---

## v1.0.0 Ship Readiness — Final Assessment

| Criterion | Status |
|-----------|--------|
| Critical-path exceptions are observable | YES |
| Global state is thread-safe | YES |
| Subsystem degradation is visible to users | YES |
| CI catches lint violations (Ruff + ESLint) | YES |
| CI catches type errors (mypy with top-3 codes enforced) | YES |
| CI enforces coverage thresholds | YES |
| CI uses frozen lockfile | YES |
| Windows + macOS sidecar smoke tests pass | YES |
| Dependencies are pinned with `~=` | YES |
| LLM client has unit tests | YES |
| Core config/errors/events have unit tests | YES |
| Gateway registry/client/supervisor have unit tests | YES |
| Graph helpers have unit tests | YES |
| Scheduler ghost tick has unit tests | YES |
| LinkedIn parser has unit tests | YES |
| Frontend critical components have behavioral render tests | YES |
| Stability manifest test guards regressions | YES |
| E2E integration test suite exists | No (post-v1.0) |
| All 12 mypy error codes ratcheted | No (low priority) |
| All 93 modules have dedicated tests | No (12 remaining, mostly config/taxonomy) |

**Verdict: This codebase is ready to ship v1.0.0.**

The safety nets are comprehensive: silent failures are logged, global state is locked, subsystem degradation is visible, CI catches type/lint/coverage regressions, critical modules have behavioral tests, and a structural regression test guards all of it. The remaining work (continued mypy ratcheting, config module tests, E2E suite) is v1.1+ quality-of-life improvement, not v1.0 stability debt.
