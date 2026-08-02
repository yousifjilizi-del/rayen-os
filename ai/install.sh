#!/bin/sh
# Install Rayen AI into the live system (run inside chroot)
set -e

DEST=/usr/share/rayen-ai
BIN=/usr/bin/rayen-ai
CONF=/etc/rayen-ai

mkdir -p "${DEST}/rayen_ai"
mkdir -p "${CONF}"

SRC=/usr/share/rayen-ai-src

# Copy Python package
cp -r "${SRC}/rayen_ai" "${DEST}/"
cp "${SRC}/rayen-ai" "${BIN}"
chmod +x "${BIN}"

# Install config (with API key if provided)
if [ -f "${SRC}/config/config.json" ]; then
    cp "${SRC}/config/config.json" "${CONF}/config.json"
fi

# Python deps are provided by the python3-* packages installed via package lists
python3 -m py_compile "${DEST}/rayen_ai/"*.py 2>/dev/null || true

# Expose llama-cli on PATH if bundled for offline AI
if [ -x "${DEST}/llama-cli" ] && [ ! -e /usr/local/bin/llama-cli ]; then
    ln -s "${DEST}/llama-cli" /usr/local/bin/llama-cli
fi

echo "Rayen AI installed."
