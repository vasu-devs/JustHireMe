# Mobile validation — 29 September 2026

## App Store readiness, jevbrowse auto-apply engine and résumé downloads

[Private run 36483391800](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/36483391800) passed on commit `532d3b9` (branch `codex/ios-appstore-readiness`) with Xcode 26 on macos-15. The Linux job passed the cloud suite (29 tests) and the premium suite (94 tests) on SQLite and again on PostgreSQL 17, including the new real-Chromium jevbrowse flow, then the extended `scripts/validate-mobile.py`. The macOS job compiled the app, ran **17 model tests** (two new: field-naming validation messages and session-expiry errors; radio, checkbox and Greenhouse select questions), **5 UI scenarios**, the recorded preview walkthrough, and the **connected walkthrough** against the loopback premium backend. Its server evidence matched exactly: 3 unique accepted submissions, 3 generated résumés, 3 confirmation emails, no worker errors, balance 185 credits. The iPad capture completed. Total runner time was eight minutes. Retained screenshots: [résumé sheet with Share and Save to Files](mobile-ui/appstore-readiness/08-generated-resume.png), [needs-attention question](mobile-ui/appstore-readiness/10-missing-answer.png), [plan screen](mobile-ui/appstore-readiness/14-server-plans.png).

What this run newly covers: the Info.plist compliance keys (export compliance, all four iPad orientations, launch colour) and privacy-manifest reasons build and validate; the résumé sheet's Share and Save to Files actions; optional questions no longer blocking a retry; the plan screen's product/price/renewal disclosure. What it does not cover: a signed device build, TestFlight, real StoreKit purchases, a live TypeSafe-backed jevbrowse submission, and physical-device performance. Those need the owner steps in [APP_STORE_SUBMISSION.md](APP_STORE_SUBMISSION.md).

---

# Mobile validation — 22 September 2026

## Connected premium backend

[Run 35723632669](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/35723632669) passed at code revision `fb2f1eb`: **22 native tests**, including the full connected walkthrough using the owner's profile, and **118 backend tests on each of SQLite and PostgreSQL**. The native journey verifies durable profile/learning state, queue submission, generated résumé, refund/retry, manual outcome, auto-apply pause and test receipt accounting. iPad capture also completed. See the [recording and exact test boundary](IOS_CONNECTED_E2E.md); external providers use controlled fixtures, and production is not deployed.

## Typography and copy refinement

[Run 35718554854](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/35718554854) passed on revision `2143539`: 15 model tests, five UI scenarios and one recorded walkthrough, plus the iPad layout capture. Backend regression tests passed on both databases. The change reduces headline size, simplifies the font hierarchy and replaces slogans with direct labels; application behavior is unchanged. See the [current visual review](IOS_NOTEBOOK_TYPOGRAPHY.md).

## Current pastel notebook frontend

[Private run 35715587730](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/35715587730) passed on app revision `da091d3d9c74d4d3be83e1dc98190f88592fa140`, with Xcode 26.3 and an iPhone 16 Pro simulator on iOS 18.5. This replaces the consumer workspace described below.

All **21 native checks passed**: 15 model tests (nine existing and six notebook tests), five interactive UI scenarios, and one separately recorded walkthrough. Coverage includes content section parsing and reviewed merging without overwriting edits, inline profile editing, duplicate submission/debit prevention, exhausted allowances, auto-apply opt-in/title/location/daily limits, plan quantities, outcome chart changes, learning completion, preview isolation, dark mode, and accessibility text size. The walkthrough test took 44.529 seconds; its recording follows profile import, recommendations, applying, tracking, growth and plans.

The same build was launched and captured on an iPad. This is a tablet layout check, not a full tablet interaction suite. Profile, organized import, recommendations, application chart, plan selection, growth, large text and iPad screenshots were visually inspected. Preserved media and the 40-second simulator recording are in [the notebook review](IOS_NOTEBOOK_REVIEW.md). The video was losslessly trimmed at a keyframe and retains its original resolution; it does not simulate a functioning backend.

New notebook data and imported files are session-only. Markdown/text and readable PDF extraction are local conveniences, not agentic ingestion. The sample jobs, submissions, outcomes, auto-apply and allowances are explicitly previews. Live AI ingestion, shared scraping/recommendations, durable user storage, employer submission/outcome syncing, and the new Apple billing catalog remain backend/release work. This run does not establish production readiness or physical-device performance. See the [current backend handoff](IOS_NOTEBOOK_HANDOFF.md).

## Consumer frontend and recorded walkthrough

[Private run 35712323818](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/35712323818) passed on app revision `3568650` using Xcode 26.3. Nine model tests and five native UI scenarios passed, followed by a separate 57-second walkthrough test recorded directly from the iPhone simulator. The script also installed the same app on an iPad and captured its layout. Backend code was unchanged; all 29 regression tests passed on SQLite and again on PostgreSQL.

The new checks exercise profile preview saving, role creation and interview tracking, application creation/editing/applied status, returning through the navigation stack, simulated monthly credits, search empty states, dark mode, and accessibility text size. Model checks cover duplicate debit prevention, insufficient balance, missing profile information, account-scoped device edits, and resetting preview state.

Two earlier runs compiled and passed all nine model checks but caught a back-navigation failure. The fixes stabilize Home's role destination when its recommendation changes and move the preview banner out of the native navigation bar's touch area. The complete corrected scenario passed in the linked final run.

The recording uses fictional preview data, sample drafts, and demo credits. It does not prove real email authentication, AI output, Apple purchases, physical-device behavior, or App Store readiness. Those integrations remain a separate backend/release step. See [frontend handoff](IOS_FRONTEND_HANDOFF.md) and [launch guide](IOS_LAUNCH.md).

