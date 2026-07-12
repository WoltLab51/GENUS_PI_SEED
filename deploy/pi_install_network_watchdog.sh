#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
# Resolve the productive login even if the whole installer is invoked through sudo.
# A direct root shell must name the intended login so it cannot persist /root as truth.
GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
if [ "$GENUS_USER" = "root" ] && [ "${GENUS_ALLOW_ROOT:-0}" != "1" ]; then
    echo "[WATCHDOG] refusing GENUS_USER=root; set GENUS_USER to the GENUS login (or explicitly GENUS_ALLOW_ROOT=1)" >&2
    exit 1
fi
PASSWD_ENTRY="$(getent passwd "$GENUS_USER" || true)"
if [ -z "$PASSWD_ENTRY" ]; then
    echo "[WATCHDOG] unknown GENUS_USER: $GENUS_USER" >&2
    exit 1
fi
DEFAULT_HOME="$(printf '%s\n' "$PASSWD_ENTRY" | cut -d: -f6)"
GENUS_HOME="${GENUS_HOME:-$DEFAULT_HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
SERVICE_PATH="/etc/systemd/system/genus-network-watchdog.service"
TIMER_PATH="/etc/systemd/system/genus-network-watchdog.timer"
PRIVILEGED_DIR="/usr/local/libexec/genus"
STATE_DIR="/var/lib/genus-network-watchdog"
CORE_ID="${GENUS_CORE_ID:-}"
case "$CORE_ID" in
    ''|*[!A-Za-z0-9._:-]*)
        if [ -n "$CORE_ID" ]; then
            echo "[WATCHDOG] invalid GENUS_CORE_ID (allowed: A-Z a-z 0-9 . _ : -, max 128)" >&2
            exit 1
        fi
        ;;
esac
if [ "${#CORE_ID}" -gt 128 ]; then
    echo "[WATCHDOG] invalid GENUS_CORE_ID (maximum 128 characters)" >&2
    exit 1
fi

as_genus_user() {
    if [ "$(id -u)" -eq 0 ] && [ "$(id -un)" != "$GENUS_USER" ]; then
        runuser -u "$GENUS_USER" -- "$@"
    else
        "$@"
    fi
}

DB_DIR="$(dirname "$DB_PATH")"
if ! as_genus_user mkdir -p "$DB_DIR" "$LOG_DIR"; then
    echo "[WATCHDOG] cannot create state paths as $GENUS_USER" >&2
    exit 1
fi
if ! as_genus_user test -w "$DB_DIR" \
        || ! as_genus_user test -w "$LOG_DIR" \
        || { [ -e "$DB_PATH" ] && ! as_genus_user test -w "$DB_PATH"; }; then
    echo "[WATCHDOG] state path is not writable by $GENUS_USER: $DB_PATH / $LOG_DIR" >&2
    exit 1
fi

# The watchdog runs as root to restart networking/reboot. Never execute that
# privilege boundary from the login user's writable checkout. The two repair
# installers are copied for the same reason: the watchdog may invoke them as root.
sudo install -d -o root -g root -m 0755 "$PRIVILEGED_DIR"
for helper in pi_network_watchdog.sh pi_install_network_watchdog.sh \
              pi_install_learner.sh pi_install_telegram_bot.sh; do
    source_path="$SCRIPT_DIR/$helper"
    target_path="$PRIVILEGED_DIR/$helper"
    if [ "$(readlink -f "$source_path")" != "$(readlink -f "$target_path" 2>/dev/null || true)" ]; then
        sudo install -o root -g root -m 0755 "$source_path" "$target_path"
    fi
done

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
TimeoutStartSec=3min
User=root
Group=root
Environment=GENUS_USER=$GENUS_USER
Environment=GENUS_HOME=$GENUS_HOME
Environment=GENUS_REPO_DIR=$REPO_DIR
Environment=GENUS_DB_PATH=$DB_PATH
Environment=GENUS_LOG_DIR=$LOG_DIR
Environment=GENUS_CORE_ID=$CORE_ID
Environment=GENUS_PRIVILEGED_HELPER_DIR=$PRIVILEGED_DIR
ExecStart=$PRIVILEGED_DIR/pi_network_watchdog.sh
StateDirectory=genus-network-watchdog
StateDirectoryMode=0700
UMask=0077
PrivateTmp=true
SyslogIdentifier=genus-network-watchdog
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
echo "[WATCHDOG] logs=journalctl -u genus-network-watchdog.service"
systemctl list-timers --all genus-network-watchdog.timer
