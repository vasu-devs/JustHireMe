# Changelog

## 1.0.33 - 2026-05-24

- Fixed resume ingestion duplicating one job into several near-identical experience entries: experiences are now normalized and de-duplicated on a content key (role+company), and education de-dupes ignoring spacing/punctuation.
- Fixed genuine projects being dropped during ingestion: a project with its own repo, real stack, or substantial impact is no longer absorbed into the previous entry or discarded for a detail-like title.
- Fixed GitHub import stalling/timing out for users without a token: unauthenticated scans now skip the recursive tree + manifest fetches (which blew GitHub's ~60 requests/hour limit) and rely on README + language signals, completing reliably; full dependency analysis still runs when a token is provided. Increased scan concurrency and aligned client/backend timeouts.
- Made the Knowledge graph reflect profile deletions faster by skipping the redundant per-read tombstone purge (read-time filtering already hides deleted items; the hard purge runs on repair/ingest).

## 1.0.32 - 2026-05-24

- Fixed the profile delete bug: deleted skills/projects/experience no longer linger on the Knowledge page or reappear on the Profile page. Deletion tombstones are now applied to the graph snapshot and embedding-space read paths, and the delete UI keeps a loader until the backend-confirmed profile reloads.
- Ingestion now rebuilds derived graph correlations (related skills, similar projects, project↔experience, credential↔skill) and re-embeds the profile after every source (resume, GitHub, LinkedIn, JSON import).
- Surfaced the active embedding mode in evaluation reasoning so hash-fallback scores read as "runtime not installed," not a poor fit.
- Added user-managed resume templates: upload your own resumes (PDF/DOCX) as reusable style guides, set a default, and pick one per job at generation time.
- Moved the canonical skill alias map to the data layer to respect module import boundaries; made the GitHub ingestor enrichment-cap test derive its expectations from the configured limits.
- Simplified the runtime-pack install banner and removed dead formatting helpers.

## 1.0.31 - 2026-05-22

- Fixed graph profile recovery so stale or partially-ingested vector rows no longer shadow the live graph state.
- Improved semantic matching score normalization for hash-embedded profiles versus sentence-transformer profiles.
- Added bad-vector-label pruning to prevent placeholder or template text from polluting vector search results.
- Added regression tests for semantic scoring and vector connection edge cases.

## 1.0.30 - 2026-05-22

- Fixed runtime startup so the vector store initializes reliably when LanceDB is available but the module cache is stale.
- Added health endpoint diagnostics for app data directory resolution and vector store readiness.
- Added lazy-import guard in the vector store package init to avoid circular import failures.
- Updated the SemanticRuntimePrompt polling timeout to 90 seconds for slower first-run extractions.

## 1.0.29 - 2026-05-22

- Hardened all data layer modules against missing or relocated app data directories on first launch.
- Fixed graph connection to re-derive its base directory when the app data path changes between sessions.
- Added path resolution tests for app data directory across bundled and development environments.

## 1.0.28 - 2026-05-21

- Bundled the runtime pack directly into desktop installers so first-run extraction no longer requires an internet download.
- Added Tauri resource embedding for the runtime pack zip and extraction logic in the Rust sidecar launcher.
- Updated CI release workflow to build and embed the runtime pack per-platform before packaging installers.

## 1.0.27 - 2026-05-21

- Fixed Windows update shortcut metadata so Start Menu entries survive in-place upgrades.
- Expanded NSIS installer hooks to preserve and restore shortcut properties during updates.
- Added Windows updater smoke tests covering shortcut persistence across upgrade cycles.

## 1.0.26 - 2026-05-21

- Fixed profile graph ingestion so skills, projects, and experience nodes stay consistent after repeated imports.
- Improved graph connection upsert logic to handle duplicate primary key races without data loss.
- Added frontend profile utility tests for graph-to-UI data mapping.

## 1.0.25 - 2026-05-21

- Added profile hydration from graph vectors so the Profile view shows project, skill, and credential rows even when the snapshot is sparse.
- Added bad-vector-label detection to filter out placeholder or template entries from vector-backed profile reads.
- Expanded profile service tests for vector-to-profile round-trip fidelity.

## 1.0.24 - 2026-05-21

- Fixed Windows updater persistence so pending-restart state does not carry over across fresh app launches.
- Added NSIS installer hooks to clean up stale update state during upgrades.
- Added stability component tests for updater restart flow and session storage cleanup.

## 1.0.23 - 2026-05-21

- Stopped automatic graph refreshes from running heavy repair/vector sync work that could trip the 45s UI timeout.
- Added graph-backed profile hydration so Profile shows project, skill, and evidence rows when the graph has them but the profile endpoint is sparse.
- Kept saved profile snapshots visible when graph reads are temporarily busy instead of returning an empty profile.

## 1.0.22 - 2026-05-21

- Fixed OTA runtime readiness so incomplete stale LanceDB payloads no longer count as installed.
- Added runtime-pack verification that imports LanceDB and opens a vector connection before publishing OTA assets.

## 1.0.21 - 2026-05-20

- Repaired the Windows updater flow to retry signed release downloads as a single download-and-install operation after transient response-body decode failures.
- Prevented Windows installer smoke tests from leaving the real JustHireMe uninstall registry entry pointed at a temporary test install.

## 1.0.20 - 2026-05-20

- Fixed the PyO3/LanceDB startup path so native vector import failures degrade to deterministic matching instead of blocking the app behind a restart modal.
- Removed the frontend PyO3 string heuristic that could force a restart even when the backend did not request one.
- Kept the runtime pack installer mandatory only when the pack is actually missing.

## 1.0.18 - 2026-05-20

- Fixed the Tauri ACL regression that blocked runtime-pack and updater restarts.
- Restored the Windows installer to a slim onefile sidecar and kept the heavy vector/browser runtime in the first-run OTA pack.
- Added release guardrails so CI fails if `_internal` is bundled into installers again.

## 1.0.2 - 2026-05-18

- Added the execution and stability records to the repository release branch.
- Fixed Linux CI mypy checks for Windows-only SQLite migration locking.

## 1.0.1 - 2026-05-18

- Added cross-platform `release:smoke` CI coverage across Linux, Windows, and macOS.
- Added profile-to-score-to-generate integration coverage plus startup, lead-store, generation-readiness, and scoring invariant tests.
- Tightened profile parsing utilities by replacing unsafe `as any` casts with explicit unknown narrowing.
- Fixed startup validation so built-in default job targets do not produce false broad-target warnings.

## 1.0.0 - 2026-05-18

- Added thread-local SQLite connection pooling with shutdown cleanup to reduce lock churn.
- Made WebSocket broadcast, event recording, frontend message parsing, and LLM fallback failures visible.
- Replaced race-prone scan/reevaluation globals with an atomic task registry and `/api/v1/status`.
- Isolated graph work onto a dedicated executor with lock timeouts for degraded-but-responsive graph reads.
- Added frontend state reconciliation after WebSocket reconnects plus progress indicators for long scans.
- Added sidecar stale-PID validation and capped auto-restart after crashes.
- Reworked lead row mapping to use SQLite column names instead of positional indexes.
- Added settings validation, local structured diagnostics, and release smoke coverage for core API endpoints.
- Removed the deprecated `backend/db` compatibility facade.
