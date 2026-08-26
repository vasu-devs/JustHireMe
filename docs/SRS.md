# Software Requirements Specification — JustHireMe

**Version:** 1.4.0 · Follows the IEEE 830 structure, trimmed to what is actually useful for this product.

Requirements are traceable: each carries an ID, and the **Verified by** column
names the test that proves it. `docs/FEATURE_TEST_MATRIX.md` is the companion
coverage view.

---

## 1. Introduction

### 1.1 Purpose
Specify the functional and non-functional requirements of the JustHireMe desktop
application, so behaviour changes are deliberate and testable.

### 1.2 Scope
An installed, single-user desktop application that discovers relevant jobs,
scores fit with evidence, generates tailored application material, and tracks
the pipeline locally. Out of scope for this version: multi-user hosting, team
features, and automatic submission without user review.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| **Lead** | A discovered job, with status, score and generated assets. |
| **Package** | The generated resume + cover letter + outreach messages for one lead. |
| **CGFE** | Coverage-Grounded Fit Evaluation — the scoring engine. |
| **Keyless source** | A job source needing no API key; on by default. |
| **Sidecar** | The Python FastAPI process the Tauri shell supervises. |
| **Degraded** | Running with a reduced-capability fallback, reported honestly. |

---

## 2. Overall description

### 2.1 Product perspective
Self-contained desktop app: Tauri (Rust) shell + React UI + Python sidecar +
local SQLite/Kùzu/LanceDB. No JustHireMe-operated server exists. The only
outbound traffic is to public job sources and the LLM provider the user chose.

### 2.2 User characteristics
A single job-seeking candidate in **any** field — the product is explicitly not
tech-only. Assumed comfortable installing a desktop app; not assumed to hold an
LLM API key.

### 2.3 Constraints
- Must run offline for everything except discovery and generation.
- Must not require a paid key to be useful.
- Must not transmit CV content anywhere except the user's chosen LLM provider.
- Single-tenant: one profile per installation.

### 2.4 Assumptions and dependencies
Job sources keep serving public endpoints; LLM provider availability is the
user's; the OS permits binding a loopback port.

---

## 3. Functional requirements

### 3.1 Profile ingestion

| ID | Requirement | Verified by |
|---|---|---|
| FR-1.1 | Import a CV from PDF, DOCX, TXT or MD and extract text. | `unit/business/test_ingestor_documents.py` |
| FR-1.2 | Parse a CV into skills, experience, projects, education and credentials **without** an LLM. | `unit/business/test_field_location_agnostic.py` |
| FR-1.3 | Parse a **non-technical** CV (e.g. nurse) with equal fidelity. | `unit/business/test_field_location_agnostic.py` |
| FR-1.4 | Import from GitHub, a portfolio URL, a LinkedIn export, raw text, or a JSON profile. | `test_github_ingestor.py`, `test_portfolio_ingestor.py`, `regression/test_regression_api_profile.py` |
| FR-1.5 | Accept any reasonable JSON shape (JSON Resume, camelCase, native) and report what was imported. | `unit/business/test_ingestion_hardening.py` |
| FR-1.6 | Re-ingesting must not duplicate entities. | `unit/business/test_ingestion_dedup.py` |
| FR-1.7 | Persist to the graph and vector stores; deletions must not resurrect. | `regression/test_profile_delete_consistency.py` |
| FR-1.8 | Link projects to the skills they evidence, including via non-`stack` fields. | `regression/test_project_skill_linking.py` |
| FR-1.9 | Reject SSRF targets on any user-supplied URL. | `unit/common/test_url_guard.py` |

### 3.2 Discovery

| ID | Requirement | Verified by |
|---|---|---|
| FR-2.1 | Discover jobs from multiple sources with **no API key configured**. | `unit/business/test_keyless_multisource_scan.py` |
| FR-2.2 | Keyless sources default to enabled; only an explicit falsey value opts out. | `test_keyless_multisource_scan.py::test_free_sources_enabled_default_on` |
| FR-2.3 | Support ATS connectors, RSS/API boards, HN, GitHub and Reddit. | `test_sources_ats.py`, `test_discovery_sources.py` |
| FR-2.4 | Work for any field and any region, derived from the CV — no hard-coded market. | `unit/business/test_field_location_agnostic.py` |
| FR-2.5 | Reject non-job content before persistence. | `unit/business/test_quality_gate_freshness.py`, `regression/test_lead_hygiene.py` |
| FR-2.6 | Deduplicate by canonical URL. | `unit/business/test_dedup_canonical.py` |
| FR-2.7 | A failing source must not abort the scan. | `regression/test_regression_discovery_sources.py` |
| FR-2.8 | A scan must be stoppable, and stop promptly. | `unit/service/test_api.py` |

