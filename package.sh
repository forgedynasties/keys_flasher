#!/usr/bin/env bash
set -e

# package.sh: Build and package the factory desktop release.
# It assumes you already generated a binary in dist/ (e.g. via pyinstaller).

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

RELEASE_DIR="factory_package"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# Copy runtime files (for factory, prefer compiled binary distribution)
if [[ -f "dist/main" ]]; then
  echo "Using compiled binary dist/main"
  cp -v dist/main "$RELEASE_DIR/"
  # optional data includes, plus run wrapper to call binary
elif [[ -f "dist/main.exe" ]]; then
  cp -v dist/main.exe "$RELEASE_DIR/"
else
  echo "No compiled binary found in dist/. Falling back to source files (not ideal for final factory drop)."
  cp -v main.py "$RELEASE_DIR/"
  mkdir -p "$RELEASE_DIR/gui" "$RELEASE_DIR/core" "$RELEASE_DIR/assets" "$RELEASE_DIR/data/keyboxes" "$RELEASE_DIR/data/rkp_factory_extraction_tool" "$RELEASE_DIR/data/logs" "$RELEASE_DIR/data/errors"
  cp -rv gui/* "$RELEASE_DIR/gui/"
  cp -rv core/* "$RELEASE_DIR/core/"
  cp -rv assets/* "$RELEASE_DIR/assets/" 2>/dev/null || true
  cp -rv data/keyboxes/* "$RELEASE_DIR/data/keyboxes/" 2>/dev/null || true
  cp -rv data/rkp_factory_extraction_tool "$RELEASE_DIR/data/" 2>/dev/null || true
fi

# Include essentials: QDL files + firmware + ADB wrappers
mkdir -p "$RELEASE_DIR/tools/adb" "$RELEASE_DIR/tools/qdl"
cp -rv tools/adb/* "$RELEASE_DIR/tools/adb/" 2>/dev/null || true
cp -rv tools/qdl/* "$RELEASE_DIR/tools/qdl/" 2>/dev/null || true
mkdir -p "$RELEASE_DIR/data/firmwares"
cp -rv data/firmwares/* "$RELEASE_DIR/data/firmwares/" 2>/dev/null || true

# Include packaging helpers and docs
cp -v run.sh "$RELEASE_DIR/"
cp -v FACTORY_PACKAGE.md "$RELEASE_DIR/README_FACTORY.md"
cp -v requirements.txt "$RELEASE_DIR/"

# Create final zip
ZIP_NAME="flasher_tool_factory_$(date +%Y%m%d_%H%M%S).zip"
rm -f "$ZIP_NAME"
zip -r "$ZIP_NAME" "$RELEASE_DIR"

echo "Packaged: $ZIP_NAME"