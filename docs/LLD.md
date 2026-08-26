# Low-Level Design — JustHireMe

Module-level design. Read [HLD.md](HLD.md) first for context and
[LAYERS.md](LAYERS.md) for the dependency rules this document assumes.

---

## 1. Service layer — `backend/api/`

### 1.1 Composition

`api/app.py::create_app` is the only place routers are mounted. It takes its
collaborators by parameter (lifespan, token getter, scheduler, connection
manager, logger) rather than importing singletons, so tests build an app with
fakes and no global state.

Routers come in two shapes:

- **Module-level `router`** — for features with no runtime collaborators
  (`profile`, `graph`, `help`, `learning`, `events`, `runtime`).
- **`create_router(...)` factory** — for features that need the WebSocket
  connection manager, scheduler or logger closed over
  (`leads`, `discovery`, `generation`, `automation`, `ingestion`, `settings`,
  `templates`, `health`, `diagnostics`).

### 1.2 Request path

```
request
  → TrustedHostMiddleware      reject non-loopback Host
  → CORSMiddleware             local webview origin only
  → require_http_token         bearer check (except /health)
  → router handler             parse + delegate  (no storage access)
  → business service           domain rules, raises core.errors
  → repository                 storage
```

Routers never import `data`/`models` — enforced by
`test_routers_never_reach_past_the_business_layer`. The only place that
constructs data access is the composition root, `api/dependencies.py`, which
builds each service from an injected `Repository`.

Two exception handlers sit on the app:

- `JustHireMeError` → the status from `core.errors.http_status_for` (404 / 400 /
  422 / 409). This is the transport boundary: domain code raises types, not
  status codes, and never imports `fastapi`.
- `Exception` → records the exception server-side and returns
  `{"detail": "Internal server error", "request_id": ...}`. Internal text never
  reaches the client.

### 1.3 Dependency providers

Every provider takes its collaborators through `Depends`, e.g.

```python
def get_lead_service(repo: Repository = Depends(get_repository),
                     ranking_service=Depends(get_ranking_service)):
    return create_lead_service(repo, ranking_service)
```

They are deliberately **not** `lru_cache`d over a module-level
`get_repository()` call: a cached instance captures the real repository forever,
so an override (a test, or any alternate wiring) is silently ignored and the
service keeps talking to the production database.

### 1.4 Route ordering hazard

FastAPI matches the first registered route. `/leads/manual/generate/start` and
`/leads/{job_id}/generate/start` have the same shape — the literal **must** be
registered first, or `job_id` captures `"manual"`. This is enforced by ordering
inside `generation.py` and called out in a comment there.

### 1.5 Long-running work

Generation, scanning and application submission exceed a sane HTTP timeout, so
they follow one pattern:

1. Validate synchronously; return `{"status": "started", ...}` immediately.
2. Run the work in a tracked `asyncio.Task` (held in a module-level set so it is
   not garbage-collected mid-flight).
3. Broadcast progress and the terminal result over WebSocket.

The orchestration itself lives in the business layer
(`generation.orchestrator`, `discovery.orchestrator`); the router passes in a
`notify` callback that wraps `manager.broadcast`, so domain code fans out
progress without knowing a WebSocket exists.

Every blocking SQLite/Kùzu call inside those tasks goes through
`asyncio.to_thread`. The sidecar is single-worker: a blocking call on the event
loop stalls *every* coroutine including `/health`, which the UI then reports as
"backend unreachable".

---

## 2. Business layer

### 2.1 Discovery — `backend/discovery/`

```
orchestrator.py the scan/re-evaluate use cases + their task registry
service.py      orchestration: query gen → sources → normalise → gate → persist
query_gen.py    turns the profile into source-appropriate queries
sources/        one adapter per source, all behind sources/base.py
  ats.py        Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio
  rss.py        RemoteOK, Remotive, Jobicy, WeWorkRemotely
  hackernews.py github_jobs.py reddit.py x_twitter.py web.py custom.py apify.py
normalizer.py   source payload → canonical lead shape
quality_gate.py pre-save rejection (non-jobs, spam, dead links)
lead_intel.py   manual paste → structured lead
```

