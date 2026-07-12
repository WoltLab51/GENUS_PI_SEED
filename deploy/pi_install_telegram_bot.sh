#!/usr/bin/env bash
set -Eeuo pipefail

# Install the Telegram bridge as a long-lived systemd service. Unlike the background learner
# (deliberately idle-priority, defers to everything), this answers a human directly, so it runs
# at NORMAL priority -- it should feel responsive. The bot token is a credential and stays in its
# own 0600 file. The strictly numeric allow-list is also kept in a user file for user-level helper
# scripts, but PID 1 must never read that user-controlled file: only its validated value is embedded
# in the root-owned unit. Telegram user IDs are authorization selectors, not authentication secrets.
#
# Usage: deploy/pi_install_telegram_bot.sh [BOT_TOKEN] <ALLOWED_TELEGRAM_USER_ID> [MORE_IDS...]
#   The token is OPTIONAL here if you've already placed it yourself in the token file -- the most
#   private path: your secret goes straight from @BotFather onto this Pi, through no one else's
#   hands. Detected by shape: a Telegram token contains a ':' (12345:ABC...), a user id is digits.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
# sudo-fest wie pi_learn.sh/pi_clock_check.sh: unter sudo ist $HOME /root -- der Token,
# die Logs und der Dienst gehören aber RONNYS Nutzer (live gefunden, 2026-07-04: der
# Installer suchte /root/.genus/telegram_bot_token und verweigerte).
GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
if [ "$GENUS_USER" = "root" ] && [ "${GENUS_ALLOW_ROOT:-0}" != "1" ]; then
    echo "[TGBOT] refusing GENUS_USER=root; set GENUS_USER to the GENUS login (or explicitly GENUS_ALLOW_ROOT=1)" >&2
    exit 1
fi
PASSWD_ENTRY="$(getent passwd "$GENUS_USER" || true)"
if [ -z "$PASSWD_ENTRY" ]; then
    echo "[TGBOT] unknown GENUS_USER: $GENUS_USER" >&2
    exit 1
fi
DEFAULT_HOME="$(printf '%s\n' "$PASSWD_ENTRY" | cut -d: -f6)"
GENUS_HOME="${GENUS_HOME:-$DEFAULT_HOME}"
GENUS_GROUP="${GENUS_GROUP:-$(id -gn "$GENUS_USER")}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
TOKEN_FILE="$GENUS_HOME/.genus/telegram_bot_token"
ENV_FILE="$GENUS_HOME/.genus/telegram_bot.env"
LOCK_FILE="$GENUS_HOME/.genus/telegram_bot.lock"
SERVICE_PATH="/etc/systemd/system/genus-telegram-bot.service"

as_genus_user() {
    if [ "$(id -u)" -eq 0 ] && [ "$(id -un)" != "$GENUS_USER" ]; then
        runuser -u "$GENUS_USER" -- "$@"
    else
        "$@"
    fi
}

# A first argument that looks like a token (contains ':') is used; otherwise every argument is a
# user id and the token must already be in TOKEN_FILE (the private, pre-placed path).
BOT_TOKEN=""
if [ "$#" -ge 1 ]; then
    case "$1" in
        *:*) BOT_TOKEN="$1"; shift ;;
    esac
fi

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 [BOT_TOKEN] <ALLOWED_TELEGRAM_USER_ID> [MORE_IDS...]" >&2
    echo "  BOT_TOKEN is optional here if you placed it in $TOKEN_FILE yourself (chmod 600)." >&2
    echo "  ALLOWED_TELEGRAM_USER_ID: your numeric Telegram id (from @userinfobot)." >&2
    exit 1
fi
ALLOWED_IDS="$(IFS=,; echo "$*")"
if ! [[ "$ALLOWED_IDS" =~ ^[0-9]{1,20}(,[0-9]{1,20}){0,15}$ ]]; then
    echo "[TGBOT] allow-list must contain 1-16 comma-separated numeric user IDs" >&2
    exit 1
fi

DB_DIR="$(dirname "$DB_PATH")"
TOKEN_DIR="$(dirname "$TOKEN_FILE")"
if ! as_genus_user mkdir -p "$DB_DIR" "$TOKEN_DIR" "$LOG_DIR"; then
    echo "[TGBOT] cannot create state paths as $GENUS_USER" >&2
    exit 1
