#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_USER="${GENUS_USER:-$(id -un)}"
GENUS_HOME="${GENUS_HOME:-$HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
SERVICE_PATH="/etc/systemd/system/genus-network-watchdog.service"
TIMER_PATH="/etc/systemd/system/genus-network-watchdog.timer"

mkdir -p "$(dirname "$DB_PATH")" "$LOG_DIR"
chmod +x "$REPO_DIR/deploy/pi_network_watchdog.sh"

tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"
cleanup() {
    rm -f "$tmp_service" "$tmp_timer"
}
trap cleanup EXIT

cat > "$tmp_service" <<EOF
[Unit]
Description=GENUS network watchdog
After=network.target

[Service]
Type=oneshot
Environment=GENUS_USER=$GENUS_USER
Environment=GENUS_HOME=$GENUS_HOME
Environment=GENUS_REPO_DIR=$REPO_DIR
Environment=GENUS_DB_PATH=$DB_PATH
Environment=GENUS_LOG_DIR=$LOG_DIR
Environment=GENUS_CORE_ID=${GENUS_CORE_ID:-}
ExecStart=/bin/bash $REPO_DIR/deploy/pi_network_watchdog.sh
StandardOutput=append:$LOG_DIR/network-watchdog.log
StandardError=append:$LOG_DIR/network-watchdog.log
EOF

cat > "$tmp_timer" <<'EOF'
[Unit]
Description=Run GENUS network watchdog every five minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo install -m 0644 "$tmp_service" "$SERVICE_PATH"
sudo install -m 0644 "$tmp_timer" "$TIMER_PATH"
sudo systemctl daemon-reload
sudo systemctl enable --now genus-network-watchdog.timer

echo "[WATCHDOG] installed genus-network-watchdog.timer"
echo "[WATCHDOG] user=$GENUS_USER"
echo "[WATCHDOG] repo=$REPO_DIR"
echo "[WATCHDOG] db=$DB_PATH"
echo "[WATCHDOG] logs=$LOG_DIR/network-watchdog.log"
systemctl list-timers --all genus-network-watchdog.timer
