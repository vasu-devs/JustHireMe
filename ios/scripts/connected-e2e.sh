#!/bin/bash
# Called by run-simulator.sh after compiling the native test bundle.
set -euo pipefail
: "${RUN_DIR:?}" "${SIM_ID:?}"
PYTHON="${E2E_PYTHON:-python3}"
export PYTHONPATH="$PWD/cloud:$PWD/premium"
export RESUME_FONT_PATH="$PWD/ios/JustHireMe/Fonts/InstrumentSans-Regular.ttf"
SERVER_PID=""
VIDEO_PID=""
cleanup() {
  local status=$?
  if [ -n "$VIDEO_PID" ]; then kill -INT "$VIDEO_PID" 2>/dev/null || true; wait "$VIDEO_PID" 2>/dev/null || true; fi
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; fi
  if [ -d "$RUN_DIR/Connected.xcresult" ]; then
    xcrun xcresulttool export attachments --path "$RUN_DIR/Connected.xcresult" --output-path "$RUN_DIR/ConnectedScreenshots" || true
  fi
  return "$status"
}
trap cleanup EXIT
"$PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",8769)); s.close()'
"$PYTHON" premium/tests/ios_e2e_server.py --directory "$RUN_DIR/backend" > "$RUN_DIR/connected-server.log" 2>&1 &
SERVER_PID=$!
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8769/health > /dev/null; then break; fi
  kill -0 "$SERVER_PID" || { cat "$RUN_DIR/connected-server.log"; exit 1; }
  sleep 1
done
curl --fail --silent http://127.0.0.1:8769/__test/evidence > "$RUN_DIR/connected-before.json"
xcrun simctl io "$SIM_ID" recordVideo --codec=h264 "$RUN_DIR/ConnectedRaw.mp4" > "$RUN_DIR/connected-recording.log" 2>&1 &
VIDEO_PID=$!
xcodebuild -project ios/JustHireMe.xcodeproj -scheme JustHireMe \
  -configuration Debug -destination "platform=iOS Simulator,id=$SIM_ID" \
  -derivedDataPath ios/DerivedData -resultBundlePath "$RUN_DIR/Connected.xcresult" \
  -parallel-testing-enabled NO -only-testing:JustHireMeUITests/ConnectedWalkthroughUITests \
  CODE_SIGNING_ALLOWED=NO test-without-building 2>&1 | tee "$RUN_DIR/connected.log"
kill -INT "$VIDEO_PID"
wait "$VIDEO_PID" || true
VIDEO_PID=""
curl --fail --silent http://127.0.0.1:8769/__test/evidence > "$RUN_DIR/connected-evidence.json"
"$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["submitted"] == d["employer_calls"] == d["unique_employer_calls"] == d["resume_count"] == d["emails"] == 3; assert d["balance"] == 185 and not d["worker_errors"]; print("Connected API, worker, PDF, credit and notification assertions passed")' "$RUN_DIR/connected-evidence.json"
ffmpeg -hide_banner -loglevel warning -y -i "$RUN_DIR/ConnectedRaw.mp4" -vf 'scale=720:-2,fps=30' -c:v libx264 -preset fast -crf 22 -threads 2 -an -movflags +faststart "$RUN_DIR/ConnectedWalkthrough.mp4"
