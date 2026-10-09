# Mobile validation — 7 September 2026

The mobile source was pushed to [JustHireMe-iOS-private](https://github.com/vasu-devs/JustHireMe-iOS-private) after verifying private visibility. No mobile changes were pushed to the public repository.

## Verified hosted run

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

Native UI tests exercised the explicitly labelled demo. Real Supabase authentication, Apple sandbox purchases and lifecycle events, AI generation, production deployment, operational reconciliation, and backup/restore drills still require staging credentials and testing. Physical devices, iPad/small-screen layouts, dark mode, accessibility, signing, TestFlight, and App Store submission remain. See the [launch guide](IOS_LAUNCH.md).

The simulator ZIP contains a Mac simulator app, not a signed iPhone IPA. The hosted simulator ends when CI completes; the captured run is not a currently interactive simulator stream.
