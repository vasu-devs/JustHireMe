"""Portable structural checks; this does not replace an Xcode build."""
import json
import plistlib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "ios").rglob("*.plist"):
    if path.name == "Configuration.plist":
        continue
    with path.open("rb") as stream:
        plistlib.load(stream)
with (ROOT / "ios/JustHireMe/PrivacyInfo.xcprivacy").open("rb") as stream:
    privacy = plistlib.load(stream)
assert privacy["NSPrivacyTracking"] is False
for path in (ROOT / "ios/JustHireMe/Assets.xcassets").rglob("Contents.json"):
    json.loads(path.read_text())
assert (ROOT / "ios/Branding.png").is_file()
swift = "\n".join(p.read_text() for p in (ROOT / "ios/JustHireMe").glob("*.swift"))
assert "signed_transaction" in swift and "transaction.finish()" in swift
assert "kSecAttrAccessibleWhenUnlockedThisDeviceOnly" in swift
assert not re.search(r"(?:sk-ant-|service_role\s*=)", swift)
assert "NSAllowsArbitraryLoads" not in (ROOT / "ios/JustHireMe/Info.plist").read_text()
if "--release" in sys.argv:
    path = ROOT / "ios/JustHireMe/Configuration.plist"
    assert path.is_file(), "Release requires ios/JustHireMe/Configuration.plist"
    with path.open("rb") as stream:
        config = plistlib.load(stream)
    for name in ("APIBaseURL", "SupabaseURL", "PrivacyURL", "SupportURL", "TermsURL"):
        value = config.get(name, "")
        url = urlparse(value)
        assert url.scheme == "https" and url.hostname and "REPLACE" not in value, f"Configure {name} for release"
        assert not url.hostname.endswith("example.com"), f"Replace the example {name}"
    assert config.get("SupabasePublicKey") and "REPLACE" not in config["SupabasePublicKey"], "Configure the public auth key"
print("Mobile plist, asset, and configuration checks passed. Swift compilation requires Xcode.")
