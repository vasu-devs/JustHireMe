# JustHireMe for iOS

Native SwiftUI source for an iOS 17+ mobile edition of JustHireMe, with a separate multi-account cloud API in `../cloud`. The existing Tauri desktop app remains local-first.

Implemented: email-code sign-in, secure session refresh, profile editing and AI consent, saved opportunities, skill mentions, application status tracking, application drafts and sharing, weekly/monthly StoreKit subscriptions, consumable credits, purchase recovery, credit history, account export, and in-app deletion. An explicitly labelled demo is available without signing in. The demo contains fictional data and never takes payments or calls AI.

This is a first mobile implementation, not an App Store release. The native app compiled with Xcode 26.3 and passed five unit tests and three UI tests on an iPhone 16 Pro simulator in the [private CI run](https://github.com/vasu-devs/JustHireMe-iOS-private/actions/runs/34131799854). The app was installed and launched, and screenshots plus a simulator app archive were captured. Physical-device testing, real auth/AI/payment integration, signing, and TestFlight remain. Follow [the launch guide](../docs/IOS_LAUNCH.md) for the release gates.

## Build on a Mac

Use Xcode 26 or newer with an iOS 26 SDK for submission. The deployment target remains iOS 17.

```sh
brew install xcodegen
cp ios/Configuration.example.plist ios/JustHireMe/Configuration.plist
# Edit the copied plist with real HTTPS endpoints and the Supabase PUBLIC key.
xcodegen generate --spec ios/project.yml
open ios/JustHireMe.xcodeproj
```

Choose the JustHireMe scheme and an iPhone simulator, then Run. The project builds without configuration for exploring the labelled demo, but sign-in and live services require a configured API. Select your Apple signing team for a physical device. The build prepares an opaque app icon from the repository's existing brand artwork.

Run unit tests with Product → Test. Also test on an iPad, the smallest supported iPhone, dark mode, VoiceOver, and large Dynamic Type. CI in `.github/workflows/mobile.yml` runs an unsigned simulator build/test job; the verified run is linked above.

To build, run the native unit/UI tests, launch the demo in an iPhone simulator, and save screenshots in one command on a Mac:

```sh
bash ios/scripts/run-simulator.sh
```

Set `SIMULATOR_ID` to select a particular installed device. Otherwise the script prefers a booted iPhone and then an available iPhone. It boots the selected device if needed. The UI tests cover onboarding, tabs/plans/profile, creating a sample opportunity, updating its interview status, and disabled demo payments/drafting. They use only the explicitly labelled demo, with no live account or paid transactions.

Screenshots, an Xcode `.xcresult` bundle, build logs, and the simulator `.app` archive are saved under ignored `ios/TestArtifacts`. CI uploads these as `ios-simulator-evidence` on success or failure. The simulator app runs on compatible Mac simulators; it is not a signed device IPA. Live auth and Apple sandbox purchases remain separate integration tests.

## Services and persistence

The app connects to `/v1/*` in the new cloud service. It must never point to the existing desktop sidecar, whose endpoints and storage were designed for a local user. The client holds account content in memory, uses an ephemeral URLSession without a response cache, and stores only its authentication session in the iOS Keychain with `WhenUnlockedThisDeviceOnly`. Signing out clears in-memory account content and local tokens. Explicitly exported/shared data belongs to the user and is outside app storage.

StoreKit supplies localized product names and prices. Credit quantities come from the authenticated API. There is no locally writable wallet and no production grant endpoint. Transactions are finished only after the server records the purchase; unfinished transactions are retried after login and foregrounding. The backend's account UUID token binds each purchase to the original customer. Consumable balances are recovered by signing back into that account.

## Current feature boundary

Mobile users paste a job description and type/paste their experience. Drafting produces reviewable Markdown text. Automated discovery, résumé file import, graph/vector matching, PDF generation, desktop-to-cloud sync, and auto-apply are not implemented in this mobile edition. Skill mentions are transparent exact-text matches, not the desktop fit score. These boundaries are reflected in the UI; the launch description must not advertise the desktop-only features.

The cloud drafting adapter accepts explicit account inputs and uses a server-managed Anthropic API key. It intentionally does not load the desktop's shared profile, settings, filesystem, local CLI subscriptions, or browser session. Cloud source adapters and the fuller ranking pipeline need explicit tenant-safe interfaces before reuse.
