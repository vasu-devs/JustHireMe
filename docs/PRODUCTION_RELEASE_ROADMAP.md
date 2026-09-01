# Production Release Roadmap

This roadmap turns JustHireMe's current release skeleton into a production-grade release system: stable installers for Windows, macOS, and Linux; signed OTA updates; repeatable CI builds; small first-download packages; and release gates that catch broken builds before users do.

## Release Principles

- Build from tags in CI, not from a maintainer laptop.
- Treat Windows, macOS, and Linux as separate native products with one shared release process.
- Keep the default installer small and reliable. Move heavy or experimental capabilities into optional runtime downloads.
- Make updates boring: signed artifacts, predictable channels, rollback paths, and smoke-tested installers.
- Preserve local-first behavior. User profile data, leads, generated documents, graph data, vector data, settings, API keys, and browser caches stay in the OS app data directory and must survive updates.
- Prefer deterministic release gates over human memory. Every manual checklist item should eventually become a script or CI job.

## Target Release Shape

| Area | Target |
| --- | --- |
| Windows | NSIS installer as the default public download; MSI only for managed deployments |
| macOS | Separate signed and notarized builds for Apple Silicon and Intel |
| Linux | AppImage plus `.deb` |
| Updates | Tauri updater artifacts signed with the updater private key |
| Channels | `stable`, `beta`, and `nightly` update manifests |
| Backend | Bundled Python sidecar for core workflows |
| Heavy features | Optional post-install downloads for browser runtime, local embedding models, and advanced automation |
| Release source | GitHub Actions from immutable `v*` tags |
| Rollback | Previous stable installer and update manifest retained for emergency downgrade instructions |

## Current Gaps To Close

