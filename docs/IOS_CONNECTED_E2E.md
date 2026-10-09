# Connected iPhone walkthrough

The five-tab native notebook now calls the premium backend created in the separate backend task. The source and cloud dependencies are backed up together in the **private** `vasu-devs/JustHireMe-iOS-private` repository. The public desktop repository was not pushed.

## Verified result — 22 September 2026

[Private CI run 35723632669](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/35723632669) passed on code revision `fb2f1ebf47c15a7873f2ce97fd6ad6731163107a`.

| Check | Result |
|---|---|
| Native model tests | 15 passed |
| Native UI scenarios | 5 passed |
| Preview walkthrough | 1 passed |
| Connected walkthrough using Vasudev's profile | 1 passed; 139 seconds |
| Cloud API tests | 29 passed on SQLite; 29 on PostgreSQL |
| Premium backend tests, including Chromium flow | 89 passed on SQLite; 89 on PostgreSQL |
| iPad adaptive layout | Simulator screenshot captured |

The [recorded walkthrough](mobile-ui/connected/walkthrough.mp4), sixteen named screenshots and [server evidence](mobile-ui/connected/server-evidence.json) are retained with this handoff. The video is actual simulator output, not an animated mockup.

## What is connected

- Profile: editable notebook sections, application contact details, separate provider consents, atomic save with revision conflict protection, and restoration after relaunch.
- For You: paginated server recommendations, relevance scores, per-employer capabilities, last-checked timestamps, and idempotent application requests.
- Applications: real queue states, timelines, generated PDF, missing-answer retries, cancellation, user-reported outcomes, confirmation-email status and server summary counts.
- Auto-apply: explicit authorization, attempt and daily limits, relevance threshold, progress and pause through the campaign API.
- Grow: study suggestions from job/profile skill gaps and account-owned completion persistence. These are not predictions of hiring outcomes.
- Plan: backend catalog and allowance, StoreKit pricing/purchase/restore hooks, and a Debug-only receipt fixture for the recorded test.
- Account settings: data export, sign-out and confirmed deletion through the existing account API.

Notebook metadata and learning progress are stored in the existing account profile JSON. Saving learning progress does not invalidate professional matching evidence. No new database tables were needed for these additions. Source attachments are session-local; saving a profile persists its extracted sections, not the original files. Arbitrary file interpretation and OCR are not connected services.

## Test boundary

The connected XCTest launches the actual SwiftUI app in the iPhone simulator and makes HTTP requests to the actual FastAPI application on the macOS runner. It uses SQL persistence, the discovery parser, match worker, application queue, résumé builder, campaign worker, notification outbox and credit ledger.

External discovery responses, TypeSafe matching decisions, employer acceptance, email delivery, authentication and Apple receipt verification use controlled fixtures. No employer was contacted, no email was sent and no payment was made. This is integration evidence, not proof of production deployment or live provider credentials.

The test profile contains selected career facts from the owner's `E:/content.md`: work, education, projects, skills and achievements. Embedded agent instructions and confidential employer metrics were excluded. The selected fixture and recordings contain personal career information and belong only in this private workspace/repository.

The test imports the six sections, saves and relaunches, submits a role, opens its PDF, records an interview outcome, resolves a missing-answer refund/retry, runs and pauses auto-apply, completes a learning step, buys a test monthly allowance, and relaunches again to verify persistence. Final server assertions require three unique accepted fixture submissions, three résumés, three notification deliveries, no worker errors and **185 credits**: 50 initial − 15 consumed + 150 test purchase.

## Reproduce on a Mac

From the private repository root, install Python 3.13 requirements from `cloud/requirements.lock.txt` and `premium/requirements.txt`, plus XcodeGen and ffmpeg. Run `RUN_CONNECTED_E2E=1 bash ios/scripts/run-simulator.sh`. The script owns and shuts down its loopback backend process and recording process. It refuses to reuse port 8769. Test databases remain in ignored `ios/TestArtifacts`, outside uploaded artifacts.

The release app ignores the test launch flag. Its API URL must be HTTPS in ignored `ios/JustHireMe/Configuration.plist`; the loopback address exists only in Debug. Production requires a deployed premium API, PostgreSQL, Supabase configuration, server provider credentials and App Store Connect products/signing. None were provisioned by this integration task.
