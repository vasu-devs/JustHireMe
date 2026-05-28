# Changelog

## 1.0.42 - 2026-05-28

- Fixed CI: two backend tests still used very short placeholder job descriptions that tripped the stricter generation-readiness check added in 1.0.39, turning the test suite red on main even though releases built fine. Gave those fixtures realistic descriptions. No change to app behavior.

## 1.0.41 - 2026-05-27

- Reworked the dark theme so it no longer looks flat and muddy. Surfaces now sit on a clear elevation ramp (cards and panels visibly lift off a deeper base), borders are crisper, text contrast is stronger, and the dashboard's hero and stat cards use richer jewel-tone darks instead of washed-out browns. Light mode is unchanged.

## 1.0.40 - 2026-05-27

- Added a full dark mode. Switch it from the new sun/moon button in the top bar or from Settings → Appearance (Light / Dark / System). The default follows your operating system and updates live when the OS theme changes; an explicit choice is remembered across launches and applied before first paint (no flash of the wrong theme). The whole app is themed via design tokens — dashboard, pipeline, profile, knowledge graph, activity log, settings, and onboarding — with a warm dark palette that keeps the product's character. (#92)

## 1.0.39 - 2026-05-25

- Fixed "Customize One Job" rejecting valid non-technical roles with "Paste a fuller job description before generating." The pre-generation readiness check required software/engineering keywords (engineer, python, react, ...), so complete descriptions for non-tech roles — e.g. a "Financial Aid Advisor" posting — were wrongly blocked. Generation readiness now gates on the substance of the description (length and word count) instead of a tech-keyword whitelist, so any field is supported. (#92)
- Fixed the "Export Graph" button doing nothing on Linux. Tauri's Linux webview (WebKitGTK) silently ignores programmatic `<a download>` clicks, so no file was ever produced. The export now hands the file to the system opener inside the desktop app — the same path the resume "Download PDF" button uses — and keeps the direct-download anchor for browser/dev use. (#92)

## 1.0.38 - 2026-05-25

- Fixed first-run runtime pack download failing on macOS (and hardened the same path on Linux) with `SSL: CERTIFICATE_VERIFY_FAILED — unable to get local issuer certificate`. The bundled sidecar Python has no system CA store wired into OpenSSL, so the HTTPS download to GitHub could not verify the server certificate. The downloader now builds its SSL context from certifi's CA bundle, which is collected into the packaged sidecar. Windows was unaffected because it falls back to the OS certificate store.

## 1.0.37 - 2026-05-25

- Thin installer + first-run runtime download: the heavy runtime pack (Chromium + vector libs + embedding model) is no longer bundled into the installer. It is content-versioned and fetched on first run, then cached, so routine app updates no longer re-download it. Windows installer ~450 MB → ~102 MB; macOS ~718 MB → ~101 MB.

## 1.0.36 - 2026-05-24

- Hardened resume/GitHub ingestion: PDF text extraction now preserves page line breaks, resume heuristics avoid splitting one role into multiple experience entries, education lines merge into one school record, and GitHub stack cleanup rejects repo metadata/noise like forks, maintained-through dates, package filler, and verbs.
- GitHub and profile ingestion no longer use fixed client/backend scan timeouts; the UI shows an active progress panel while long imports run, and ingestion responses now wait for Kùzu graph correlation rebuilds plus Lance vector sync before triggering Profile/Knowledge refreshes.

## 1.0.35 - 2026-05-24

- Reworked rapid profile-delete handling: replaced the serial delete queue with a single in-flight lock so only one delete runs at a time. The clicked row stays visible with a "Deleting..." loader, every other delete button is disabled, and the UI does not unlock until the backend delete and profile refresh both finish.
- Hardened packaged sidecar startup: release builds now resolve the bundled backend from the actual install/resource paths and report the checked paths when it is missing, and the pre-package sidecar check rejects stale, mismatched, or placeholder binaries before packaging.

## 1.0.34 - 2026-05-24

- Fixed profile items (skills, projects, experience, education, certifications) failing to delete when delete buttons were clicked rapidly. Rapid clicks fired concurrent backend deletes that contended for the Kùzu graph lock; the 1.5s lock timeout starved later requests, which silently failed so nodes were never removed (they returned in the UI on navigation and stayed in the knowledge graph).
- Frontend now serializes deletes through a queue: rapid clicks hide each item immediately with a per-item loader, but the backend DELETE requests run one at a time, with a single profile + knowledge-graph refresh after the whole batch completes.
- Raised the graph lock acquisition timeout from 1.5s to 30s so concurrent graph operations wait for the lock instead of failing.

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
