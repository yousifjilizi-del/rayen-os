#!/usr/bin/env bash
# fix.sh — Rayen OS fix script
# Run this on the Linux build machine before building.
# It fixes line endings, BOM, and file permissions.
set -euo pipefail

echo "=== Rayen OS Fix Script ==="

# 1. Fix line endings (CRLF → LF) for all shell/script files
echo "[1/4] Converting CRLF to LF..."
find . -type f \( -name "*.sh" -o -name "*.chroot" -o -name "config" -path "*/auto/*" \) \
  -exec sed -i 's/\r$//' {} \;
echo "  Done."

# 2. Remove UTF-8 BOM if present
echo "[2/4] Removing UTF-8 BOM..."
find . -type f \( -name "*.sh" -o -name "*.chroot" -o -name "*.yml" -o -name "config" \) \
  -exec sed -i '1s/^\xEF\xBB\xBF//' {} \;
echo "  Done."

# 3. Set proper permissions
echo "[3/4] Setting permissions..."
find . -name "*.sh" -exec chmod +x {} \;
find config/hooks -type f -exec chmod +x {} \;
find config/auto -type f -exec chmod +x {} \;
echo "  Done."

# 4. Verify no CRLF remains
echo "[4/4] Verifying..."
if grep -rl $'\r$' config/ build.sh fix.sh 2>/dev/null; then
    echo "  WARNING: CRLF still found in files above"
else
    echo "  All files have Unix line endings. Ready to build."
fi

echo "=== Fix complete ==="
