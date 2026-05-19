# Windows Release Checklist

The stable public target for this RC is the Windows desktop installer. macOS and Linux artifacts may still be built by CI where supported, but Windows is the promoted stable path for this pass.

## Local Validation

Local machines should validate behavior, not produce public signed installers:

```powershell
npm install
cd backend
uv sync --dev
cd ..
npm run release:smoke
npm run smoke:windows-update
```

`npm run release:smoke` is the supported fast local release check. It builds the frontend/backend release path and smokes the sidecar without requiring Tauri updater signing secrets.

`npm run smoke:windows-update` runs static Windows updater checks locally. To smoke a real installer, set:

```powershell
$env:JHM_WINDOWS_INSTALLER_SMOKE = "1"
$env:JHM_NEW_INSTALLER = "path\to\JustHireMe_<version>_x64-setup.exe"
npm run smoke:windows-update
```

To test update-over-existing locally with two already-built installers:

```powershell
$env:JHM_WINDOWS_UPDATE_SMOKE = "1"
$env:JHM_OLD_INSTALLER = "path\to\previous\JustHireMe_<old>_x64-setup.exe"
$env:JHM_NEW_INSTALLER = "path\to\new\JustHireMe_<new>_x64-setup.exe"
npm run smoke:windows-update
```

## Packaging And Signing

Public Windows packaging and updater signing happen in GitHub Actions from a release tag. The release workflow owns these secrets:

- `TAURI_SIGNING_PRIVATE_KEY`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, when the key is encrypted

Do not spend local RC time trying to produce signed public installers. `npm run release:windows` and `npm run package:windows` are only useful locally when those signing variables are intentionally available for a packaging rehearsal. Otherwise, use `npm run release:smoke` locally and let tagged CI build the installer.

| Artifact | Use |
| --- | --- |
| `src-tauri/target/release/bundle/nsis/JustHireMe_<version>_x64-setup.exe` | GitHub Actions-built public Windows installer |
| `src-tauri/target/release/justhireme.exe` | Unbundled release executable for local smoke tests |
| `release-assets/JustHireMe-vector-runtime-windows.zip` | Mandatory first-run semantic matching runtime OTA asset |
| `release-assets/JustHireMe-browser-runtime-windows.zip` | Optional browser automation runtime OTA asset |

Build MSI only when managed Windows deployment is explicitly needed:

```powershell
npm run package:windows:msi
```

## CI Release Checks

Tagged releases must verify:

- updater signing secrets are present before packaging
- the Windows NSIS installer is produced by Tauri
- `latest.json` matches the tag, uploaded artifacts, and `.sig` files
- the newly built Windows installer installs into a temp directory
- the slim installed sidecar reports `/health` with app, sqlite, and graph OK
- the mandatory vector runtime OTA installs and then reports vector OK
- update-over-existing smoke passes when a previous stable Windows installer is available

## Stable Core Scope

The stable core installer supports app launch, settings, profile/lead workflows, deterministic ranking, local CRM, and document/outreach generation. Semantic matching is mandatory but delivered as a first-run OTA runtime so the installer stays small while LanceDB, PyArrow, and native vector search are installed only once per machine.

Browser automation and auto-apply are experimental, opt-in lab features. They are not part of the stable core promise and should not be described as the primary workflow in release notes.

## Manual Smoke Test

- Install on a clean Windows machine or VM.
- Open the app without developer tools.
- Accept the required semantic engine install prompt and wait for it to finish.
- Enter a local/Ollama or API provider setting.
- Import a profile or resume.
- Run a scan.
- Verify leads show signal, fit, and quality explanations.
- Generate resume PDF, cover letter PDF, and outreach drafts.
- Confirm browser automation and auto-apply remain clearly experimental and opt-in.
- If a previous release is installed, confirm the update installs over it and preserves local app data.

## Release Notes

Mention whether the build is the Windows stable-core installer. Include SHA256 checksums for every uploaded installer asset. Public installers should be built by GitHub Actions from the release tag, not uploaded from a local workstation.
