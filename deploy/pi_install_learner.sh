#!/usr/bin/env bash
set -Eeuo pipefail

# Install the background vocabulary learner as a LOWEST-priority systemd timer. The service
# runs pi_learn.sh under idle CPU and IO scheduling, so the kernel only lets it run in true
# idle time and it yields instantly to the punctual sensor ticks -- the "clever job timing"
# is the OS scheduler itself. The timer fires often but each run is a tiny, gated batch.
# Stop it any time with `genus pause` (the script honors it) or `systemctl stop`.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_USER="${GENUS_USER:-$(id -un)}"
GENUS_HOME="${GENUS_HOME:-$HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
BATCH="${GENUS_LEARN_BATCH:-10}"
INTERVAL="${GENUS_LEARN_INTERVAL:-3min}"
SERVICE_PATH="/etc/systemd/system/genus-learner.service"
TIMER_PATH="/etc/systemd/system/genus-learner.timer"

mkdir -p "$(dirname "$DB_PATH")" "$LOG_DIR"
chmod +x "$REPO_DIR/deploy/pi_learn.sh"

tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"
cleanup() { rm -f "$tmp_service" "$tmp_timer"; }
trap cleanup EXIT

# Nice=19 + idle CPU/IO scheduling => the lowest possible priority. It runs only when the
# box is otherwise idle and steps aside the instant anything else needs the CPU or disk.
cat > "$tmp_service" <<EOF
[Unit]
Description=GENUS background vocabulary learner
After=network-online.target

[Service]
Type=oneshot
Nice=19
CPUSchedulingPolicy=idle
IOSchedulingClass=idle
Environment=GENUS_USER=$GENUS_USER
Environment=GENUS_HOME=$GENUS_HOME
Environment=GENUS_REPO_DIR=$REPO_DIR
Environment=GENUS_DB_PATH=$DB_PATH
Environment=GENUS_LOG_DIR=$LOG_DIR
Environment=GENUS_CORE_ID=${GENUS_CORE_ID:-}
Environment=GENUS_LEARN_BATCH=$BATCH
ExecStart=/bin/bash $REPO_DIR/deploy/pi_learn.sh
StandardOutput=append:$LOG_DIR/learn.log
StandardError=append:$LOG_DIR/learn.log
EOF

cat > "$tmp_timer" <<EOF
[Unit]
Description=Run the GENUS vocabulary learner in idle time

[Timer]
OnBootSec=5min
OnUnitActiveSec=$INTERVAL
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo install -m 0644 "$tmp_service" "$SERVICE_PATH"
sudo install -m 0644 "$tmp_timer" "$TIMER_PATH"
sudo systemctl daemon-reload
sudo systemctl enable --now genus-learner.timer

echo "[LEARNER] installed genus-learner.timer (every $INTERVAL, batch $BATCH, idle priority)"
echo "[LEARNER] repo=$REPO_DIR  db=$DB_PATH  logs=$LOG_DIR/learn.log"
echo "[LEARNER] stop any time: genus pause   (or: sudo systemctl stop genus-learner.timer)"
systemctl list-timers --all genus-learner.timer