### 3.3 Ranking

| ID | Requirement | Verified by |
|---|---|---|
| FR-3.1 | Score every lead with an evidence-backed fit score and a stated reason. | `unit/business/test_scoring_engine_invariants.py` |
| FR-3.2 | Score candidate-relative and field-agnostic — no technology blocklist. | `unit/business/test_cgfe_field_agnostic.py` |
| FR-3.3 | Produce a deterministic score when no LLM is available. | `unit/business/test_evaluator_prefilter.py` |
| FR-3.4 | Expose score provenance (which engine produced it). | `unit/business/test_semantic_mode_surfacing.py` |
| FR-3.5 | Send only the top-K leads to the LLM, to bound cost. | `unit/business/test_evaluator_prefilter.py` |
| FR-3.6 | Feed thumbs up/down back into ranking; recomputes must be idempotent and coalesced. | `test_feedback_recompute.py`, `test_feedback_relearn_coalesce.py` |
| FR-3.7 | Honour an explicit minimum score of zero (not treated as "unset"). | `regression/test_explicit_min_score_zero.py` |
| FR-3.8 | Degrade semantic matching to hashing and **say so**. | `unit/data/test_embedding_honesty.py` |

### 3.4 Generation

| ID | Requirement | Verified by |
|---|---|---|
| FR-4.1 | Generate a tailored resume and cover letter per lead. | `unit/business/test_generation_service.py` |
| FR-4.2 | Generate useful artifacts for non-technical roles. | `unit/business/test_generation_non_tech_artifacts.py` |
| FR-4.3 | Render deterministic PDFs, with style presets. | `regression/test_regression_generation_pdf.py`, `test_resume_style_presets.py` |
| FR-4.4 | Report keyword coverage (asked-for vs incorporated). | `unit/business/test_generation_generators.py` |
| FR-4.5 | Generate outreach (founder message, LinkedIn note, cold email). | `unit/business/test_generation_generators.py` |
| FR-4.6 | Keep versioned assets and let the user retrieve any version. | `unit/service/test_api.py` |
| FR-4.7 | Block generation with a clear reason when prerequisites are missing. | `unit/business/test_startup_leadstore_generation_readiness.py` |
| FR-4.8 | On transient failure keep the lead retryable; never report success on a failed save. | `unit/service/test_api.py` |
| FR-4.9 | Cap outreach volume. | `unit/business/test_outreach_caps.py` |

### 3.5 Pipeline and application

| ID | Requirement | Verified by |
|---|---|---|
| FR-5.1 | Track lead status through the pipeline and persist transitions. | `unit/service/test_api.py` |
| FR-5.2 | Schedule and surface follow-ups. | `unit/service/test_api.py` |
| FR-5.3 | Read an application form and pre-fill from the profile. | `unit/business/test_automation_service.py` |
| FR-5.4 | Preview a submission before it is sent; never submit unreviewed. | `unit/business/test_actuator_vision_safety.py` |
| FR-5.5 | Export the pipeline to CSV. | `unit/service/test_api.py` |
| FR-5.6 | Accept a manually pasted job and optionally generate immediately. | `unit/service/test_api.py` |

### 3.6 Transparency and control

| ID | Requirement | Verified by |
|---|---|---|
| FR-6.1 | Report the real state of every subsystem. | `regression/test_phase3_degradation.py` |
| FR-6.2 | Show what the system learned from feedback. | `unit/business/test_learning_insights.py` |
| FR-6.3 | Render the profile knowledge graph, and never as a blank canvas when a snapshot exists. | `unit/data/test_graph.py`, `unit/business/test_graph_service_helpers.py` |
| FR-6.4 | Let the user choose the LLM provider and model, including local Ollama. | `unit/adapter/test_model_catalog.py`, `test_provider_allowlist.py` |
| FR-6.5 | Let the user delete all local data. | `unit/data/test_data_reset.py` |
| FR-6.6 | Stream live progress for long operations. | `unit/service/test_ws_auth.py` |

