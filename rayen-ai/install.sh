#!/usr/bin/env bash
# Rayen AI — standalone installer
# Installs the Rayen AI assistant (daemon + CLI + desktop app) onto a running
# Debian/Ubuntu system. Useful for testing outside the live-build ISO, or for
# adding Rayen AI to an existing install.
#
#   sudo ./install.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAYEN_LOCAL_MODEL="${RAYEN_LOCAL_MODEL:-llama3.2:3b}"

info()  { echo -e "\033[1;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m   $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "Run as root: sudo ./install.sh"

info "Installing system packages..."
apt-get update -y || warn "apt update failed (continuing)"
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-requests python3-gi gir1.2-gtk-3.0 \
    curl ca-certificates || warn "Some packages may already be installed"

python3 -m pip install --break-system-packages --no-input requests 2>/dev/null || true

info "Installing Rayen AI files..."
mkdir -p /opt/rayen-ai/daemon /opt/rayen-ai/desktop /etc/rayen-ai
cp -r "$HERE/daemon/rayend" /opt/rayen-ai/daemon/
cp "$HERE/daemon/requirements.txt" /opt/rayen-ai/daemon/ 2>/dev/null || true
find /opt/rayen-ai -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

install -m 0755 "$HERE/cli/rayen" /usr/local/bin/rayen
install -m 0755 "$HERE/desktop/rayen-ai-chat.py" /opt/rayen-ai/desktop/rayen-ai-chat.py
install -m 0644 "$HERE/desktop/rayen-ai.png" /usr/share/pixmaps/rayen-ai.png 2>/dev/null || true
install -m 0644 "$HERE/desktop/rayen-ai.desktop" /usr/share/applications/rayen-ai.desktop 2>/dev/null || true

# Default config
if [ ! -f /etc/rayen-ai/config.json ]; then
    cat > /etc/rayen-ai/config.json << EOF
{
  "mode": "hybrid",
  "local_model": "${RAYEN_LOCAL_MODEL}",
  "cloud_provider": "",
  "require_confirmation": true
}
EOF
fi

info "Installing Ollama (local AI brain)..."
if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh || warn "Ollama install failed; install it manually later"
fi
systemctl enable --now ollama 2>/dev/null || true

info "Pulling local model ${RAYEN_LOCAL_MODEL} (may take a while)..."
if command -v ollama >/dev/null 2>&1; then
    for i in $(seq 1 30); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
    ollama pull "${RAYEN_LOCAL_MODEL}" || warn "Model pull failed; run 'ollama pull ${RAYEN_LOCAL_MODEL}' later"
fi

info "Installing systemd service..."
cat > /etc/systemd/system/rayend.service << 'EOF'
[Unit]
Description=Rayen AI system assistant daemon (rayend)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=/opt/rayen-ai/daemon
Environment=RAYEN_HOST=127.0.0.1
Environment=RAYEN_PORT=8765
WorkingDirectory=/opt/rayen-ai/daemon
ExecStart=/usr/bin/python3 -m rayend
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now rayend.service || warn "Could not start rayend; check 'systemctl status rayend'"

update-desktop-database /usr/share/applications 2>/dev/null || true

ok "Rayen AI installed."
echo ""
echo "  CLI:      rayen \"what's my disk usage?\""
echo "  Chat:     rayen chat        (interactive)"
echo "  Desktop:  search 'Rayen AI' in your app menu"
echo "  Status:   rayen status"
echo ""
echo "  Cloud (optional):"
echo "    rayen config cloud_provider=openai cloud_api_key=sk-...   then  rayen config mode=hybrid"
