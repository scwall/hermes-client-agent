#!/usr/bin/env bash
"""Install Hermes Agent as a systemd user service (Linux)."""
set -euo pipefail

SERVICE_NAME="hermes-agent"
EXE_SOURCE="$(dirname "$0")/../dist/hermes-agent"

if [ "${1:-}" = "--uninstall" ]; then
    echo "Uninstalling Hermes Agent..."
    systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$SERVICE_NAME.service"
    systemctl --user daemon-reload
    echo "Uninstall complete."
    exit 0
fi

if [ ! -f "$EXE_SOURCE" ]; then
    echo "ERROR: $EXE_SOURCE not found. Run './scripts/build.sh' first."
    exit 1
fi

INSTALL_DIR="${HOME}/.local/bin"
mkdir -p "$INSTALL_DIR"
cp "$EXE_SOURCE" "$INSTALL_DIR/hermes-agent"

mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/"

cat > "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$SERVICE_NAME.service" << EOF
[Unit]
Description=Hermes Remote Control Agent
After=network.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/hermes-agent
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"

echo "Hermes Agent installed and started as a user service."
echo "Check status: systemctl --user status $SERVICE_NAME"
