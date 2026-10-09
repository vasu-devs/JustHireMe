#!/bin/bash
# Reuse an already-built simulator app to inspect tablet layout without recompiling.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p ios/TabletArtifacts .tmp/ipad-app
XCODE_PATH=$(python3 -c 'import glob; print(sorted(glob.glob("/Applications/Xcode_26*.app"))[-1])')
sudo xcode-select -s "$XCODE_PATH/Contents/Developer"
APP_ZIP=$(python3 -c 'import glob; files=glob.glob(".tmp/tested-app/**/JustHireMe-simulator.zip", recursive=True); assert len(files)==1, files; print(files[0])')
shasum -a 256 "$APP_ZIP" > ios/TabletArtifacts/tested-app-sha256.txt
ditto -x -k "$APP_ZIP" .tmp/ipad-app
IPAD_TYPE=$(xcrun simctl list devicetypes -j | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(x["identifier"] for x in d["devicetypes"] if x["name"] == "iPad (10th generation)"))')
RUNTIME_ID=$(xcrun simctl list runtimes -j | python3 -c 'import json,sys; d=json.load(sys.stdin); r=[x for x in d["runtimes"] if x["isAvailable"] and "iOS" in x["name"]]; assert r, "An installed iOS runtime is required"; print(r[-1]["identifier"])')
IPAD_ID=$(xcrun simctl create 'JustHireMe tablet review' "$IPAD_TYPE" "$RUNTIME_ID")
printf '%s\n' "$IPAD_ID" "$RUNTIME_ID" > ios/TabletArtifacts/simulator.txt
xcrun simctl boot "$IPAD_ID"
xcrun simctl bootstatus "$IPAD_ID" -b
xcrun simctl status_bar "$IPAD_ID" override --time '9:41' --batteryState charged --batteryLevel 100
xcrun simctl install "$IPAD_ID" .tmp/ipad-app/JustHireMe.app
xcrun simctl launch "$IPAD_ID" com.justhireme.mobile --ui-testing --demo
sleep 4
xcrun simctl io "$IPAD_ID" screenshot ios/TabletArtifacts/Overview-iPad.png
test -s ios/TabletArtifacts/Overview-iPad.png
