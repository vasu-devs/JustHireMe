#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

TARGET_DIR="src-tauri/resources/backend"

echo "Building Python sidecar..."
cd backend
uv run pyinstaller backend.spec --distpath ../src-tauri/resources/backend --noconfirm
cd ..

echo "Sidecar built at: $TARGET_DIR"
echo "Rename the binary for Tauri's triple-target naming..."

TRIPLE=$(rustc -vV | grep 'host:' | awk '{print $2}')

if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "win"* ]]; then
  SRC="$TARGET_DIR/backend.exe"
  DST="$TARGET_DIR/backend-${TRIPLE}.exe"
else
  SRC="$TARGET_DIR/backend"
  DST="$TARGET_DIR/backend-${TRIPLE}"
fi

cp "$SRC" "$DST"
chmod +x "$DST" 2>/dev/null || true
echo "Sidecar ready: $DST"
