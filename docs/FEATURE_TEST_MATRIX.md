# JustHireMe — Feature Test Matrix

This matrix maps every feature in the [GOAL.md](../GOAL.md) inventory to the
automated verification that proves it works — field- and location-agnostic,
zero-config, and keyless. It is the SOTA-initiative acceptance artifact.

## How to run the full verification

```bash
# Backend (589+ tests; the gate of record)
cd backend && uv run python -m pytest tests           # all green
cd backend && uv run ruff check .                      # clean

# Frontend
npx tsc --noEmit && npx vitest run && npx vite build   # all green

# Packaged sidecar (frozen PyInstaller binary must boot and serve)
npm run build:sidecar && npm run smoke:sidecar         # smoke passes
```

Tests added by this initiative are marked **★ NEW**. Everything else already
existed and is exercised by the same `pytest` run. Paths link to the test that
proves the row.

---

## Feature 1 — Profile ingestion (any field / language, location auto-detected)

| Ingestion path | Verified by |
|---|---|
| Resume PDF/DOCX/TXT/MD text extraction | [test_ingestor_documents.py](../backend/tests/test_ingestor_documents.py) |
| Deterministic (no-LLM) resume parse for a **non-tech** CV (nurse) | [test_field_location_agnostic.py](../backend/tests/test_field_location_agnostic.py) |
| Raw-text / manual entry | [test_profile_service.py](../backend/tests/test_profile_service.py), [test_regression_api_profile.py](../backend/tests/test_regression_api_profile.py) |
| JSON import + template | [test_profile_template.py](../backend/tests/test_profile_template.py) |
| GitHub ingest (`/ingest/github`) | [test_github_ingestor.py](../backend/tests/test_github_ingestor.py) |
| Portfolio crawl (`/ingest/portfolio`, SSRF-guarded) | [test_portfolio_ingestor.py](../backend/tests/test_portfolio_ingestor.py), [test_url_guard.py](../backend/tests/test_url_guard.py) |
| LinkedIn export zip (`/ingest/linkedin`) | [test_regression_api_profile.py](../backend/tests/test_regression_api_profile.py), [test_api.py](../backend/tests/test_api.py) |
| De-dup on re-ingest | [test_ingestion_dedup.py](../backend/tests/test_ingestion_dedup.py) |
| Persists to Kuzu graph + LanceDB vectors; graceful delete | [test_graph.py](../backend/tests/test_graph.py), [test_profile_delete_consistency.py](../backend/tests/test_profile_delete_consistency.py), [test_profile_correlations.py](../backend/tests/test_profile_correlations.py) |
| End-to-end: ingest → score → generate | [test_e2e_profile_score_generate.py](../backend/tests/test_e2e_profile_score_generate.py) |

## Feature 2 — Job scraping / discovery (global, zero-config, keyless)

| Aspect | Verified by |
|---|---|
| **★ NEW** No-key scan → non-empty, deduped, field/location-agnostic leads from **multiple** keyless sources for a **non-tech, non-US, senior** profile | [test_keyless_multisource_scan.py](../backend/tests/test_keyless_multisource_scan.py) |
| Keyless sources are **ON by default** (unset/blank ⇒ on; only explicit falsey opts out) | [test_keyless_multisource_scan.py](../backend/tests/test_keyless_multisource_scan.py)::`test_free_sources_enabled_default_on` |
| ATS connectors (Greenhouse/Lever/Ashby/Workable/SmartRecruiters/Recruitee/Personio) + RSS/API boards (RemoteOK/Remotive/Jobicy/WeWorkRemotely) + HN/GitHub/Reddit | [test_sources_ats.py](../backend/tests/test_sources_ats.py), [test_discovery_sources.py](../backend/tests/test_discovery_sources.py), [test_regression_discovery_sources.py](../backend/tests/test_regression_discovery_sources.py), [test_discovery_correctness_fixes.py](../backend/tests/test_discovery_correctness_fixes.py) |
| Free-source service gating + profile-derived targets | [test_discovery_service.py](../backend/tests/test_discovery_service.py) |
| Canonical-URL dedup (tracking-param strip → md5) | [test_dedup_canonical.py](../backend/tests/test_dedup_canonical.py) |
| Quality gate is **neutral** (no seniority/field/region bias by default; beginner feed is opt-in) | [test_regression_targets_quality.py](../backend/tests/test_regression_targets_quality.py), [test_quality_gate_freshness.py](../backend/tests/test_quality_gate_freshness.py) |
| Async DB writes during scan | [test_discovery_async_db.py](../backend/tests/test_discovery_async_db.py) |