---

## 4. Non-functional requirements

### 4.1 Security

| ID | Requirement | Verified by |
|---|---|---|
| NFR-S1 | Bind loopback only; reject non-loopback `Host`. | `regression/test_security_hardening.py` |
| NFR-S2 | Require a bearer token on every route except `/health`, including WS upgrades. | `unit/service/test_api.py::TestAuthGate`, `test_ws_auth.py` |
| NFR-S3 | Never return internal exception detail to the client. | `regression/test_security_hardening.py` |
| NFR-S4 | Never log secrets, tokens, full payloads or source. | `unit/common/test_telemetry_metrics.py` |
| NFR-S5 | Rate-limit generation, manual leads, help chat and error reporting. | `unit/service/test_rate_limit_retry_after.py` |
| NFR-S6 | Validate and guard every outbound user-supplied URL. | `unit/common/test_url_guard.py` |
| NFR-S7 | Bound the size of client-supplied error reports. | `unit/service/test_api.py` |

### 4.2 Reliability

| ID | Requirement | Verified by |
|---|---|---|
| NFR-R1 | No silently swallowed exceptions in critical modules. | `regression/test_stability_manifest.py` |
| NFR-R2 | Never mark a lead complete unless its assets persisted. | `unit/service/test_api.py` |
| NFR-R3 | Survive a locked or missing store without data loss. | `regression/test_phase0_data_integrity.py`, `test_phase2_data_safety.py` |
| NFR-R4 | Serialise graph access; no concurrent writers. | `unit/data/test_graph_connection_locking.py` |
| NFR-R5 | Atomic job-store updates. | `unit/data/test_job_store_atomic.py` |
| NFR-R6 | Reserve the port before announcing it (no TOCTOU steal). | `unit/service/test_port_reserve.py` |

### 4.3 Performance

| ID | Requirement | Verified by |
|---|---|---|
| NFR-P1 | No blocking I/O on the event loop. | `unit/business/test_discovery_async_db.py` |
| NFR-P2 | Bound LLM calls per scan. | `unit/business/test_evaluator_prefilter.py` |
| NFR-P3 | Coalesce feedback recomputes. | `unit/business/test_feedback_relearn_coalesce.py` |
| NFR-P4 | Keep the default graph read snapshot-only. | `unit/service/test_api.py::TestGraphEndpoint` |
| NFR-P5 | Bound graph snapshot size. | `unit/data/test_graph_snapshot_budget.py` |
| NFR-P6 | Reap dead connections from the SQLite pool. | `unit/data/test_connection_pool_reap.py` |

### 4.4 Maintainability

| ID | Requirement | Verified by |
|---|---|---|
| NFR-M1 | Dependencies point downward across layers only. | `unit/architecture/test_import_boundaries.py` |
| NFR-M2 | `core/` depends on no project package. | same |
| NFR-M3 | Routers contain no business logic (size-ratcheted). | same |
| NFR-M4 | One router module per feature; no grab-bags. | same |
| NFR-M5 | The UI never builds a backend URL itself. | `src/api/api-layer.test.ts` |
| NFR-M6 | ≥60% overall backend coverage enforced in CI. | `.github/workflows/ci.yml` |

### 4.5 Privacy

| ID | Requirement |
|---|---|
| NFR-V1 | CV, leads and generated documents stay on the device. |
| NFR-V2 | The only outbound destinations are public job sources and the user's chosen LLM provider. |
| NFR-V3 | No telemetry is sent off-device. |
| NFR-V4 | The user can erase everything from within the app. |

---

## 5. Traceability

Every requirement above names a test. Run the layer that covers a requirement
group directly:

```bash
cd backend
uv run python -m pytest tests/unit/business -q     # FR-2, FR-3, FR-4
uv run python -m pytest tests/unit/service -q      # FR-5, NFR-S
uv run python -m pytest tests/unit/architecture -q # NFR-M
uv run python -m pytest tests/regression -q        # previously-fixed behaviour
```
