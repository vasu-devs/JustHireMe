# Maintainer Release Checklist

Use this before cutting a public release or sharing a build link.

For the full production release plan, see [Production Release Roadmap](PRODUCTION_RELEASE_ROADMAP.md).

## Required Local Checks

- [ ] `npm ci`
- [ ] `npm run check:all`
- [ ] `npm run lint`
- [ ] `npm run test:coverage`
- [ ] `cd backend && .\.venv\Scripts\python.exe -m ruff check .`
- [ ] `cd backend && .\.venv\Scripts\python.exe -m mypy . --ignore-missing-imports`
- [ ] `cd backend && .\.venv\Scripts\python.exe -m pytest tests -q --cov=. --cov-report=term-missing --cov-fail-under=60`
- [ ] `npm run release:smoke`
- [ ] `npm run smoke:windows-update`

`npm run release:smoke` is the normal local release validation path. Do not require local signed installer builds for RC validation.

## CI Release Checks

- [ ] Tagged release verifies `TAURI_SIGNING_PRIVATE_KEY` and, when used, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.
- [ ] Windows NSIS installer is produced by the Tauri build in GitHub Actions.
- [ ] `npm run release:verify-updater -- release-assets vX.Y.Z` passes for generated release assets.
- [ ] GitHub Actions installs the newly built Windows installer into a temp directory and smokes the installed sidecar.
- [ ] Update-over-existing smoke passes when a previous stable Windows installer is available.

## Privacy And Safety

- [ ] No `.env`, API keys, cookies, bearer tokens, private resumes, generated PDFs, local databases, graph stores, vector stores, private app data, or packaged sidecar binaries are committed.
- [ ] Live-fire and test fixtures use fake `.test` identity data, not personal emails, phone numbers, or LinkedIn profiles.
- [ ] Browser automation and auto-apply are documented as candidate-authorized, default-deny, and manually reviewable when blocked.
- [ ] Release notes describe JustHireMe as local-first and do not imply a hosted backend.
- [ ] Release notes include SHA256 checksums for uploaded installer assets.
- [ ] Tauri updater signing secrets live in the GitHub Actions release environment, not in local docs or committed files.
- [ ] Tauri capabilities remain narrow; frontend code should not receive broad shell execution permissions.
- [ ] The bundled sidecar listens on `127.0.0.1` and requires the runtime token for HTTP and WebSocket access.

## Release Flow

1. Update versions with `npm run version:bump -- X.Y.Z`.
2. Run the required local checks above.
3. Create a tag like `vX.Y.Z`.
4. Push the tag and let the release workflow build, sign, verify updater artifacts, smoke the Windows installer, and publish the GitHub Release from CI.
5. Download and smoke-test the GitHub-built Windows installer before sharing the release link widely.
6. If a previous stable installer exists, confirm the in-app update installs the new version and preserves local app data.
