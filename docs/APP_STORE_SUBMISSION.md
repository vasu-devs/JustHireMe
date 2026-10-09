# App Store submission runbook

Written 29 September 2026 for the five-tab notebook app (`ios/`) and the premium backend (`premium/` in the private repository). It lists what the code now guarantees, what the hosted CI proves, and the exact steps that still need the owner's Apple, Supabase and hosting accounts. Nothing here claims the app is approved or deployed.

## What the repository now provides

| Area | State |
| --- | --- |
| Bundle | `com.justhireme.mobile`, version `1.0.0`, build number set per archive, iOS 17 minimum, iPhone and iPad |
| Compliance keys | `ITSAppUsesNonExemptEncryption=false` (HTTPS only), iPad supports all four orientations (multitasking), branded launch colour, `LSRequiresIPhoneOS` |
| Privacy manifest | No tracking; `UserDefaults` declared with reason `CA92.1`; collected data: name, email, phone, user ID, purchase history, other user content |
| Account | Email code sign-in, in-app account deletion, data export, privacy/terms/support links from `Configuration.plist`, expired sessions sign the user out with a clear message |
| Purchases | StoreKit 2 with server-side signed-transaction delivery, restore, manage-subscription sheet, localized name/price/period and the auto-renewal disclosure on the plan screen |
| Applications | One-tap apply, campaigns (auto-apply) with daily limits and pause, missing-answer retry that now supports choice and consent questions, résumé preview with **Share** and **Save to Files** |
| Release tooling | `ios/scripts/archive-release.sh` + `ios/ExportOptions.plist` (archive, sign with an App Store Connect API key, upload to TestFlight); `.github/workflows/ios-release.yml` runs the same on a hosted Mac |
| Structural checks | `scripts/validate-mobile.py` (portable) and `--release` (requires the production `Configuration.plist`); runs in CI and before every archive |

Backend: the premium API `0.4.0` adds the jevbrowse submission engine (`BROWSER_SUBMISSION_ENGINE=jevbrowse`), which reads any supported Greenhouse, Lever or Ashby hosted form, fills only supplied facts, and returns every unanswered consent, authorization or required question to the app instead of guessing. See `premium/docs/DEPLOYMENT.md`.

## Owner steps, in order

1. **Apple Developer Program.** Enroll the seller identity that will appear on the store. Record the 10-character Team ID.
2. **App record.** In App Store Connect create the app with bundle ID `com.justhireme.mobile`, name *JustHireMe*, primary language English. Note the numeric Apple ID for the backend (`APPLE_APP_ID`).
3. **In-app purchases.** Create exactly these products, in one subscription group at the same service level, Family Sharing off, no offers:
   - `justhireme.focus.weekly` (auto-renewable, 1 week, grants 30 credits = 6 applications)
   - `justhireme.pro.monthly` (auto-renewable, 1 month, grants 150 credits = 30 applications)
   - `justhireme.credits.50` (consumable, grants 50 credits = 10 applications)
   Set prices in App Store Connect; the app never hardcodes a price. Any extra bulk SKU must also be added to `PREMIUM_APPLE_PRODUCTS` on the server before it is sold.
4. **Agreements, tax, banking.** Complete the Paid Apps agreement. Purchases stay unavailable (`billing_available=false`) until the backend has Apple root certificates and the App Store Server API key.
5. **App Store Connect API key.** Users and Access → Integrations → App Store Connect API → generate a key with the *App Manager* role (cloud signing needs it). Download the `.p8` once. Keep the Key ID and Issuer ID.
6. **Production backend.** Deploy `premium` with PostgreSQL, a production Supabase project (email OTP with `{{ .Token }}`, custom SMTP, short code lifetime), `SUBMISSIONS_ENABLED=true`, `BROWSER_SUBMISSIONS_ENABLED=true`, `BROWSER_SUBMISSION_ENGINE=jevbrowse`, a TypeSafe key, Apple verification settings, and HTTPS ingress with rate limits. Run `python -m jhm_premium.manage init-db` once. Start `discover`, `match`, `campaign`, `apply`, `notify`, `recover` workers. Configure App Store Server Notifications V2 to `/v1/billing/apple-notifications`.
7. **Public pages.** Publish real privacy policy, support and terms pages (or use Apple's standard EULA for terms). They must be reachable during review.
8. **`ios/JustHireMe/Configuration.plist`.** Copy `ios/Configuration.example.plist`, fill `APIBaseURL` (HTTPS API), `SupabaseURL`, `SupabasePublicKey` (the *public* key only), `PrivacyURL`, `SupportURL`, `TermsURL`. `python3 scripts/validate-mobile.py --release` must pass.
9. **Archive and upload.** Either locally on a Mac:
   ```sh
   brew install xcodegen
   export APPLE_TEAM_ID=XXXXXXXXXX ASC_KEY_ID=ABC123DEFG ASC_ISSUER_ID=<uuid> ASC_KEY_PATH=~/AuthKey_ABC123DEFG.p8
   bash ios/scripts/archive-release.sh
   ```
   or from GitHub: add the secrets `APPLE_TEAM_ID`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_API_KEY_P8` (base64 of the `.p8`), `IOS_CONFIGURATION_PLIST` (base64 of the plist) to the private repository and run **iOS release to TestFlight**. With automatic signing and the API key, Xcode registers the App ID, creates the distribution certificate and profile, and uploads the build.
10. **TestFlight.** Install the processed build on a real iPhone and iPad. Walk through: sign up with a fresh email, code resend, profile import and save, feed, apply, needs-attention retry, auto-apply start and pause, résumé share/save, plan purchase in the sandbox (weekly, monthly, top-up, restore, cancel), sign out, delete account. Test airplane mode, an expired session (revoke the refresh token in Supabase), VoiceOver and the largest text size.
11. **Store listing.** Screenshots on the required sizes from the TestFlight build (empty state, profile, matches, application detail, auto-apply, plan with live prices). App Privacy answers must match the privacy manifest: name, email, phone, user ID, purchase history, user content; all linked to identity, none used for tracking. Age rating questionnaire, support URL, privacy URL, subscription disclosure text (see `docs/IOS_LAUNCH.md` for a draft) and the review notes below.
12. **Review notes.** Provide a review account whose email codes the reviewer can retrieve (a documented shared mailbox), or a review mailbox forwarder. Explain: the demo button explores sample data without an account; applications are sent only to public employer forms after the user taps Apply or authorizes auto-apply; AI is used only to select the user's own résumé paragraphs with consent; purchases are consumed as application allowance and never expire.
13. **Manual release.** Choose manual release, submit, and after approval release gradually while watching the operator status endpoint, purchase deliveries and support mail.

## Checks before every upload

- `python3 scripts/validate-mobile.py --release` passes.
- The private CI run for the commit is green: cloud tests on SQLite and PostgreSQL, premium tests including the Chromium and jevbrowse flows, native unit and UI tests, and the connected walkthrough against the loopback backend.
- `git status` is clean apart from the ignored `Configuration.plist`.
- The build number increased (the script uses the commit count).

## Known limits to keep out of the listing

- Auto-apply covers public Greenhouse, Lever and Ashby forms. Login walls, CAPTCHAs, Workday, LinkedIn and Indeed are not automated; those applications come back as *Needs attention* with the employer link.
- The relevance score is a model estimate of professional fit, never a hiring probability. Copy in the app already says so.
- A campaign's maximum counts queued attempts. Do not advertise a guaranteed number of submitted applications.
- Email notifications and résumé tailoring appear only when the server has the corresponding providers configured.
