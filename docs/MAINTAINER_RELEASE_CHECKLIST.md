# Maintainer Release Checklist

Use this before cutting a public release or sharing a build link.

For the full production release plan, see [Production Release Roadmap](PRODUCTION_RELEASE_ROADMAP.md).

## Required Checks

- [ ] `npm ci`
- [ ] `npm run release:preflight`
- [ ] `npm run version:check`
- [ ] `npm run typecheck`
- [ ] `npm test`
- [ ] `npm run build`
- [ ] `cd backend && uv sync --dev`
- [ ] `cd backend && uv run python -m pytest tests/test_regressions.py tests/test_api.py::TestAuthGate`
- [ ] `cd src-tauri && cargo test --lib`
- [ ] `cd src-tauri && cargo check`
- [ ] For generated release assets, `npm run release:verify-updater -- release-assets vX.Y.Z`

## Privacy And Safety

- [ ] No `.env`, API keys, cookies, bearer tokens, private resumes, generated PDFs, local databases, graph stores, vector stores, or packaged sidecar binaries are committed.
- [ ] Browser automation and auto-apply behavior is documented as experimental and opt-in.
- [ ] Release notes describe JustHireMe as local-first and do not imply a hosted backend.
- [ ] Release notes include SHA256 checksums for uploaded installer assets.
- [ ] Tauri updater signing secrets are available in the release environment: `TAURI_SIGNING_PRIVATE_KEY` and, when used, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.
- [ ] Tauri capabilities remain narrow; frontend code should not receive broad shell execution permissions.
- [ ] The bundled sidecar listens on `127.0.0.1` and requires the runtime token for HTTP and WebSocket access.
- [ ] macOS release notes tell users to drag `JustHireMe.app` from the DMG into `/Applications` or `~/Applications` before opening it. In-app updates cannot replace an app running from a mounted DMG or Gatekeeper App Translocation.

## Release Flow

1. Update versions with `npm run version:bump -- X.Y.Z`.
2. Run the required checks above.
3. Create a tag like `v1.0.0`.
4. For a quick local smoke test, run `npm run release:smoke` and launch `src-tauri/target/release/justhireme.exe`.
5. For the standard Windows installer, run `npm run release:windows`.
6. Push the tag and let the release workflow build, verify updater artifacts, and publish the GitHub Release from CI.
7. Download and smoke-test the GitHub-built installer before sharing the release link widely.
8. On macOS, first confirm a DMG-launched copy blocks in-app update with a clear "move app first" message instead of `Read-only file system (os error 30)`.
9. On a machine with the previous release installed in a writable Applications folder, open the app, wait for the update prompt, install the update, restart, and confirm the app reports the new version while local app data remains intact.
