#!/usr/bin/env bash
set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

echo "Building keys_flasher binary with pyinstaller..."

source .venv/bin/activate
pyinstaller --onefile --name keys_flasher --hidden-import PyQt5 --collect-all PyQt5 main.py

echo "Done. Binary at: dist/keys_flasher"
