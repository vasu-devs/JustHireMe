"""Portable structural checks for the iOS app; this does not replace an Xcode build.

Run from any OS. `--release` additionally requires the ignored production Configuration.plist.
"""
import json
import plistlib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ios/JustHireMe"


def fail(message):
    raise SystemExit(f"validate-mobile: {message}")


for path in (ROOT / "ios").rglob("*.plist"):
    if path.name == "Configuration.plist":
        continue
    with path.open("rb") as stream:
        plistlib.load(stream)

with (APP / "Info.plist").open("rb") as stream:
    info = plistlib.load(stream)
if info.get("ITSAppUsesNonExemptEncryption") is not False:
    fail("Info.plist must answer export compliance with ITSAppUsesNonExemptEncryption=false")
if "NSAllowsArbitraryLoads" in (APP / "Info.plist").read_text(encoding="utf-8"):
    fail("Never allow arbitrary loads")
ipad = set(info.get("UISupportedInterfaceOrientations~ipad", []))
if len(ipad) != 4 and not info.get("UIRequiresFullScreen"):
    fail("iPad builds must support all four orientations or set UIRequiresFullScreen")
launch = info.get("UILaunchScreen", {})
color = launch.get("UIColorName")
if not color or not (APP / f"Assets.xcassets/{color}.colorset/Contents.json").is_file():
    fail("UILaunchScreen.UIColorName must name a color set in Assets.xcassets")
if info.get("CFBundleShortVersionString") != "$(MARKETING_VERSION)" or info.get("CFBundleVersion") != "$(CURRENT_PROJECT_VERSION)":
    fail("Version keys must come from build settings")

project = (ROOT / "ios/project.yml").read_text(encoding="utf-8")
version = re.search(r'MARKETING_VERSION:\s*"([^"]+)"', project)
if not version or not re.fullmatch(r"\d+\.\d+\.\d+", version.group(1)):
    fail("MARKETING_VERSION must be a three-part version in ios/project.yml")
if "PRODUCT_BUNDLE_IDENTIFIER: com.justhireme.mobile" not in project:
    fail("Bundle identifier changed; update App Store Connect, the cloud verifier and this check together")

with (APP / "PrivacyInfo.xcprivacy").open("rb") as stream:
    privacy = plistlib.load(stream)
if privacy["NSPrivacyTracking"] is not False or privacy.get("NSPrivacyTrackingDomains"):
    fail("The app does not track; the privacy manifest must say so")
reasons = {item["NSPrivacyAccessedAPIType"]: item["NSPrivacyAccessedAPITypeReasons"]
           for item in privacy.get("NSPrivacyAccessedAPITypes", [])}
swift = "\n".join(p.read_text(encoding="utf-8") for p in APP.glob("*.swift"))
if "UserDefaults" in swift and "CA92.1" not in reasons.get("NSPrivacyAccessedAPICategoryUserDefaults", []):
    fail("UserDefaults is used; declare NSPrivacyAccessedAPICategoryUserDefaults with reason CA92.1")
if re.search(r"\.(creationDate|contentModificationDate|fileModificationDate|attributesOfItem)\b", swift) \
        and "NSPrivacyAccessedAPICategoryFileTimestamp" not in reasons:
    fail("File timestamp APIs need a declared reason")
collected = {item["NSPrivacyCollectedDataType"] for item in privacy.get("NSPrivacyCollectedDataTypes", [])}
for required in ("NSPrivacyCollectedDataTypeEmailAddress", "NSPrivacyCollectedDataTypeName",
                 "NSPrivacyCollectedDataTypeUserID", "NSPrivacyCollectedDataTypePurchaseHistory",
                 "NSPrivacyCollectedDataTypeOtherUserContent", "NSPrivacyCollectedDataTypePhoneNumber"):
    if required not in collected:
        fail(f"Privacy manifest is missing {required}")
if "NSPrivacyCollectedDataTypeCoarseLocation" in collected and "CoreLocation" not in swift:
    fail("Coarse location is declared but CoreLocation is never used")

for path in (APP / "Assets.xcassets").rglob("Contents.json"):
    json.loads(path.read_text(encoding="utf-8"))
if not (ROOT / "ios/Branding.png").is_file():
    fail("ios/Branding.png (the icon source) is missing")
if "signed_transaction" not in swift or "transaction.finish()" not in swift:
    fail("StoreKit delivery must post the signed transaction before finishing it")
if "kSecAttrAccessibleWhenUnlockedThisDeviceOnly" not in swift:
    fail("Keychain sessions must be device-only")
if re.search(r"(?:sk-ant-|service_role\s*=|sb_secret_)", swift):
    fail("A server secret appears in the app source")
if "Delete account" not in swift:
    fail("Apple requires in-app account deletion")
if not re.search(r'url\("PrivacyURL"\)', swift) or not re.search(r'url\("TermsURL"\)', swift):
    fail("Privacy and terms links must be shown from Configuration.plist")

for script in ("run-simulator.sh", "connected-e2e.sh", "capture-ipad.sh", "archive-release.sh"):
    if not (ROOT / "ios/scripts" / script).is_file():
        fail(f"ios/scripts/{script} is missing")
with (ROOT / "ios/ExportOptions.plist").open("rb") as stream:
    export = plistlib.load(stream)
if export.get("method") != "app-store-connect" or export.get("signingStyle") != "automatic":
    fail("ExportOptions.plist must target App Store Connect with automatic signing")

if "--release" in sys.argv:
    path = APP / "Configuration.plist"
    if not path.is_file():
        fail("Release requires ios/JustHireMe/Configuration.plist (copy ios/Configuration.example.plist)")
    with path.open("rb") as stream:
        config = plistlib.load(stream)
    for name in ("APIBaseURL", "SupabaseURL", "PrivacyURL", "SupportURL", "TermsURL"):
        value = config.get(name, "")
        url = urlparse(value)
        if url.scheme != "https" or not url.hostname or "REPLACE" in value:
            fail(f"Configure {name} for release")
        if url.hostname.endswith("example.com") or url.hostname in ("localhost", "127.0.0.1"):
            fail(f"Replace the placeholder {name}")
    key = config.get("SupabasePublicKey", "")
    if not key or "REPLACE" in key or key.startswith("sb_secret_") or "service_role" in key:
        fail("Configure the public Supabase key (never a secret key)")
print("Mobile plist, privacy manifest, asset, release tooling and configuration checks passed. Swift compilation requires Xcode.")
