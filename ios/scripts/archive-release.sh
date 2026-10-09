#!/bin/bash
# Archive the signed Release build and upload it to App Store Connect (TestFlight) from a Mac.
#
# Required environment:
#   APPLE_TEAM_ID   10-character Apple Developer Team ID
#   ASC_KEY_ID      App Store Connect API key ID (Users and Access > Integrations > App Store Connect API)
#   ASC_ISSUER_ID   Issuer ID shown on the same page
#   ASC_KEY_PATH    Path to the downloaded AuthKey_<KEY_ID>.p8 (never committed)
# Optional:
#   BUILD_NUMBER    CURRENT_PROJECT_VERSION for this archive (default: commit count, always increasing)
#   UPLOAD=0        Export a local .ipa instead of uploading
#
# ios/JustHireMe/Configuration.plist (ignored by Git) must contain the production HTTPS API,
# Supabase URL/public key and the live privacy/support/terms pages; validate-mobile.py checks it.
set -euo pipefail

if [ "$(uname -s)" != "Darwin" ]; then
  echo "A Mac with Xcode 26+ is required to archive for the App Store." >&2
  exit 2
fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
: "${APPLE_TEAM_ID:?Set APPLE_TEAM_ID to the Apple Developer Team ID}"
: "${ASC_KEY_ID:?Set ASC_KEY_ID to the App Store Connect API key ID}"
: "${ASC_ISSUER_ID:?Set ASC_ISSUER_ID to the App Store Connect issuer ID}"
: "${ASC_KEY_PATH:?Set ASC_KEY_PATH to the AuthKey .p8 file}"
test -f "$ASC_KEY_PATH" || { echo "ASC_KEY_PATH does not exist: $ASC_KEY_PATH" >&2; exit 2; }
KEY_PATH="$(cd "$(dirname "$ASC_KEY_PATH")" && pwd)/$(basename "$ASC_KEY_PATH")"
BUILD_NUMBER="${BUILD_NUMBER:-$(git rev-list --count HEAD)}"
command -v xcodegen >/dev/null || { echo "Install XcodeGen with: brew install xcodegen" >&2; exit 2; }

xcodebuild -version
python3 scripts/validate-mobile.py --release
xcodegen generate --spec ios/project.yml

OUT="$REPO_ROOT/ios/TestArtifacts/release-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
printf '%s\n' "$OUT" > ios/TestArtifacts/latest-release.txt
EXPORT_OPTIONS="$OUT/ExportOptions.plist"
cp ios/ExportOptions.plist "$EXPORT_OPTIONS"
/usr/libexec/PlistBuddy -c "Set :teamID $APPLE_TEAM_ID" "$EXPORT_OPTIONS"
if [ "${UPLOAD:-1}" != "1" ]; then
  /usr/libexec/PlistBuddy -c "Set :destination export" "$EXPORT_OPTIONS"
fi

MARKETING_VERSION="$(sed -n 's/^ *MARKETING_VERSION: *"\(.*\)"/\1/p' ios/project.yml | head -1)"
echo "Archiving JustHireMe ${MARKETING_VERSION} (${BUILD_NUMBER}) for team ${APPLE_TEAM_ID}"

xcodebuild -project ios/JustHireMe.xcodeproj -scheme JustHireMe -configuration Release \
  -destination "generic/platform=iOS" -archivePath "$OUT/JustHireMe.xcarchive" \
  -derivedDataPath ios/DerivedData \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
  -allowProvisioningUpdates -allowProvisioningDeviceRegistration \
  -authenticationKeyPath "$KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID" \
  archive 2>&1 | tee "$OUT/archive.log"

xcodebuild -exportArchive -archivePath "$OUT/JustHireMe.xcarchive" \
  -exportOptionsPlist "$EXPORT_OPTIONS" -exportPath "$OUT/export" \
  -allowProvisioningUpdates \
  -authenticationKeyPath "$KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID" \
  2>&1 | tee "$OUT/export.log"

if [ "${UPLOAD:-1}" = "1" ]; then
  echo "Uploaded build ${MARKETING_VERSION} (${BUILD_NUMBER}). It appears in App Store Connect > TestFlight after Apple processes it."
else
  ls -l "$OUT/export"
  echo "Exported .ipa to $OUT/export (not uploaded)."
fi
