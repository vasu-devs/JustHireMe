# Changelog

## 1.3.0 - 2026-07-03

- Gets better the more you use it. Thumbs-up / thumbs-down on a lead now moves the actual match score, not just a hidden signal: every still-open lead is instantly re-ranked from what your feedback taught the app (jobs, companies, and stacks like the ones you liked rise; ones like those you disliked fall). Re-ranking is idempotent — it always works from the original evaluator score, so repeated feedback never double-counts.
- Real jobs in any field, with no API key. The zero-config discovery backbone is more reliable and returns relevant, deduplicated leads for any profession and country out of the box — a keyless aggregator plus auto-seeded company boards, with a cleaned role query and strict title matching so results actually match your field instead of drifting into noise. New keyless ATS adapters: SmartRecruiters, Recruitee, and Personio.
- Genuinely field-agnostic ranking. Matches are scored relative to your own profile's field and level, so a nurse, electrician, accountant, teacher, or chef surfaces their real best-fit roles (non-technical experience is weighted fairly, tenure is read from prose, and a symmetric off-field cap keeps clearly-wrong-field postings out of your list for every profession — not just software).
- Meaning-level matching on by default. The local ONNX semantic embedding model now auto-downloads in the background at first launch, so ranking understands the meaning of a posting out of the box (it falls back to fast hashing until the model is ready, then upgrades automatically — no setup, no key).
- Lower LLM cost. Fit evaluation now spends the model only on the top leads by a cheap local pre-score, and the per-lead prompt was slimmed and reordered — roughly 78% fewer evaluation tokens per scan on a typical run, so running the intelligence on your own subscription or API key stays cheap. Advanced knobs: `max_llm_evaluations`, `ghost_max_llm_evaluations`, `llm_eval_floor`.
- Field-neutral application materials. When the language model is unavailable, the fallback résumé and cover letter no longer leak software-specific phrasing into non-technical applications.
- Security and reliability hardening. SSRF guards now abort every outbound request type (not just document fetches), private-host navigation is blocked in the crawler and actuator browser paths, and the desktop shell only kills a stale sidecar process once it has confirmed the process is actually ours — plus roughly 68 correctness fixes from a deep recursive audit across discovery, ranking, generation, the vector store, the profile graph, and the UI.

## 1.2.0 - 2026-06-22

- Keyless, zero-config discovery by default. The free ATS/community/RSS sources (Greenhouse, Lever, Ashby, Workable, RemoteOK, Remotive, Jobicy, Hacker News, GitHub, RSS/Atom, …) are enabled out of the box, so a brand-new profile in any field or country gets real, deduplicated leads with no API key. A neutral, field-agnostic quality gate keeps discovery unbiased across professions.
- Lighter runtime. Dropped the unused heavy ML stack (torch and friends) in favor of the bundled ONNX embedding model, shrinking the first-run runtime download while keeping local semantic matching keyless.
- Broader keyless model options and a feature test matrix to keep the keyless/subscription paths honest across releases.

## 1.1.1 - 2026-06-14

- Codex (ChatGPT) subscription: use the models your account actually supports. ChatGPT-account Codex only allows its own default model (gpt-5.5 as of June 2026); the older `gpt-5-codex`/`gpt-5.1`/`gpt-5` options were rejected with "not supported when using Codex with a ChatGPT account." The model picker now offers the supported set (default = your codex config's own model), and if a selected model is ever rejected the app transparently retries on your account's default instead of failing. Verified end-to-end: résumé ingestion, fit scoring, and text generation all run on the Codex subscription.
- Fixed a noisy "suppressed exception … invalid literal for int()" line appearing in the activity stream during scans. An unset numeric setting is now treated as its default silently instead of being logged as an error.

## 1.1.0 - 2026-06-13

- Works for any field, anywhere. Ranking, discovery, and résumé parsing are no longer biased toward software jobs. Scoring is now judged relative to your own profile's field instead of a fixed tech vocabulary, so a nurse, electrician, accountant, teacher, or chef is scored on their real merits (previously such roles were hard-capped at a low score as "not a technical opportunity"). Discovery and the no-LLM résumé parser recognize occupations across every field.
- Location-aware discovery for any region. Your job-search location is detected from your résumé (or set explicitly in onboarding/Settings) and injected into searches worldwide, with a remote / hybrid / onsite preference. The old India/Global toggle is generalized to any city or country.
- Run the whole app on your ChatGPT (Codex) or Claude subscription — no API key. The Codex provider now works end to end: it talks to the local `codex` CLI over stdin (fixing Windows command-line mangling), reads clean output, and no longer forces an unsupported model. Pick "Codex · sub" in Settings.
- Fixed the bundled backend failing to start on some installs ("Application startup failed"). Several internal modules loaded dynamically weren't being packaged into the sidecar; they are now bundled explicitly.
- Fixed résumé upload sometimes failing with "'C' object has no attribute 'n'" when the language model was unavailable. The fallback now degrades cleanly to the built-in parser instead of crashing.
- Security hardening: SSRF guards on all outbound fetches and custom LLM endpoints, XML parsing hardened against entity-expansion attacks, upload size caps, loopback-only host checks, rate limits on more endpoints, and assorted correctness fixes across the data and generation layers.

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
