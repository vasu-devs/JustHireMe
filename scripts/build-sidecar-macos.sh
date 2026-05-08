#!/bin/bash
set -e

echo "Building Python sidecar for macOS..."

cd backend

# Install dependencies
echo "Syncing dependencies..."
uv sync --dev

# Create output directory if it doesn't exist
mkdir -p ../src-tauri/binaries

# Build with PyInstaller
echo "Running PyInstaller..."
uv run pyinstaller backend.spec --distpath ../src-tauri/binaries --noconfirm

# Determine target triple
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  TARGET="aarch64-apple-darwin"
else
  TARGET="x86_64-apple-darwin"
fi

SIDECAR="../src-tauri/binaries/backend-$TARGET"

# Rename binary to include target triple
mv ../src-tauri/binaries/backend "$SIDECAR" 2>/dev/null || true

# Ad-hoc sign the binary
echo "Signing sidecar binary..."
codesign --force --deep --sign - "$SIDECAR"

echo "Done! Sidecar built at $SIDECAR"
