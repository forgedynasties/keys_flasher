#!/usr/bin/env bash
set -e

# ============================================================
# Environment Variables (uncomment and set as needed)
# ============================================================
# export KEYS_FLASHER_ROOT="/path/to/keys_flasher"
# export KEYS_FLASHER_DATA_ROOT="/path/to/keys_flasher/data"

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

export KEYS_FLASHER_ROOT="$WORKDIR"
export KEYS_FLASHER_DATA_ROOT="$WORKDIR/data"

echo "========================================"
echo "  Keys Flasher - Desktop Launcher"
echo "========================================"
echo ""

# -- Print env vars --
echo "[ENV] KEYS_FLASHER_ROOT=$KEYS_FLASHER_ROOT"
echo "[ENV] KEYS_FLASHER_DATA_ROOT=$KEYS_FLASHER_DATA_ROOT"
echo ""

ERRORS=0

# -- Check python3 --
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found!"
    ERRORS=$((ERRORS + 1))
else
    echo "[OK] python3: $(python3 --version)"
fi

# -- Activate venv --
echo ""
echo "[VENV] Activating virtual environment..."
if [[ -f "$WORKDIR/venv/bin/activate" ]]; then
    echo "  Found: venv/"
    source "$WORKDIR/venv/bin/activate"
elif [[ -f "$WORKDIR/.venv/bin/activate" ]]; then
    echo "  Found: .venv/ (fallback)"
    source "$WORKDIR/.venv/bin/activate"
else
    echo "[ERROR] No venv or .venv found!"
    ERRORS=$((ERRORS + 1))
fi
echo "  Python: $(which python3)"
echo ""

# -- Check deps inside venv --
if ! python3 -c "import PyQt5" 2>/dev/null; then
    echo "[ERROR] PyQt5 not installed in venv!"
    ERRORS=$((ERRORS + 1))
else
    echo "[OK] PyQt5"
fi

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    echo "[ABORT] $ERRORS error(s) found. Fix before running."
    read -rp "Press Enter to close..."
    exit 1
fi

echo ""

# -- Ensure runtime dirs --
mkdir -p "$WORKDIR/data/logs" "$WORKDIR/data/errors"

# -- Prefer local qdl/adb --
if [[ -x "$WORKDIR/qdl" ]] || [[ -x "$WORKDIR/adb" ]]; then
    export PATH="$WORKDIR:$PATH"
fi

# -- Launch --
echo "[RUN] Launching main.py..."
echo "========================================"
echo ""
python3 "$WORKDIR/main.py"

EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
    echo ""
    echo "[EXIT] main.py exited with code $EXIT_CODE"
    read -rp "Press Enter to close..."
fi
