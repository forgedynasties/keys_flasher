#!/usr/bin/env bash
set -e

# ============================================================
# Environment Variables (uncomment and set as needed)
# ============================================================
# export KEYS_FLASHER_ROOT="/path/to/keys_flasher"
# export KEYS_FLASHER_DATA_ROOT="/path/to/keys_flasher/data"

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

# -- Set env vars --
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

# -- Check dependencies --
echo "[DEPS] Checking dependencies..."

if ! command -v python3 &>/dev/null; then
    echo "[FAIL] python3 not found. Install python3."
    read -rp "Press Enter to exit..."
    exit 1
fi
echo "  python3: $(python3 --version)"

if ! command -v pip3 &>/dev/null && ! command -v pip &>/dev/null; then
    echo "[WARN] pip not found. May not be able to install deps."
else
    echo "  pip: $(pip3 --version 2>/dev/null || pip --version)"
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
    echo "[WARN] No venv or .venv found. Running with system python."
fi
echo "  Python: $(which python3)"
echo "  Version: $(python3 --version)"
echo ""

# -- Check PyQt5 --
echo "[DEPS] Checking PyQt5..."
if python3 -c "import PyQt5" 2>/dev/null; then
    echo "  PyQt5: OK"
else
    echo "  PyQt5: MISSING - installing from requirements.txt..."
    pip3 install -r "$WORKDIR/requirements.txt"
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