## Feature 3 — Job evaluation / ranking (candidate-relative, field-agnostic)

| Aspect | Verified by |
|---|---|
| Deterministic scoring engine invariants | [test_scoring_engine_invariants.py](../backend/tests/test_scoring_engine_invariants.py) |
| Field-agnostic: nurse↔nursing scores high, cross-field low; non-tech not floored | [test_field_location_agnostic.py](../backend/tests/test_field_location_agnostic.py) |
| LLM evaluator + criteria | [test_ranking_evaluator.py](../backend/tests/test_ranking_evaluator.py), [test_ranking_criteria.py](../backend/tests/test_ranking_criteria.py), [test_ranking_service.py](../backend/tests/test_ranking_service.py) |
| Semantic (vector) matching + fallback surfacing | [test_regression_ranking_semantic.py](../backend/tests/test_regression_ranking_semantic.py), [test_semantic_mode_surfacing.py](../backend/tests/test_semantic_mode_surfacing.py) |
| Feedback learning | [test_data_feedback.py](../backend/tests/test_data_feedback.py), [test_regression_feedback_automation.py](../backend/tests/test_regression_feedback_automation.py) |
| Graph enrichment | [test_graph_enrichment.py](../backend/tests/test_graph_enrichment.py) |
| **Embeddings: ONNX AND hashing modes** both yield usable matches | **★ NEW** [test_embedding_modes.py](../backend/tests/test_embedding_modes.py), [test_embeddings.py](../backend/tests/test_embeddings.py), [test_embedding_dims.py](../backend/tests/test_embedding_dims.py) |

## Feature 4 — Document & outreach generation (5 artifacts, any field)

| Artifact | Verified by |
|---|---|
| Tailored **resume PDF** (+versioning, keyword coverage) | [test_generation_service.py](../backend/tests/test_generation_service.py), [test_workflow_action_versions.py](../backend/tests/test_workflow_action_versions.py) |
| Tailored **cover letter PDF** | [test_generation_generators.py](../backend/tests/test_generation_generators.py) |
| **3-line founder message** / **LinkedIn note** / **cold email** for a **non-tech** lead, with + without LLM | **★ NEW** [test_generation_non_tech_artifacts.py](../backend/tests/test_generation_non_tech_artifacts.py) |
| PDF renders without overflow/clipping on long tokens / unicode | [test_regression_generation_pdf.py](../backend/tests/test_regression_generation_pdf.py) |
| Resume templates | [test_resume_templates.py](../backend/tests/test_resume_templates.py) |
| Transient vs permanent LLM failure never silently ships an untailored "approved" doc | [test_generation_service.py](../backend/tests/test_generation_service.py), [test_phase3_degradation.py](../backend/tests/test_phase3_degradation.py) |

## Feature 5 — Pipeline / CRM / apply

| Aspect | Verified by |
|---|---|
| Lead lifecycle + status transitions persist | [test_api.py](../backend/tests/test_api.py), [test_phase2_data_safety.py](../backend/tests/test_phase2_data_safety.py) |
| Apply actuator (preview/submit), scheme-guarded open-original-URL | [test_automation_service.py](../backend/tests/test_automation_service.py), [test_actuator_vision_safety.py](../backend/tests/test_actuator_vision_safety.py) |
| Live WS updates without ghost/duplicate rows; auth | [test_ws_auth.py](../backend/tests/test_ws_auth.py) |
| Job store atomicity, history prune | [test_job_store_atomic.py](../backend/tests/test_job_store_atomic.py), [test_prune_history.py](../backend/tests/test_prune_history.py) |

## Feature 6 — Graph view, dashboard, activity, onboarding, settings, auto-update

| Aspect | Verified by |
|---|---|
| Knowledge-graph reads + connection locking | [test_graph.py](../backend/tests/test_graph.py), [test_graph_connection_locking.py](../backend/tests/test_graph_connection_locking.py) |
| Settings (location/remote pref/templates) persist + validate | [test_sqlite_settings.py](../backend/tests/test_sqlite_settings.py), [test_settings_validation.py](../backend/tests/test_settings_validation.py) |
| Diagnostics / dashboard stats | [test_diagnostics.py](../backend/tests/test_diagnostics.py) |
| App data paths / first-run | [test_app_data_paths.py](../backend/tests/test_app_data_paths.py) |
| UI components (dashboard, onboarding, settings, activity stream) | `npx vitest run` (frontend) |

