# JustHireMe for iOS

The product is a pastel paper notebook with five sections: **Profile, For You, Applications, Grow, Plan**. Signed in, it uses the premium backend's `/v2` API for profile sync, job matches, one-tap apply, auto-apply campaigns, application timelines, generated résumés and learning progress; see [the connected walkthrough](../docs/IOS_CONNECTED_E2E.md) and [the API contract](../premium/docs/IOS_API.md). The **Explore the demo** button runs the same screens on sample data without an account, purchases, AI requests or employer contact.

Markdown, text and text-based PDFs are extracted on-device. The generated résumé for each application can be previewed, shared (AirDrop, Mail, Messages) or saved to Files. Missing employer questions, including yes/no authorization and consent checkboxes, are answered in the app and retried without a second charge.

## Native build and review

Use a Mac with Xcode 26+ and XcodeGen. The deployment target is iOS 17.

```sh
brew install xcodegen
python3 scripts/validate-mobile.py        # portable plist, privacy manifest and asset checks (any OS)
xcodegen generate --spec ios/project.yml
bash ios/scripts/run-simulator.sh          # build, unit + UI tests, screenshots, walkthrough recording
RUN_CONNECTED_E2E=1 bash ios/scripts/run-simulator.sh   # also the loopback backend walkthrough
```

Set `SIMULATOR_ID` to select an installed simulator. CI runs the same script on a hosted Mac and uploads screenshots, logs, the simulator app and recordings. A simulator app is not a signed iPhone build.

## Release to TestFlight and the App Store

1. Copy `ios/Configuration.example.plist` to the ignored `ios/JustHireMe/Configuration.plist` and fill the production HTTPS API, Supabase URL and **public** key, and the live privacy, support and terms pages. `python3 scripts/validate-mobile.py --release` must pass.
2. Archive, sign and upload with an App Store Connect API key (no certificates to manage by hand):
   ```sh
   export APPLE_TEAM_ID=XXXXXXXXXX ASC_KEY_ID=ABC123DEFG ASC_ISSUER_ID=<issuer uuid> ASC_KEY_PATH=~/AuthKey_ABC123DEFG.p8
   bash ios/scripts/archive-release.sh            # UPLOAD=0 exports a local .ipa instead
   ```
   The same runs from GitHub Actions as **iOS release to TestFlight** (`.github/workflows/ios-release.yml`) once the secrets are configured.
3. Follow [the submission runbook](../docs/APP_STORE_SUBMISSION.md) for the App Store Connect records, in-app purchase products, review notes and the device test list.

`MARKETING_VERSION` lives in `ios/project.yml`; the build number is the commit count at archive time. Export compliance (`ITSAppUsesNonExemptEncryption=false`), iPad orientations, the launch colour and the privacy manifest are checked by the validation script so a rejected upload is caught before Xcode.

[Screenshots and recorded walkthrough](../docs/IOS_NOTEBOOK_REVIEW.md) · [Validation history](../docs/IOS_VALIDATION.md) · [Original launch checklist](../docs/IOS_LAUNCH.md)
