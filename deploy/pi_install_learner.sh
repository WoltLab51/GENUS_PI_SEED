#!/usr/bin/env bash
set -Eeuo pipefail

# Install the background vocabulary learner as a LONG-LIVED, lowest-priority systemd service.
# It runs continuously (word after word) under idle CPU and IO scheduling, so the kernel only
# lets it run in true idle time and it yields instantly to the punctual sensor ticks -- the
# "clever job timing" is the OS scheduler itself. Restart=always keeps it alive across reboots
# and hiccups. Stop it any time with `genus pause` (the daemon honors it) or `systemctl stop`.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_USER="${GENUS_USER:-$(id -un)}"
GENUS_HOME="${GENUS_HOME:-$HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
DELAY="${GENUS_LEARN_DELAY:-2}"
SERVICE_PATH="/etc/systemd/system/genus-learner.service"

mkdir -p "$(dirname "$DB_PATH")" "$LOG_DIR"
chmod +x "$REPO_DIR/deploy/pi_learn.sh"

tmp_service="$(mktemp)"
trap 'rm -f "$tmp_service"' EXIT

# Nice=19 + idle CPU/IO scheduling => the lowest possible priority: runs only when the box is
# otherwise idle, steps aside the instant anything else needs the CPU or disk.
cat > "$tmp_service" <<EOF
[Unit]
Description=GENUS background vocabulary learner (continuous, idle priority)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Nice=19
CPUSchedulingPolicy=idle
IOSchedulingClass=idle
Restart=always
RestartSec=30
Environment=GENUS_USER=$GENUS_USER
Environment=GENUS_HOME=$GENUS_HOME
Environment=GENUS_REPO_DIR=$REPO_DIR
Environment=GENUS_DB_PATH=$DB_PATH
Environment=GENUS_LOG_DIR=$LOG_DIR
Environment=GENUS_CORE_ID=${GENUS_CORE_ID:-}
Environment=GENUS_LEARN_DELAY=$DELAY
ExecStart=/bin/bash $REPO_DIR/deploy/pi_learn.sh
StandardOutput=append:$LOG_DIR/learn.log
StandardError=append:$LOG_DIR/learn.log

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$tmp_service" "$SERVICE_PATH"
sudo systemctl daemon-reload
sudo systemctl enable --now genus-learner.service

echo "[LEARNER] installed genus-learner.service (continuous, ${DELAY}s/word, idle priority)"
echo "[LEARNER] repo=$REPO_DIR  db=$DB_PATH  logs=$LOG_DIR/learn.log"
echo "[LEARNER] stop any time: genus pause   (or: sudo systemctl stop genus-learner.service)"
systemctl --no-pager status genus-learner.service | head -5