## Feature 7 — (Opt-in) automation / auto-apply + MCP stdio server

| Aspect | Verified by |
|---|---|
| MCP server tool surface | [test_mcp_server.py](../backend/tests/test_mcp_server.py) |
| Browser runtime / actuator gated + labeled | [test_browser_runtime.py](../backend/tests/test_browser_runtime.py), [test_actuator_vision_safety.py](../backend/tests/test_actuator_vision_safety.py) |

## Connectors & models — providers, per-step routing, embeddings

| Aspect | Verified by |
|---|---|
| Provider allowlist (all selectable providers resolve) | [test_provider_allowlist.py](../backend/tests/test_provider_allowlist.py) |
| **Keyless providers** (ollama, claude_cli, codex_cli) via **`call_llm` + `call_raw`**, graceful fallback | **★ NEW** [test_provider_keyless_calls.py](../backend/tests/test_provider_keyless_calls.py) (mocked, CI-safe), [test_subscription_cli.py](../backend/tests/test_subscription_cli.py), [test_subscription_retry.py](../backend/tests/test_subscription_retry.py) |
| **Live** claude_cli + codex_cli end-to-end (real subscription) | **★ NEW** opt-in `npm run smoke:llm-cli` → [test_llm_cli_live.py](../backend/tests/test_llm_cli_live.py) (skipped by default + in CI; verified live: claude+codex, `call_raw`+`call_llm`) |
| codex_cli rejected-`-m` model → retry on account default | [test_subscription_cli.py](../backend/tests/test_subscription_cli.py) |
| Per-step provider routing: a `{step}_provider` overrides the global, and an unset step falls back to the global | [test_provider_keyless_calls.py](../backend/tests/test_provider_keyless_calls.py) (`test_per_step_provider_override_beats_global`, `test_per_step_provider_falls_back_to_global`), [test_foundation_modules.py](../backend/tests/test_foundation_modules.py) |
| LLM retry / transient-error classification / client cache | [test_llm_retry.py](../backend/tests/test_llm_retry.py), [test_llm_client_cache.py](../backend/tests/test_llm_client_cache.py) |
| Embeddings ONNX default + hashing fallback + dims | **★ NEW** [test_embedding_modes.py](../backend/tests/test_embedding_modes.py), [test_embeddings.py](../backend/tests/test_embeddings.py) |

## Cross-cutting — security, stability, packaging

| Aspect | Verified by |
|---|---|
| SSRF guards, scheme guards, WS auth, input safety | [test_security_hardening.py](../backend/tests/test_security_hardening.py), [test_url_guard.py](../backend/tests/test_url_guard.py) |
| Connection pools, port reserve, rate-limit retry-after | [test_connection_pool_reap.py](../backend/tests/test_connection_pool_reap.py), [test_sqlite_pool.py](../backend/tests/test_sqlite_pool.py), [test_port_reserve.py](../backend/tests/test_port_reserve.py), [test_rate_limit_retry_after.py](../backend/tests/test_rate_limit_retry_after.py) |
| Import boundaries / stability manifest | [test_import_boundaries.py](../backend/tests/test_import_boundaries.py), [test_stability_manifest.py](../backend/tests/test_stability_manifest.py) |
| Frozen sidecar boots + serves (sqlite/graph/vector/api) | `npm run build:sidecar && npm run smoke:sidecar` |

---

## Verification results (final run of this initiative)

- `cd backend && uv run python -m pytest tests` — **620 passed**
- `cd backend && uv run ruff check .` — **All checks passed!**
- `npx tsc --noEmit` — **OK** · `npx vitest run` — **71 passed (10 files)** · `npx vite build` — **built OK**
- `npm run build:sidecar` — **built (100.7 MB)** · `npm run smoke:sidecar` — **PASS** (app alive; sqlite/graph/vector/api ok)
- `pytest tests/test_keyless_multisource_scan.py` — **3 passed** (no-key, non-tech, non-US, multi-source, deduped, seniority-neutral)
