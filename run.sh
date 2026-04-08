#!/usr/bin/env bash
set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

export KEYS_FLASHER_ROOT="$WORKDIR"
export KEYS_FLASHER_DATA_ROOT="$WORKDIR/data"

# 1) Uninstall previous installed key_flasher package/binary if present
if command -v keys_flasher >/dev/null 2>&1; then
  echo "Uninstalling existing keys_flasher from PATH..."
  EXISTING="$(command -v keys_flasher)"
  echo "Existing keys_flasher: $EXISTING"
  if [[ "$EXISTING" == "/usr/local/bin/keys_flasher" ]] || [[ "$EXISTING" == "/usr/bin/keys_flasher" ]]; then
    sudo rm -f "$EXISTING" || true
  fi
fi
if dpkg -s keys-flasher >/dev/null 2>&1; then
  echo "Removing installed keys-flasher Debian package..."
  sudo apt-get remove -y keys-flasher || true
  sudo apt-get purge -y keys-flasher || true
  sudo apt-get autoremove -y
fi

# 2) Install .deb if available
DEB="keys-flasher_1.0.0_amd64.deb"
if [[ -f "$DEB" ]]; then
  echo "Installing keys-flasher from .deb..."
  sudo dpkg -i "$DEB" || true
  sudo apt-get install -f -y
fi

# 3) Also install local binary overwriting if available
LOCAL_BIN=""
for candidate in "$WORKDIR/bin/keys_flasher" "$WORKDIR/keys_flasher" "$WORKDIR/main" "$WORKDIR/dist/keys_flasher"; do
  if [[ -x "$candidate" ]]; then
    LOCAL_BIN="$candidate"
    break
  fi
done

if [[ -n "$LOCAL_BIN" ]]; then
  echo "Installing local binary to /usr/local/bin/keys_flasher..."
  sudo cp "$LOCAL_BIN" /usr/local/bin/keys_flasher
  sudo chmod +x /usr/local/bin/keys_flasher
fi

# 3) Prefer local bundled qdl/adb if present
if [[ -x "$WORKDIR/qdl" ]]; then
  export PATH="$WORKDIR:$PATH"
fi
if [[ -x "$WORKDIR/adb" ]]; then
  export PATH="$WORKDIR:$PATH"
fi

# 4) Ensure runtime directories
mkdir -p "$WORKDIR/data/logs" "$WORKDIR/data/errors"

# 5) Launch
if command -v keys_flasher >& /dev/null; then
  echo "Launching installed keys_flasher..."
  keys_flasher
elif [[ -x "$WORKDIR/bin/keys_flasher" ]]; then
  echo "Launching local binary bin/keys_flasher..."
  "$WORKDIR/bin/keys_flasher"
elif [[ -x "$WORKDIR/main" ]]; then
  echo "Launching bundled binary main..."
  "$WORKDIR/main"
elif [[ -f "$WORKDIR/main.py" ]]; then
  echo "Launching Python source main.py..."
  python3 main.py
else
  echo "No launcher found (keys_flasher, main, or main.py)."
  exit 1
fi