fi
if ! as_genus_user test -w "$DB_DIR" \
        || ! as_genus_user test -w "$TOKEN_DIR" \
        || ! as_genus_user test -w "$LOG_DIR" \
        || { [ -e "$DB_PATH" ] && ! as_genus_user test -w "$DB_PATH"; }; then
    echo "[TGBOT] state path is not usable by $GENUS_USER: $DB_PATH / $TOKEN_DIR / $LOG_DIR" >&2
    exit 1
fi
as_genus_user chmod 700 "$DB_DIR" "$TOKEN_DIR" "$LOG_DIR"

# The token lives in its own file, chmod 600, never in the world-readable unit file. Prefer a
# token you pre-placed (so it never passed through the installer's arguments at all); only write
# it here if you chose to pass it on the command line.
umask 077
if [ -n "$BOT_TOKEN" ]; then
    printf '%s' "$BOT_TOKEN" | as_genus_user tee "$TOKEN_FILE" >/dev/null
    as_genus_user chmod 600 "$TOKEN_FILE"
elif ! as_genus_user test -s "$TOKEN_FILE"; then
    echo "No token on the command line and $TOKEN_FILE is missing/empty." >&2
    echo "Place your token there first (chmod 600), or pass it as the first argument." >&2
    exit 1
fi
printf 'GENUS_TELEGRAM_ALLOWED_IDS=%s\n' "$ALLOWED_IDS" \
    | as_genus_user tee "$ENV_FILE" >/dev/null
as_genus_user chmod 600 "$TOKEN_FILE" "$ENV_FILE"

tmp_service="$(mktemp)"
trap 'rm -f "$tmp_service"' EXIT

cat > "$tmp_service" <<EOF
[Unit]
Description=GENUS Telegram bridge (controlled companion membrane)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=5min
StartLimitBurst=5

[Service]
Type=simple
User=$GENUS_USER
Group=$GENUS_GROUP
WorkingDirectory=$REPO_DIR
Restart=on-failure
RestartSec=15
Environment=HOME=$GENUS_HOME
Environment=GENUS_DB_PATH=$DB_PATH
Environment=GENUS_LOG_DIR=$LOG_DIR
Environment=GENUS_TELEGRAM_TOKEN_FILE=$TOKEN_FILE
Environment=GENUS_TELEGRAM_LOCK_FILE=$LOCK_FILE
Environment=GENUS_TELEGRAM_ALLOWED_IDS=$ALLOWED_IDS
# Die Stimme ist reine Stil-Glättung und würde ein zweites 1.5B-Modell dauerhaft laden.
# Die verifizierte Template-Antwort bleibt ohne sie vollständig; ein Opt-in braucht bewusst
# zusätzlich einen höheren MemoryMax-Override, statt den Pi versehentlich wieder zu verdrängen.
Environment=GENUS_TELEGRAM_STIMME=0
ExecStart=$REPO_DIR/.venv/bin/python $REPO_DIR/deploy/telegram_bot.py
StandardOutput=journal
StandardError=journal
SyslogIdentifier=genus-telegram-bot

# Ein Deuter-Modell passt komfortabel; ein versehentlich zweites Modell nicht. MemoryHigh
# drosselt zuerst, MemoryMax verhindert, dass die Begleiter-Membran den ganzen Pi verdrängt.
MemoryAccounting=true
MemoryHigh=2500M
MemoryMax=3G
MemorySwapMax=512M
OOMPolicy=stop
TasksMax=64
LimitNOFILE=256

# Der Bot braucht Netzwerk sowie Schreibzugriff auf ~/.genus, aber keinerlei Privilegien,
# Geräte-, Kernel-, cgroup- oder /usr-/etc-Schreibzugriffe.
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=full
ProtectControlGroups=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectClock=true
ProtectHostname=true
ProtectProc=invisible
ProcSubset=pid
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
SystemCallArchitectures=native
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$tmp_service" "$SERVICE_PATH"
sudo systemctl daemon-reload
sudo systemctl enable genus-telegram-bot.service
# enable --now lässt einen bereits laufenden Prozess nach einer Unit-Änderung unangetastet.
# Ein expliziter Restart aktiviert Lock, RAM-Grenzen und Sandbox sofort und beendet Alt-Poller.
sudo systemctl restart genus-telegram-bot.service

echo "[TGBOT] installed genus-telegram-bot.service — allowed id(s): $ALLOWED_IDS"
echo "[TGBOT] token file: $TOKEN_FILE (chmod 600, not in git)"
echo "[TGBOT] stop any time: sudo systemctl stop genus-telegram-bot.service"
systemctl --no-pager status genus-telegram-bot.service | head -5
