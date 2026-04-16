#!/usr/bin/env bash
set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$HOME/Desktop"
DESKTOP_FILE="$DESKTOP_DIR/keys-flasher.desktop"

mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Keys Flasher
Comment=AIO Keys Flasher Tool
Exec=bash -c 'cd $WORKDIR && ./run-desktop.sh; exec bash'
Icon=$WORKDIR/aio.png
Terminal=true
Type=Application
Categories=Utility;Development;
StartupNotify=false
EOF

chmod +x "$DESKTOP_FILE"

echo "Desktop shortcut created: $DESKTOP_FILE"