CI uploads screenshots, manifests, logs, a simulator app archive, and the walkthrough for seven days. Full `.xcresult` bundles remain available when running the script locally on a Mac; they are omitted from CI uploads to avoid unnecessarily large transfers. The reviewed media are preserved in the repository's `docs/mobile-ui/consumer/` directory.

---

# Earlier validation — 7 September 2026

The mobile source was pushed to [JustHireMe-iOS-private](https://github.com/vasu-devs/JustHireMe-iOS-private) after verifying private visibility. No mobile changes were pushed to the public repository.

## Desktop journal UI validation

The final UI refinement run [34138397456](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/34138397456) passed six native unit tests, five UI tests, and all 29 backend tests on both databases, on source revision `04b2c9af2c1344bcb4488d2971b76b244ed77a61`. It includes the desktop brand header and Profile dossier identity card. The iPhone screenshots and simulator ZIP were downloaded and inspected. A subsequent shell quoting error prevented tablet capture even though CI reported success; this did not invalidate the completed native tests. The capture script was corrected, exit status preservation added, and both Bash scripts passed local syntax checks. CI now checks Bash syntax before starting a native build.

The dedicated [iPad run 34139482938](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/34139482938) then passed on workflow revision `bd481ca`. It checked both Bash scripts, downloaded the tested app, created an iPad (10th generation) on iOS 26.2, installed and launched the demo, and captured the two-column journal. The downloaded app archive SHA-256 matched the iPhone run exactly: `d392d1d4edea86affd8fda3fbc85e19d23d2e455b6a87c7377b8b24df7f5fed5`. This is a tablet launch/layout check, not a complete tablet interaction suite. The screenshot was visually inspected and saved in the comparison document. GitHub warned that artifact actions v4 are being run with Node 24 instead of their deprecated Node 20 runtime; the download and upload succeeded.

[Run 34137328273](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/34137328273) passed on revision `9782b61abbe1797ef38f7ff45fcf8d490ffa5b32`: six native unit tests, five UI tests, and all 29 backend tests against both databases. The new font test verified all six desktop fonts register in the app. UI scenarios covered light/dark navigation, accessibility text sizing, demo onboarding, job creation/status updates, and disabled demo drafting.

The app ran on iPhone 16 Pro with iOS 18.5, built using Xcode 26.3. Thirteen UI screenshot attachments plus the post-test launch screenshot were downloaded. The overview in light/dark mode, large-text overview, and dark profile were visually inspected against the desktop reference. The first visual pass did not produce an iPad capture because of the capture-script quoting error described above.

See [desktop design comparison](IOS_DESKTOP_PARITY.md) for design sources and deliberate platform adaptations.

## Initial verified hosted run

[GitHub Actions run 34131799854](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/34131799854) passed on source revision `40fa0cfe7b955c29a5528d27af48e524f82db771`.

- The native app compiled with Xcode 26.3 (17C529) on a hosted Mac and ran on an iPhone 16 Pro simulator.
- Five Swift unit tests passed: server account decoding, session-expiry decoding, demo isolation, profile encoding, and whole-word skill matching.
- Three UI tests passed: onboarding/tab navigation, job creation and interview tracking, and disabled demo drafting.
- The script installed and launched the demo app after testing, captured `Workspace.png`, exported eight UI screenshot attachments, and packaged `JustHireMe-simulator.zip`.
- The workspace, credit plans, and profile screenshots were visually inspected.
- All 29 backend tests passed against SQLite and again against PostgreSQL in Linux CI.

The workflow retains the simulator app, screenshots, build log, and `Tests.xcresult` for seven days. A local copy is saved under `ios/TestArtifacts/verified-34131799854/` (ignored by Git).

The first hosted attempt failed in icon preparation because a headless AppKit graphics context could not use the RGB bitmap. Replacing that context with an opaque CoreGraphics/ImageIO render fixed the build. The successful run had no Swift build errors or test failures. App Intents metadata extraction emitted an informational warning because the app has no App Intents dependency.

## Local checks

The same 29 backend tests also passed locally against SQLite and a temporary PostgreSQL 17 container, including row-lock/concurrency paths. The container used synthetic data and was stopped after validation. Ruff, Python compilation, portable plist/privacy manifest/asset checks, Bash syntax, YAML parsing, and Git whitespace checks passed.

The backend suite covers authentication rejection, account isolation, duplicate and concurrent receipt delivery, subscription renewal credits, non-expiry, refunds/debt and reversal, sandbox restrictions, consent, idempotent generation, provider failure refunds, stale-job recovery, concurrent spending, unsafe input, deletion retries, retention purge, and history/notification reconciliation. Apple's actual server library rejected a forged JWS. Successful authentication, Apple purchases/history responses, and AI output were mocked. Two upstream TestClient/AnyIO deprecation warnings remain.

## Remaining validation

Native UI tests exercised the explicitly labelled demo. Real Supabase authentication, Apple sandbox purchases and lifecycle events, AI generation, production deployment, operational reconciliation, and backup/restore drills still require staging credentials and testing. Physical devices, additional screen sizes/orientations, a complete VoiceOver/accessibility audit, signing, TestFlight, and App Store submission remain. Light/dark and one accessibility text-size scenario have been tested; they do not cover every accessibility setting. See the [launch guide](IOS_LAUNCH.md).

The simulator ZIP contains a Mac simulator app, not a signed iPhone IPA. The hosted simulator ends when CI completes; the captured run is not a currently interactive simulator stream.
