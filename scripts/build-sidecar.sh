#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
TARGET_DIR="src-tauri/resources/backend"

export UV_CACHE_DIR="$REPO_ROOT/backend/.uv-cache"
export PYTHONNOUSERSITE="1"
export PYINSTALLER_CONFIG_DIR="$REPO_ROOT/backend/.pyinstaller-cache"
export HF_HOME="$REPO_ROOT/backend/.hf-cache"

echo "Building Python sidecar..."
rm -rf "$TARGET_DIR"
rm -f "${TARGET_DIR}.exe"

cd backend
uv run pyinstaller backend.spec --distpath ../src-tauri/resources/backend --noconfirm --clean
cd ..

TRIPLE="$(rustc -vV | awk '/host:/ {print $2}')"

if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "win"* ]]; then
  SRC="$TARGET_DIR/backend.exe"
  DST="$TARGET_DIR/backend-${TRIPLE}.exe"
else
  SRC="$TARGET_DIR/backend"
  DST="$TARGET_DIR/backend-${TRIPLE}"
fi

if [[ ! -f "$SRC" ]]; then
  echo "Expected sidecar was not created: $SRC" >&2
  exit 1
fi

cp "$SRC" "$DST"
chmod +x "$DST" 2>/dev/null || true
echo "Sidecar ready: $DST"
