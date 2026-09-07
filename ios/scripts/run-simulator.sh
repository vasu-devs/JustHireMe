#!/bin/bash
# Build, test, install, and capture the real iOS app on a Mac.
set -euo pipefail

if [ "$(uname -s)" != "Darwin" ]; then
  echo "A Mac with Xcode is required for the native iOS simulator." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
command -v xcodegen >/dev/null || { echo "Install XcodeGen with: brew install xcodegen" >&2; exit 2; }
xcodebuild -version
python3 scripts/validate-mobile.py
xcodegen generate --spec ios/project.yml

mkdir -p "$REPO_ROOT/ios/TestArtifacts"
RUN_DIR="$(mktemp -d "$REPO_ROOT/ios/TestArtifacts/run-XXXXXXXX")"
export RUN_DIR
printf '%s\n' "$RUN_DIR" > ios/TestArtifacts/latest-run.txt

SIM_ID="${SIMULATOR_ID:-}"
if [ -z "$SIM_ID" ]; then
  SIM_ID="$(xcrun simctl list devices available -j | python3 -c '
import json, sys
data = json.load(sys.stdin)
devices = [device for runtime, group in data["devices"].items() if "iOS" in runtime for device in group if "iPhone" in device["name"]]
booted = [device for device in devices if device["state"] == "Booted"]
if not devices:
    sys.exit("No iPhone simulator is installed. Install an iOS runtime in Xcode Settings > Components.")
print((booted or devices)[0]["udid"])
')"
fi
printf '%s\n' "$SIM_ID" > "$RUN_DIR/simulator-id.txt"

# The user requested simulation. Boot only this selected device if it isn't already booted.
BOOTED="$(xcrun simctl list devices -j | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((x["state"] for g in d["devices"].values() for x in g if x["udid"]==sys.argv[1]), "Missing"))' "$SIM_ID")"
if [ "$BOOTED" = "Missing" ]; then echo "The selected simulator does not exist." >&2; exit 2; fi
if [ "$BOOTED" != "Booted" ]; then xcrun simctl boot "$SIM_ID"; fi
xcrun simctl bootstatus "$SIM_ID" -b
xcrun simctl status_bar "$SIM_ID" override --time "9:41" --batteryState charged --batteryLevel 100

export_evidence() {
  if [ -d "$RUN_DIR/Tests.xcresult" ]; then
    xcrun xcresulttool export attachments --path "$RUN_DIR/Tests.xcresult" --output-path "$RUN_DIR/Screenshots" || true
  fi
  printf 'Native build artifacts: %s\n' "$RUN_DIR"
}
trap export_evidence EXIT

xcodebuild -project ios/JustHireMe.xcodeproj -scheme JustHireMe \
  -configuration Debug -destination "platform=iOS Simulator,id=$SIM_ID" \
  -derivedDataPath ios/DerivedData -resultBundlePath "$RUN_DIR/Tests.xcresult" \
  -parallel-testing-enabled NO CODE_SIGNING_ALLOWED=NO test 2>&1 | tee "$RUN_DIR/xcodebuild.log"

APP_PATH="$REPO_ROOT/ios/DerivedData/Build/Products/Debug-iphonesimulator/JustHireMe.app"
xcrun simctl install "$SIM_ID" "$APP_PATH"
xcrun simctl launch "$SIM_ID" com.justhireme.mobile --ui-testing --demo
sleep 3
xcrun simctl io "$SIM_ID" screenshot "$RUN_DIR/Workspace.png"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$RUN_DIR/JustHireMe-simulator.zip"
if [ "${CI:-}" != "true" ]; then open -a Simulator --args -CurrentDeviceUDID "$SIM_ID"; fi
