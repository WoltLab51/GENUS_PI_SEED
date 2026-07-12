#!/usr/bin/env bash
set -Eeuo pipefail

# Install the background vocabulary learner as a LONG-LIVED, lowest-priority systemd service.
# It runs continuously (word after word) under idle CPU and IO scheduling, so the kernel only
# lets it run in true idle time and it yields instantly to the punctual sensor ticks -- the
# "clever job timing" is the OS scheduler itself. Restart=always keeps it alive across reboots
# and hiccups. Stop it any time with `genus pause` (the daemon honors it) or `systemctl stop`.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
# sudo-safe: a whole-script `sudo` changes id/$HOME to root.  The learner must nevertheless
# remain attached to the invoking GENUS login and its one productive ledger.  Explicit
# GENUS_USER/GENUS_HOME still win for deliberate non-default installations.
GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
# A direct root shell has no trustworthy invoking login to fall back to. Refuse to
# silently attach the learner to /root; deliberate root installs need a visible opt-in.
if [ "$GENUS_USER" = "root" ] && [ "${GENUS_ALLOW_ROOT:-0}" != "1" ]; then
    echo "[LEARNER] refusing GENUS_USER=root; set GENUS_USER to the GENUS login (or explicitly GENUS_ALLOW_ROOT=1)" >&2
    exit 1
fi
PASSWD_ENTRY="$(getent passwd "$GENUS_USER" || true)"
if [ -z "$PASSWD_ENTRY" ]; then
    echo "[LEARNER] unknown GENUS_USER: $GENUS_USER" >&2
    exit 1
fi
DEFAULT_HOME="$(printf '%s\n' "$PASSWD_ENTRY" | cut -d: -f6)"
GENUS_HOME="${GENUS_HOME:-$DEFAULT_HOME}"
GENUS_GROUP="${GENUS_GROUP:-$(id -gn "$GENUS_USER")}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
DELAY="${GENUS_LEARN_DELAY:-2}"
CHAT_WORD_LEARNING="${GENUS_CHAT_WORD_LEARNING:-0}"
SERVICE_PATH="/etc/systemd/system/genus-learner.service"
if [ "$CHAT_WORD_LEARNING" != "0" ] && [ "$CHAT_WORD_LEARNING" != "1" ]; then
    echo "[LEARNER] GENUS_CHAT_WORD_LEARNING must be 0 or 1" >&2
    exit 1
fi
CORE_ID="${GENUS_CORE_ID:-}"
case "$CORE_ID" in
    ''|*[!A-Za-z0-9._:-]*)
        if [ -n "$CORE_ID" ]; then
            echo "[LEARNER] invalid GENUS_CORE_ID (allowed: A-Z a-z 0-9 . _ : -, max 128)" >&2
            exit 1
        fi
        ;;
esac
if [ "${#CORE_ID}" -gt 128 ]; then
    echo "[LEARNER] invalid GENUS_CORE_ID (maximum 128 characters)" >&2
    exit 1
fi

# If the installer itself runs as root, create user-state directories AS the GENUS user.  This
# avoids fixing the unit only to leave behind root-owned paths that the corrected service cannot
# write.  A custom path that is not writable by that user fails here, before installing a unit.
as_genus_user() {
    if [ "$(id -u)" -eq 0 ] && [ "$(id -un)" != "$GENUS_USER" ]; then
        runuser -u "$GENUS_USER" -- "$@"
    else
        "$@"
    fi
}
DB_DIR="$(dirname "$DB_PATH")"
if ! as_genus_user mkdir -p "$DB_DIR" "$LOG_DIR" \
        || ! as_genus_user test -w "$DB_DIR" \
        || ! as_genus_user test -w "$LOG_DIR" \
        || { [ -e "$DB_PATH" ] && ! as_genus_user test -w "$DB_PATH"; }; then
    echo "[LEARNER] state path is not writable by $GENUS_USER: $DB_PATH / $LOG_DIR" >&2
    exit 1
fi

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
User=$GENUS_USER
Group=$GENUS_GROUP
WorkingDirectory=$REPO_DIR
Nice=19
CPUSchedulingPolicy=idle
IOSchedulingClass=idle
Restart=always
RestartSec=30
Environment=HOME=$GENUS_HOME
Environment=GENUS_USER=$GENUS_USER
Environment=GENUS_HOME=$GENUS_HOME
Environment=GENUS_REPO_DIR=$REPO_DIR
Environment=GENUS_DB_PATH=$DB_PATH
Environment=GENUS_LOG_DIR=$LOG_DIR
Environment=GENUS_CORE_ID=$CORE_ID
Environment=GENUS_LEARN_DELAY=$DELAY
Environment=GENUS_CHAT_WORD_LEARNING=$CHAT_WORD_LEARNING
ExecStart=/bin/bash $REPO_DIR/deploy/pi_learn.sh
StandardOutput=journal
StandardError=journal
SyslogIdentifier=genus-learner

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$tmp_service" "$SERVICE_PATH"
sudo systemctl daemon-reload
sudo systemctl enable genus-learner.service
# `enable --now` does not replace an already-running process after User=/path changes.  Restart
# explicitly so reinstalling this hardened unit immediately evicts a legacy root learner.
sudo systemctl restart genus-learner.service

echo "[LEARNER] installed genus-learner.service (continuous, ${DELAY}s/word, idle priority)"
echo "[LEARNER] user=$GENUS_USER  home=$GENUS_HOME"
echo "[LEARNER] repo=$REPO_DIR  db=$DB_PATH  logs=journalctl -u genus-learner.service"
echo "[LEARNER] stop any time: genus pause   (or: sudo systemctl stop genus-learner.service)"
systemctl --no-pager status genus-learner.service | head -5
