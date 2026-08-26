# Architecture

JustHireMe is a local-first desktop app with a Tauri shell, React frontend, and Python backend sidecar.

> This page is the short overview. For the full design set see
> **[HLD](HLD.md)** (context, components, failure modes) ·
> **[LLD](LLD.md)** (module design, schemas, hazards) ·
> **[SRS](SRS.md)** (requirements traced to tests) ·
> **[UML](UML.md)** (diagrams) ·
> **[LAYERS](LAYERS.md)** (the enforced dependency rules).

## High-Level Flow

```text
Profile ingestion
  -> Kuzu graph + LanceDB vectors
  -> Source scrapers
  -> Lead quality gate
  -> Fit ranking / semantic matching
  -> Customization package generation
  -> Local CRM and review UI
```

## Frontend

The React app in `src/` is responsible for:

- navigation and workspace UI
- lead cards and filters
- settings
- profile and ingestion screens
- customization package review
- WebSocket event display

The frontend talks to the backend through authenticated local HTTP requests. Tauri provides the backend port and API token at runtime.

## Backend

The Python backend in `backend/` is responsible for:

- FastAPI routes
- source scraping
- quality gating
- ranking and evaluation
- profile ingestion
- vector search fallback behavior
- PDF and outreach generation
- local persistence

Important modules:

- `backend/automation/free_scout.py`: direct/free source scraping
- `backend/automation/scout.py`: broader source scraping orchestration
- `backend/discovery/quality_gate.py`: pre-save quality checks
- `backend/ranking/scoring_engine.py`: deterministic fit scoring
- `backend/ranking/semantic.py`: LanceDB semantic matching and fallback behavior
- `backend/generation/service.py` and `backend/generation/generators/`: resume, cover letter, outreach, and package generation
- `backend/data/repository.py`: repository facade for local persistence
- `backend/data/sqlite/`, `backend/data/graph/`, and `backend/data/vector/`: SQLite, Kuzu, and LanceDB access helpers

## Storage

Local storage includes:

- SQLite for leads, settings, events, generated asset metadata
- Kuzu for profile graph data
- LanceDB for profile vectors
- local files for generated PDFs

These files should not be committed or uploaded in public issues.

## Experimental Automation

Browser automation exists as a contributor lab and is intentionally separate from the core OSS promise. The supported workflow is scraper, ranker, vector matching, and customizer.
