#!/usr/bin/env bash
set -euo pipefail

# source.sh - create a ZIP archive containing only the repository source files
# Usage: ./source.sh [output.zip]
# If no output name is provided, a timestamped archive will be created.

OUT=${1:-source_$(date +%Y%m%d_%H%M%S).zip}

echo "Creating source archive: $OUT"

# Candidate directories to include (only added if present)
POSSIBLE_DIRS=(data gui tests adb qdl core assets)
INCLUDES=()
for d in "${POSSIBLE_DIRS[@]}"; do
    if [ -d "$d" ]; then
        INCLUDES+=("$d")
    fi
done

# Top-level files to include if present
TOP_FILES=(README.md README.rst README LICENSE requirements.txt requirements-dev.txt main.py package.sh run.sh build_deb.sh)
for f in "${TOP_FILES[@]}"; do
    if [ -f "$f" ]; then
        INCLUDES+=("$f")
    fi
done

# Always include all shell scripts at repo root
sh_files=( *.sh )
for s in "${sh_files[@]}"; do
    if [ -f "$s" ]; then INCLUDES+=("$s"); fi
done

if [ ${#INCLUDES[@]} -eq 0 ]; then
    echo "No source files or directories found to include. Exiting." >&2
    exit 1
fi

# Exclude patterns (zip files, virtual envs, build outputs, binaries)
EXCLUDE_PATTERNS=(
    ".git/*"
    "venv/*"
    "venv/**"
    "**/*.zip"
    "**/*.deb"
    "dist/*"
    "build/*"
    "__pycache__/*"
    "**/*.pyc"
    "**/*.pyz"
    "**/*.exe"
    "**/*.so"
    "factory_binary_drop/*"
    "*.egg-info/*"
)

# Ensure zip is available
if ! command -v zip >/dev/null 2>&1; then
    echo "zip is not installed. Please install 'zip' and retry." >&2
    exit 2
fi

# Build exclude args while disabling pathname expansion so patterns are not expanded
set -f
EXCLUDE_ARGS=()
for p in "${EXCLUDE_PATTERNS[@]}"; do
    EXCLUDE_ARGS+=("-x" "$p")
done
set +f

echo "Including:"; printf '  %s
' "${INCLUDES[@]}"
echo "Excluding patterns:"; printf '  %s
' "${EXCLUDE_PATTERNS[@]}"

# Create the zip. Use -r to recurse included directories.
zip -r "$OUT" "${INCLUDES[@]}" "${EXCLUDE_ARGS[@]}"

echo "Archive created: $OUT"

exit 0