- Version numbers are split across `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, and `backend/pyproject.toml`; backend is currently behind the app version.
- Local `npm run release` does extra Rust work before invoking Tauri packaging.
- CI release logic duplicates sidecar build behavior instead of using `scripts/build-sidecar.mjs`.
- macOS currently uses ad-hoc signing, which is not production-grade for public downloads.
- `latest.json` generation needs complete platform coverage, especially both macOS architectures if both are supported.
- Heavy backend dependencies and generated resources can make the sidecar and installer too large.
- Installer launch smoke testing is still mostly manual.
- Update channels are not separated yet, so a bad tagged release can become the default update for everyone.

## Phase 0 - Define Release Readiness

**Goal:** Make "ready to release" explicit and measurable.

Tasks:

- Create a release definition of done:
  - Frontend typecheck passes.
  - Frontend tests pass.
  - Backend tests pass.
  - Rust check passes.
  - Sidecar builds on every target OS.
  - Installer builds on every target OS.
  - App launches and sidecar reports healthy.
  - Update artifacts and signatures are present.
  - Generated updater manifest is verified against the release assets before publishing.
  - Release notes and checksums are generated.
- Decide supported OS matrix for the next public release:
  - Windows x64.
  - macOS Apple Silicon.
  - macOS Intel, if still supported.
  - Linux x64 AppImage.
  - Linux x64 `.deb`.
- Classify features into release tiers:
  - Core: settings, profile, local lead store, scan, ranking, quality explanations, generated application materials.
  - Optional: browser runtime, advanced scraping, local semantic models, heavyweight vector features.
  - Guarded and opt-in: auto-apply and any site-driving automation.
- Add this release roadmap to maintainer onboarding and link it from the maintainer checklist.

Exit criteria:

- Everyone can tell which features are supported in the next stable release.
- Every release-blocking check is named.
- Optional and experimental features are not accidentally marketed as stable core behavior.

## Phase 1 - One Version Source Of Truth

**Goal:** A tag like `v0.1.29` updates and verifies every versioned file consistently.

Tasks:

- Add a version script, for example `scripts/bump-version.mjs`.
- The script should update:
  - `package.json`
  - `package-lock.json`
  - `src-tauri/tauri.conf.json`
  - `src-tauri/Cargo.toml`
  - `backend/pyproject.toml`
- Add a validation mode:
  - Read the git tag.
  - Read every versioned file.
  - Fail if any file differs from the tag version.
- Add a CI release step before building:
  - For tag `vX.Y.Z`, assert all project versions equal `X.Y.Z`.
- Update `docs/MAINTAINER_RELEASE_CHECKLIST.md` to use the script instead of manual edits.

Recommended commands:

```powershell
npm run version:bump -- 0.1.29
npm run version:check
```

Exit criteria:

- A release cannot start with mismatched frontend, Tauri, Rust, and backend versions.
- Maintainers no longer edit four version fields by hand.

## Phase 2 - Clean Build Commands

**Goal:** Separate fast local smoke builds from real installer builds without duplicated work.

Tasks:

- Replace the current local release scripts with clear modes:
  - `npm run build:frontend`
  - `npm run build:sidecar`
  - `npm run build:tauri`
  - `npm run release:smoke`
  - `npm run release:windows` for CI/tag release packaging or an intentional local packaging rehearsal with updater signing variables available
  - `npm run release:linux`
  - `npm run release:macos`
- Keep `release:smoke` fast:
  - Build frontend.
  - Build sidecar.
  - Build the Tauri binary.
  - Launchable locally, no installer bundling.
- Keep installer scripts honest:
  - Build required assets once.
  - Invoke Tauri packaging once.
  - Do not run a separate redundant `cargo build --release` immediately before `tauri build` unless measured and needed.
- Preserve `tauri.conf.json` with an empty `beforeBuildCommand`; frontend build should be controlled by release scripts and CI.
- Make `scripts/run-parallel.mjs` report timing per lane so slow steps are visible.

Exit criteria:

- Local smoke builds are fast enough for daily testing.
- Installer builds do not compile Rust twice unnecessarily.
- Build logs clearly show frontend, sidecar, Rust, and bundler timings.

## Phase 3 - Use One Sidecar Build Path Everywhere

**Goal:** Local and CI sidecar builds behave the same way.

Tasks:

- Update `.github/workflows/release.yml` to call `npm run build:sidecar` instead of duplicating PyInstaller commands.
- Make `scripts/build-sidecar.mjs` support all CI targets:
  - Windows executable suffix.
  - Unix executable permissions.
  - Rust host triple naming.
  - Clean copying of `_internal`.
  - Clear size summary.
- Add a sidecar manifest file during build:
  - app version
  - backend version
  - platform triple
  - Python version
  - build timestamp
  - key dependency versions
- Add a CI assertion that the built sidecar exists at the exact path Tauri expects.
- Keep packaged sidecar outputs ignored by git.

Exit criteria:

- Sidecar packaging has one owner: `scripts/build-sidecar.mjs`.
- CI and local builds produce the same resource layout.
- A missing or misnamed sidecar fails before installer packaging starts.

## Phase 4 - Reduce Package Size

**Goal:** Keep the first download small while preserving a working core product.

Tasks:

- Split backend dependencies into groups:
  - `core`: FastAPI, uvicorn, httpx, pydantic/runtime needs, SQLite/local storage, deterministic ranking, document generation.
  - `llm`: provider SDKs and structured generation helpers.
  - `graph`: Kuzu and graph-specific packages.
  - `vector`: LanceDB, PyArrow, local embedding dependencies.
  - `browser`: Playwright package and browser runtime integration.
  - `dev`: PyInstaller, pytest, lint/test tooling.
- Build the default sidecar from the smallest dependency set that supports core workflows.
- Make browser runtime a downloaded component stored under app data.
- Make local semantic/vector packages optional if they are too large for the default sidecar.
- Add a release size budget:
  - Core Windows installer target.
  - Core macOS DMG target.
  - Core Linux AppImage target.
  - Optional browser runtime target.
- Add CI size reporting:
  - sidecar executable size
  - sidecar `_internal` size
  - installer size
  - optional browser runtime asset size
- Add a size regression warning threshold, then later make it blocking.

Exit criteria:

- The default installer contains only stable core runtime pieces.
- Heavy features can be enabled after install without blocking first launch.
- CI shows package size changes on every release build.

## Phase 5 - Signed Installers And Trusted Updates

**Goal:** Users can install and update without scary OS trust failures.

Tasks:

- Keep Tauri updater signing separate from OS code signing.
- Store updater signing secrets in GitHub Actions secrets:
  - `TAURI_SIGNING_PRIVATE_KEY`
  - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
- Add Windows signing:
  - Code-sign the application executable.
  - Code-sign the NSIS installer.
  - Timestamp signatures.
- Add macOS signing:
  - Developer ID Application certificate.
  - Hardened runtime.
  - Sign app bundle and sidecar.
  - Notarize DMG or app artifact.
  - Staple notarization result.
- Decide Linux signing policy:
  - Publish SHA256 checksums.
  - Optionally publish detached signatures.
- Add CI preflight checks:
  - Fail stable releases if signing secrets are missing.
  - Allow unsigned builds only on beta/nightly or local smoke workflows.

Exit criteria:

- Stable Windows installer is signed.
- Stable macOS download is signed and notarized.
- Stable updater artifacts are signed and accepted by the app.

## Phase 6 - Update Channels And Rollout Safety

**Goal:** Bad builds do not automatically reach all users.

Tasks:

- Replace single-manifest thinking with channel manifests:
  - `updates/stable/latest.json`
  - `updates/beta/latest.json`
  - `updates/nightly/latest.json`
- Add app-side channel setting:
  - Stable by default.
  - Beta opt-in.
  - Nightly hidden/dev-only unless explicitly enabled.
- Generate channel-specific manifests in release CI.
- Publish stable only from approved version tags.
- Publish beta from pre-release tags like `v0.2.0-beta.1`.
- Publish nightly from scheduled or main-branch workflows.
- Add staged rollout support later:
  - Start at manual download only.
  - Move to beta.
  - Move to stable after smoke testing.
- Document rollback:
  - Pull bad manifest.
  - Repoint stable manifest to previous known-good version.
  - Publish advisory notes.

Exit criteria:

- Stable users only receive intentionally promoted stable builds.
- Beta testers can receive earlier builds without risking everyone.
- There is a written rollback path.

## Phase 7 - Installer And Update Smoke Tests

**Goal:** Catch broken installers before publishing release links.

Tasks:

- Add a headless app smoke mode or CLI flag:
  - Launch app.
  - Start sidecar.
  - Wait for sidecar port and token.
  - Call `/health`.
  - Exit cleanly.
- Add a packaged-app smoke test per OS:
  - Download built artifact.
  - Install or unpack it.
  - Launch the packaged app.
  - Verify sidecar health.
  - Verify app data directory is writable.
- Add an update smoke test:
  - Install previous release.
  - Point updater at a test manifest.
  - Download and install next version.
  - Relaunch.
  - Verify version changed.
  - Verify existing app data survived.
- Keep the release manifest gate in CI:
  - Parse `latest.json`.
  - Verify the manifest version matches the tag.
  - Verify every platform URL points at a local uploaded asset.
  - Verify every manifest signature matches the asset `.sig` file.
- Keep a stable test profile fixture with no private data.
- Add failure artifact uploads:
  - app logs
  - sidecar logs
  - screenshots where possible
  - generated update manifest

Exit criteria:

- CI proves every published installer can launch.
- CI proves the sidecar is usable from the packaged app.
- At least one update path is tested before stable promotion.

## Phase 8 - Data Migration And Local-First Safety

**Goal:** Updates never corrupt or erase user data.

Tasks:

- Add migration tests for every SQLite migration:
  - Fresh install.
  - Upgrade from previous schema.
  - Upgrade with realistic user data.
  - Re-run migration safely.
- Add app data backup before risky migrations:
  - Copy critical SQLite files before schema changes.
  - Keep backup count small.
  - Never upload backup data.
- Add settings migration tests:
  - Existing provider settings.
  - Missing optional settings.
  - New defaults.
- Add graph/vector store compatibility checks:
  - Detect incompatible store versions.
  - Rebuild derived indexes when needed.
  - Preserve source profile and lead data.
- Add update notes for migrations that cannot be reversed.

Exit criteria:

- A user can update from the previous stable version without losing local data.
- Migration failures are recoverable and explainable.
- Derived stores can be rebuilt from canonical local data.

## Phase 9 - Release Observability Without Violating Privacy

**Goal:** Understand release health while keeping the app local-first.

Tasks:

- Keep telemetry off by default unless the product explicitly chooses opt-in diagnostics.
- Add local diagnostics export:
  - app version
  - OS
  - sidecar startup status
  - recent non-secret logs
  - database schema version
  - enabled optional components
- Add a "copy diagnostic report" action that redacts:
  - API keys
  - bearer tokens
  - resume text
  - lead contents
  - cookies
  - local file paths where possible
- Add release issue template fields:
  - OS
  - installer type
  - app version
  - update or fresh install
  - sidecar health status
- Add a local log retention policy.

Exit criteria:

- Users can report problems without sharing private job-search data.
- Maintainers can distinguish installer, updater, sidecar, and app-data failures.

## Phase 10 - Fastest Build Program

**Goal:** Make production builds fast without making releases flaky.

Tasks:

- Add timing output for:
  - `npm ci`
  - frontend typecheck
  - Vite build
  - backend dependency sync
  - PyInstaller analysis
  - PyInstaller collection
  - Rust compile
  - Tauri bundling
  - signing/notarization
- Use caches:
  - npm cache from `package-lock.json`
  - website npm cache from `website/package-lock.json`
  - uv cache from `backend/uv.lock`
  - PyInstaller cache from spec plus lockfile hash
  - Rust cache from `src-tauri/Cargo.lock`
  - optional `sccache` for Rust compiler outputs
- Keep parallel lanes:
  - frontend build
  - sidecar build
  - Rust compile
- Avoid parallelizing steps that fight over the same output directory.
- Add a "release dry run" workflow:
  - Runs on pull requests that touch build/release files.
  - Builds smoke artifacts.
  - Does not sign or publish.
- Add a "full release" workflow:
  - Runs only from tags.
  - Signs, notarizes, generates manifests, and publishes.

Exit criteria:

- Fast local smoke build is optimized for developer feedback.
- Full CI release build is optimized for correctness and cache reuse.
- Build time regressions are visible.

## Phase 11 - Documentation And Maintainer Workflow

**Goal:** Make releases repeatable even when the maintainer is tired.

Tasks:

- Update `docs/MAINTAINER_RELEASE_CHECKLIST.md` to include:
  - version script
  - release channel choice
  - signing preflight
  - package size review
  - smoke-test links
  - rollback instructions
- Update `docs/windows-release.md` after the Windows path is final.
- Add `docs/macos-release.md`.
- Add `docs/linux-release.md`.
- Add `docs/update-channels.md`.
- Add a release issue template:
  - version
  - scope
  - risk level
  - migration impact
  - artifacts expected
  - smoke-test owner
- Keep release notes generated but editable:
  - installation steps
  - what's changed
  - known issues
  - checksums
  - privacy/local-first note

Exit criteria:

- A new maintainer can cut a beta release by following docs.
- Stable release steps are scripted where possible and checklist-driven where human approval is needed.

## Production Release Gate

Do not promote a release to stable unless all of these pass:

- [ ] Versions match the tag across all project files.
- [ ] Frontend typecheck passes.
- [ ] Frontend tests pass.
- [ ] Backend tests pass.
- [ ] Rust check passes.
- [ ] Sidecar builds on every target OS.
- [ ] Installers build on every target OS.
- [ ] Updater artifacts are generated.
- [ ] Updater signatures are present and match `latest.json`.
- [ ] Windows installer is signed for stable.
- [ ] macOS artifact is signed and notarized for stable.
- [ ] Linux checksums are published.
- [ ] Packaged app launches on every target OS.
- [ ] Sidecar health check passes from packaged app.
- [ ] Update from previous stable succeeds.
- [ ] User app data survives update.
- [ ] Installer sizes are within budget or consciously approved.
- [ ] Browser automation remains opt-in and documented as experimental.
- [ ] Release notes include checksums, known issues, and local-first privacy language.
- [ ] Rollback instructions point to the previous known-good stable release.

## Recommended Execution Order

1. Version script and version check.
2. Clean local build scripts to remove redundant work.
3. Move CI sidecar build to `scripts/build-sidecar.mjs`.
4. Add package size reporting.
5. Add stable/beta/nightly manifests.
6. Add packaged app smoke mode.
7. Add installer smoke tests.
8. Add update smoke tests.
9. Add Windows code signing.
10. Add macOS signing and notarization.
11. Split backend dependencies into core and optional feature groups.
12. Add optional component downloads for browser runtime and heavy local intelligence.
13. Promote the first production stable only after update-from-previous succeeds.

## Suggested Milestones

### Milestone A - Reliable Alpha

- One version script.
- Clean release scripts.
- CI uses the canonical sidecar script.
- Windows installer builds from tags.
- Update artifact exists and is signed.
- Manual smoke test passes on a clean Windows machine.

### Milestone B - Cross-OS Beta

- Windows, macOS, and Linux installers build from tags.
- macOS architecture support is explicit.
- Package size report is generated.
- Stable and beta update channels exist.
- Packaged sidecar smoke test runs in CI.

### Milestone C - Production Candidate

- Windows signing is active.
- macOS signing and notarization are active.
- Update from previous version is tested.
- Local data migration tests pass.
- Optional browser runtime download is verified.
- Release notes and checksums are generated automatically.

### Milestone D - Production Stable

- Stable channel is manually promoted.
- Rollback path is documented.
- Diagnostics export is available.
- Release issue template is ready.
- At least one beta cycle has completed without release-blocking bugs.

## Notes For JustHireMe

- The core product should stay useful without Playwright browser binaries. Scraping and automation can be enhanced after install, but the app should open, store settings, manage leads, rank jobs, and generate materials without the optional browser runtime.
- The sidecar should continue listening only on `127.0.0.1` and should require its runtime token for protected HTTP and WebSocket routes.
- Any generated resumes, cover letters, logs, databases, graph stores, vector stores, and provider secrets must remain outside the app install directory and inside user-writable app data locations.
- Release notes should never imply there is a hosted backend unless one is actually introduced later.
