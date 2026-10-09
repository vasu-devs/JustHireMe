# Consumer frontend handoff — September 2026

Historical design, superseded on 22 September by the [pastel notebook product](IOS_NOTEBOOK_HANDOFF.md). The current app has five sections and application-based allowances; the credit/draft journey below is retained as implementation history.

The iOS app now presents a focused customer workspace with four tabs: Home, Roles, Applications, and You. It retains the desktop brand fonts and warm palette. Home offers a single next role; credit plans are accessible through the balance and account screen.

## Working preview journey

Explore preview → inspect a role and its skill mentions → prepare a sample application → review/edit/share → mark it applied → see the updated tracker. Users can also add roles, search/filter statuses, edit their preview profile, and simulate selecting weekly/monthly/one-time credits.

The persistent preview banner identifies sample data and no charges. The preview starts with 30 **demo** credits and uses 5 per application. Reopening an existing application does not debit again. Selecting a preview plan adds demo credits only after an explicit confirmation. No real subscription, payment, AI request, account, or employer submission is created. Preview changes reset on exit/relaunch.

## Backend integration boundary

No backend implementation changed in this frontend pass. Existing email OTP, authenticated `/v1/*` calls, StoreKit product loading and verified transaction delivery remain separate from preview actions.

| Frontend feature | Existing contract |
| --- | --- |
| Account, credit balance, capabilities | `GET /v1/me` |
| Profile and AI consent | `PUT /v1/profile` |
| Role creation and status | `GET/POST /v1/jobs`, `PATCH /v1/jobs/{id}` |
| Application generation | `POST /v1/jobs/{id}/tailor`, idempotency key |
| Draft history | `GET /v1/drafts` |
| Plans, verified purchases, ledger | `/v1/products`, `/v1/billing/transactions`, `/v1/ledger` |
| Account export/deletion | `/v1/export`, `DELETE /v1/account` |

Live balances remain server-authoritative. StoreKit shows localized prices; the preview deliberately invents no live price. Weekly and monthly plans are auto-renewing subscription concepts, with a separate one-time credit pack.

Draft edits for authenticated users are **device-local**, stored in Application Support with complete file protection, excluded from backup, and scoped by a SHA-256 account identifier. Preview edits stay in memory. Account deletion removes that account's local edits. Sign-out clears loaded content; returning to the same account restores local edits. Sharing/export produces a user-controlled copy. Cross-device edit synchronization is a future backend endpoint; the UI does not claim it is available.

Jobs are saved from user-provided descriptions. There is no live discovery feed, automatic application submission, or invented hiring probability. Matching displays exact mentions of profile skills.

## Verification and capture

`ios/scripts/run-simulator.sh` builds the native app, runs model/UI tests, records a separate deliberate XCTest walkthrough using `simctl recordVideo`, captures iPhone/iPad screens, and exports evidence. Video recording is stopped by its exact PID even on failure. The simulator app archive is not a signed iPhone IPA.

See `IOS_VALIDATION.md` for verified results. Real authentication, AI, Apple sandbox billing, device signing, and TestFlight still need configured services and separate integration checks. Repository visibility remains private; existing licensing documents were preserved.