A source failure is contained: the adapter records the error, the aggregator
counts it, and the scan continues with the remaining sources.

**Dedupe** is canonical-URL based, applied before persistence.

### 2.2 Ranking — `backend/ranking/`

The scoring path is candidate-relative and field-agnostic by design; nothing in
it hard-codes a technology list.

```
service.py           entry point used by the API and the scan
evaluator.py         LLM evaluation with top-K gating (cost control)
scoring_engine.py    deterministic score, always available
fit/engine.py        CGFE: coverage-grounded fit evaluation
fit/extract.py       requirement extraction from job text
criteria/            pluggable criteria, registered in registry.py
  stack_coverage · role_alignment · seniority_fit · evidence · logistics · learning_curve
semantic.py          LanceDB similarity, with hashing fallback
feedback_ranker.py   applies thumbs up/down as a learned signal
graph_enrichment.py  pulls supporting evidence out of the profile graph
```

**Cost control:** only the top-K leads by deterministic score are sent to the
LLM (`max_llm_evaluations`); the rest keep their deterministic score, tagged
`scored_by: deterministic_fallback` so the provenance is visible in the UI.

**Feedback loop:** saving feedback triggers a coalesced re-rank
(`api/routers/leads.py::_run_relearn`) — at most one recompute runs at a time,
concurrent requests just mark it dirty. Without this, bulk feedback clicks each
spawned a full 500-lead recompute contending on the SQLite write lock.

### 2.3 Generation — `backend/generation/`

```
orchestrator.py            the "generate for this lead" use case (persistence rules)
service.py                 generate_with_contacts: package + contact lookup
generators/package.py      assembles the full package
generators/resume.py       tailored resume content
generators/cover_letter.py
generators/keywords.py     keyword coverage analysis (what the JD asked for vs what we said)
generators/outreach_email.py · founder_message.py · linkedin_message.py
pdf_renderer.py            deterministic PDF layout
contact_lookup.py          Hunter.io + Proxycurl enrichment (optional, key-gated)
```

`orchestrator.py` holds the use case: `GenerationOrchestrator.generate()` is the
transactional heart. `save_asset_package` is the only write that flips a lead to
`approved` and records the asset path, so if it fails the whole generation is
treated as failed rather than reporting success over an unchanged DB row.

Failures are classified transient vs permanent (`is_transient_generation_error`).
Transient leaves the lead in `tailoring` with `Retry-After`; permanent reverts to
`discovered`. The orchestrator raises the real exception; the router turns it
into 503-with-Retry-After or 500.

### 2.4 Profile — `backend/profile/`

```
ingestor.py           entry point
ingest_documents.py   PDF/DOCX/TXT/MD text extraction
ingest_parse.py       deterministic parse (no LLM required)
ingest_store.py       write-through to graph + vectors
normalization.py      skill canonicalisation, dedupe, caps
github_ingestor.py    repos → projects
portfolio_*.py        SSRF-guarded crawl → extract → import
linkedin_parser.py    LinkedIn export archive
```

Caps are deliberate: skills 100, and experiences/projects deduped on
role+company / title. Unbounded imports previously produced graphs too large to
render and embeddings dominated by noise.

### 2.5 Graph service — `backend/graph_service/`

`stats.py::graph_stats_payload(repo, repair=False)` builds the Knowledge page
payload. The default read is a pure snapshot; `repair=True` additionally purges
deletion tombstones and re-syncs leads, profile relationships and vectors.

Deleted items are hidden at **read** time (`_apply_graph_deletions`,
`_apply_embedding_deletions`) and only physically purged on an explicit repair —
so the common path stays fast while a deleted skill never reappears on the
Knowledge page.

---

## 3. Data layer — `backend/data/`

`repository.py` is the facade: `repo.leads`, `repo.settings`, `repo.profile`,
`repo.graph`, `repo.vector`, `repo.feedback`, `repo.resume_templates`. Business
modules depend on this, never on a driver.

