#!/usr/bin/env bash
set -e

# build_factory_zip_binary.sh
# Create a factory ZIP containing only runtime assets + compiled binary + tools.
# It intentionally excludes source directories (gui/, core/, etc.).

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

RELEASE_NAME="factory_binary_drop"
RELEASE_DIR="$WORKDIR/$RELEASE_NAME"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# 1) Pick compiled binary (priority: keys_flasher, main)
BINARY_PATH=""
if [[ -x "$WORKDIR/dist/keys_flasher" ]]; then
  BINARY_PATH="$WORKDIR/dist/keys_flasher"
elif [[ -x "$WORKDIR/dist/main" ]]; then
  BINARY_PATH="$WORKDIR/dist/main"
elif [[ -x "$WORKDIR/keys_flasher" ]]; then
  BINARY_PATH="$WORKDIR/keys_flasher"
elif [[ -x "$WORKDIR/main" ]]; then
  BINARY_PATH="$WORKDIR/main"
fi

if [[ -z "$BINARY_PATH" ]]; then
  echo "No compiled binary found. Build with pyinstaller or ensure dist/keys_flasher exists."
  exit 1
fi

mkdir -p "$RELEASE_DIR/bin"
cp -v "$BINARY_PATH" "$RELEASE_DIR/bin/" || true

# 2) Copy runtime tools qdl and adb if available
for tool in qdl adb; do
  if [[ -x "$WORKDIR/$tool" ]]; then
    cp -v "$WORKDIR/$tool" "$RELEASE_DIR/"
  elif [[ -x "$WORKDIR/tools/$tool/$tool" ]]; then
    mkdir -p "$RELEASE_DIR/tools/$tool"
    cp -v "$WORKDIR/tools/$tool/$tool" "$RELEASE_DIR/tools/$tool/"
  fi
done

# 3) Copy required data essentials for factory use
mkdir -p "$RELEASE_DIR/data"
for d in "data/csrs" "data/firmwares" "data/rkp_factory_extraction_tool" "data/keyboxes" "data/errors" "data/logs"; do
  if [[ -e "$WORKDIR/$d" ]]; then
    cp -rv "$WORKDIR/$d" "$RELEASE_DIR/data/"
  fi
done

# 4) Include launcher script and docs
cp -v run.sh "$RELEASE_DIR/" || true
cp -v FACTORY_PACKAGE.md "$RELEASE_DIR/" || true
cp -v keys-flasher_1.0.0_amd64.deb "$RELEASE_DIR/" 2>/dev/null || true

# 5) Minimal runtime asset files
for file in app_icon.ico aio.png; do
  if [[ -f "$WORKDIR/$file" ]]; then
    cp -v "$WORKDIR/$file" "$RELEASE_DIR/"
  fi
done

ZIP_NAME="factory_binary_drop_$(date +%Y%m%d_%H%M%S).zip"
rm -f "$WORKDIR/$ZIP_NAME"
cd "$WORKDIR"
zip -r "$ZIP_NAME" "$(basename "$RELEASE_DIR")" > /dev/null

echo "Created $ZIP_NAME with binary and essentials (no source)."
