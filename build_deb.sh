#!/usr/bin/env bash
set -e

# Build a Debian package (.deb) with app binary and data files.
# Requires: python3, pip, pyinstaller, dpkg-deb

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

if [[ ! -d dist ]]; then
  mkdir -p dist
fi

echo "1) Build onefile binary with pyinstaller..."
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install pyinstaller
pyinstaller --onefile --name keys_flasher --hidden-import PyQt5 --collect-all PyQt5 main.py

BINARY="dist/keys_flasher"
if [[ ! -f "$BINARY" ]]; then
  echo "Binary not found: $BINARY"
  exit 1
fi

PKG_DIR="deb_package"
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/local/bin"
mkdir -p "$PKG_DIR/usr/share/keys_flasher"
mkdir -p "$PKG_DIR/usr/share/doc/keys_flasher"

cat > "$PKG_DIR/DEBIAN/control" <<'EOF'
Package: keys-flasher
Version: 1.0.0
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Factory Team <factory@example.com>
Depends: python3, python3-pyqt5, adb
Description: Keybox firmware flashing desktop tool.
 A Debian package containing the compiled keybox flashing desktop app and required data assets.
EOF

cp "$BINARY" "$PKG_DIR/usr/local/bin/keys_flasher"
chmod 755 "$PKG_DIR/usr/local/bin/keys_flasher"

# Copy data assets and static files
mkdir -p "$PKG_DIR/usr/share/keys_flasher/data"
for d in keyboxes firmwares rkp_factory_extraction_tool csrs errors logs; do
  if [[ -e "data/$d" ]]; then
    cp -r "data/$d" "$PKG_DIR/usr/share/keys_flasher/data/" 2>/dev/null || true
  fi
done
mkdir -p "$PKG_DIR/usr/share/keys_flasher/data/logs"
mkdir -p "$PKG_DIR/usr/share/keys_flasher/data/errors"

for asset in app_icon.ico aio.png; do
  if [[ -f "$asset" ]]; then
    cp "$asset" "$PKG_DIR/usr/share/keys_flasher/" 2>/dev/null || true
  fi
done

# Install docs and extras
cp FACTORY_PACKAGE.md "$PKG_DIR/usr/share/doc/keys_flasher/README_FACTORY.md" 2>/dev/null || true
cp run.sh "$PKG_DIR/usr/share/doc/keys_flasher/run.sh" 2>/dev/null || true

# Postinst: ensure logs dir and run permissions
cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
mkdir -p /var/log/keys_flasher
chmod 755 /var/log/keys_flasher
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# Optional preinst + prerm can be added.

# Build package
DEB_FILE="keys-flasher_1.0.0_amd64.deb"
dpkg-deb --build "$PKG_DIR" "$DEB_FILE"

echo "Created Debian package: $DEB_FILE"