### 3.1 SQLite

```sql
leads(job_id PK, title, company, url, platform, status DEFAULT 'discovered',
      score INTEGER DEFAULT 0, reason, match_points, asset_path,
      cover_letter_path, selected_projects, description, gaps,
      resume_version INTEGER DEFAULT 0, created_at)
events(id PK AUTOINCREMENT, job_id, action, ts)
settings(key PK, val)
error_log(id PK AUTOINCREMENT, ...)
metrics(...)
schema_migrations(...)
```

Connections come from a pool that reaps dead threads. Writes are serialised by
SQLite's own locking; the busy timeout is why every call is off-loop.

### 3.2 Kùzu (profile graph)

Nodes: `Candidate`, `Skill`, `Project`, `Experience`, `Education`,
`Certification`, `Achievement`, `JobLead`.

Edges: `HAS_SKILL`, `BUILT`, `WORKED_AS`, `HAS_EDUCATION`, `HAS_CERTIFICATION`,
`HAS_ACHIEVEMENT`, `PROJ_UTILIZES`, `EXP_UTILIZES`, `ACHIEVEMENT_USES`,
`CERTIFIES`, `EDUCATES`, `REQUIRES`, `RELATED_SKILL`, `SIMILAR_PROJECT`,
`PROJECT_SUPPORTS_EXPERIENCE`.

All graph access is funnelled through `data/graph/connection.py::run_graph`,
which serialises work onto a single executor — Kùzu does not tolerate concurrent
writers.

### 3.3 LanceDB (vectors)

Tables mirror the profile entities (`profile`, `candidates`, `skills`,
`projects`, `experiences`, `credentials`). `data/vector/embeddings.py` picks the
provider (ONNX local → OpenAI → hashing) and **reports which one is live**.
Hashing is a real fallback, not a pretend embedding, and is surfaced as degraded.

---

## 4. Adapter layer — `backend/llm/`

`client.py` is the single call site; `providers/` holds one adapter each for
Anthropic, Gemini, Groq, Ollama and OpenAI-compatible endpoints.
`model_catalog.py` serves the picker from a keyless catalog so models can be
browsed before a key is entered. `subscription_cli.py` supports
subscription-based CLIs instead of API keys.

Retries are bounded and classify transient vs permanent; Anthropic prompt
caching is used to cut repeated-context cost.

---

## 5. Frontend — `src/`

```
api/          service layer, one module per backend router (see LAYERS.md rule 7)
features/     one folder per view: dashboard, pipeline, profile, apply, graph, learning, settings
shared/       components, hooks (useLeads, useWS, useGraphStats, useDueFollowups), lib, context
preview/      PreviewHarness — renders real views against mock data via ?preview=1
demo/         standalone demo skin
```

`useWS` holds the WebSocket and fans events out as DOM CustomEvents
(`lead-updated`, `leads-refresh`, `graph-refresh`, …). Hooks listen and refetch.
`useGraphStats` debounces those bursts by 800 ms — a scan broadcasts one event
per scored lead, and each refetch hits the expensive graph snapshot.

Optimistic updates are applied locally *as well as* awaiting the broadcast,
because the socket may be mid-reconnect when the click lands.

---

## 6. Cross-cutting

**Config** — `core/config.py` reads settings from SQLite with env fallback.
Secrets are never written to logs; `core/telemetry.py` redacts and truncates.

**Logging** — structured JSON with levels. Boundary events only. Every
`except Exception` in a critical module must log or re-raise; this is enforced
by `tests/regression/test_stability_manifest.py`.

**Caching** — LLM responses cache per prompt (`test_llm_client_cache`); the
model catalog caches with a TTL; graph reads are snapshot-cached and invalidated
by explicit repair. Nothing stale is served as authoritative.

**Complexity** — the hot paths are the scan (O(sources × pages)) and the
re-rank (O(leads)). Dedupe and skill matching use sets/maps, not nested scans.
The feedback re-rank is coalesced rather than run per click.
