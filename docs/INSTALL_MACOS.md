# Installing JustHireMe on macOS

JustHireMe's macOS builds are **ad-hoc signed but not yet notarized** by Apple
(notarization requires an Apple Developer Program membership; it's on the
roadmap). Because of that, Gatekeeper shows one of these on first launch:

> "Apple could not verify "JustHireMe" is free of malware that may harm your
> Mac or compromise your privacy."

> ""JustHireMe" is damaged and can't be opened. You should move it to the Bin."

The app is not damaged — this is macOS's standard warning for any app
distributed outside the App Store without notarization. Every release is built
in public by GitHub Actions directly from the tagged source; you can audit the
exact workflow run for your download.

## Open it anyway (choose one)

**Option A — System Settings (macOS 15 Sequoia / 26 Tahoe):**
1. Double-click the app once (it will be blocked).
2. Open **System Settings → Privacy & Security**, scroll to the Security
   section.
3. Next to *"JustHireMe" was blocked*, click **Open Anyway**, then confirm.

**Option B — Right-click Open (older macOS):**
1. In Applications, **right-click (or Control-click) JustHireMe.app → Open**.
2. In the dialog, click **Open**. This only needs doing once.

**Option C — Terminal (removes the quarantine flag directly):**
```sh
xattr -cr /Applications/JustHireMe.app
```
Then launch normally.

## Which download do I need?

| Mac | Asset |
| --- | --- |
| Apple Silicon (M1/M2/M3/M4…) | `JustHireMe_x.y.z_aarch64.dmg` |
| Intel (x86_64) | No pre-built binary yet — see below |

**Intel Macs:** there is no pre-built installer yet because a core dependency
(`lancedb`) publishes no Intel-mac wheels. As of this fix, building from source
on an Intel Mac works: `uv sync` now skips `lancedb` on `x86_64` macOS and the
app degrades gracefully to hashing-based matching (semantic vector search is
disabled; everything else works). See issue #63 for status on a pre-built
Intel/universal binary.

## Still stuck?

Open an issue with your macOS version and the exact dialog text:
https://github.com/vasu-devs/JustHireMe/issues
