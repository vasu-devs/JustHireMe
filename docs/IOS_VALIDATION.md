# Mobile implementation validation — 7 September 2026

Implemented in a Windows workspace. No native iOS build, simulator run, screenshot, device test, signing, TestFlight upload, paid AI call, or real Apple purchase was performed.

## Executed checks

- 29 Python tests passed against SQLite in isolated temporary databases.
- The same 29 tests passed against a temporary PostgreSQL 17 container, including real row-lock/concurrency paths. The container used synthetic users/jobs and was stopped after validation.
- Ruff passed for the new cloud modules, tests, and portable validation script.
- Portable validation passed for plist parsing, privacy manifest structure, asset catalog JSON, and selected configuration invariants. This does not typecheck Swift.
- Python modules compiled successfully; git whitespace validation passed.

The test suite covers authentication rejection, account isolation, zero initial balance, duplicate receipt delivery, concurrent purchase delivery, subscription renewal credits, non-expiry, refunds/debt, refund-before-purchase ordering, refund reversal, sandbox account restrictions, consent/credit prerequisites, idempotent generation, provider failure refunds, stale-job recovery, late results, concurrent spending, unsafe input, oversized request rejection, disabled provider behavior, deletion during generation, deletion retries, configured retention purge, and history/notification reconciliation.

Apple's actual server library was exercised to reject a forged JWS. Auth, successful Apple purchases/history responses, and AI output were mocked. Real Supabase email/refresh/delete flows, Apple signing chains and sandbox lifecycle events, and Anthropic output quality/cost still require staging validation. Tests emitted two upstream TestClient/AnyIO deprecation warnings but no failures.

## Unexecuted checks

The new macOS CI job and Swift unit tests are provided but have not run. Before launch, complete a successful Xcode build, simulator/device UI checks, accessibility checks, real auth, Apple sandbox purchases and notifications, operational reconciliation, retention and restore drills, and production configuration. See [launch guide](IOS_LAUNCH.md).

## Follow-up: native simulator preparation

The 29 backend tests were rerun successfully. Added three XCTest UI scenarios (onboarding/tab navigation, job creation and interview tracking, disabled demo drafting) and expanded the Swift unit suite to five cases. The simulator script builds and tests the app, installs and launches its demo, captures a screenshot, and packages the simulator app. Xcode screenshot attachments and the `.xcresult` bundle are retained by the macOS workflow. Bash syntax, YAML target/workflow parsing, plist checks, and whitespace checks passed locally.

No Xcode installation or connected Mac simulator is available on this Windows host. GitHub access was verified, and an isolated local `codex/ios-simulator-tests` branch was prepared from `origin/main`. Publishing that branch and executing the hosted macOS workflow await the user's approval. Native build success and simulator screenshots must not be claimed until that run actually completes.
