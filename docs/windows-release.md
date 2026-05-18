# Windows Release Checklist

The stable 1.0.0 public release target is a Windows desktop installer.

## Build

```powershell
npm install
cd backend
uv sync --dev
cd ..
npm run release:windows
```

The standard Windows release build verifies project versions, builds the frontend and Python sidecar, then produces the NSIS installer through Tauri. Use `npm run release:smoke` when you want the fastest parallel local smoke build without installer generation.

Because the app has a Tauri updater public key configured, a full local `npm run release:windows` also needs `TAURI_SIGNING_PRIVATE_KEY` and, when applicable, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Public installers should normally be produced by the tagged GitHub release workflow where those secrets are available.

| Artifact | Use |
| --- | --- |
| `src-tauri/target/release/bundle/nsis/JustHireMe_<version>_x64-setup.exe` | Recommended public download for testers |
| `src-tauri/target/release/justhireme.exe` | Unbundled release executable for local smoke tests |

For the fastest release smoke test, skip installer generation:

```powershell
npm run release:smoke
.\src-tauri\target\release\justhireme.exe
```

Build MSI only when you specifically need managed Windows deployment:

```powershell
npm run package:windows:msi
```

Build both NSIS and MSI only for a full compatibility release:

```powershell
npm run package:windows:all
```

For the stable core installer, the bundled Python sidecar intentionally excludes the experimental browser automation stack and heavyweight local embedding model packages. The supported release smoke path is app launch, settings, profile/lead workflows, deterministic ranking, and document/outreach generation. Semantic matching should fail soft when local embedding packages are unavailable.

## Updater Verification

Tagged GitHub releases generate `latest.json` from the signed Tauri updater artifacts. The release workflow runs:

```powershell
npm run release:verify-updater -- release-assets vX.Y.Z
```

That check fails the release if `latest.json` points at a missing installer, has a mismatched version, omits a signature, or contains a signature that does not match the uploaded `.sig` file.

## Smoke Test

- Install on a clean Windows machine or VM.
- Open the app without developer tools.
- Enter a local/Ollama or API provider setting.
- Import a profile or resume.
- Run a scan.
- Verify leads show signal, fit, and quality explanations.
- Generate resume PDF, cover letter PDF, and outreach drafts.
- Confirm experimental browser automation is not presented as the primary workflow.
- If a previous release is installed, confirm the in-app update prompt downloads the new release, installs it, restarts, and preserves local app data.

## Release Notes

Mention that browser automation is experimental. The supported workflow is scraper, ranker, vector matching, and customization.
Mention whether the build is the stable core installer or a future full-ML installer.
Include SHA256 checksums for every uploaded installer asset.
Public installers should be built by GitHub Actions from the release tag, not uploaded from a local workstation.
