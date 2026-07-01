#!/usr/bin/env bash
set -Eeuo pipefail

# Install the Telegram bridge as a long-lived systemd service. Unlike the background learner
# (deliberately idle-priority, defers to everything), this answers a human directly, so it runs
# at NORMAL priority -- it should feel responsive. The bot token and allow-list are secrets: kept
# in files outside the repo with restrictive permissions (0600), never in the world-readable
# systemd unit file (0644) and never committed to git.
#
# Usage: deploy/pi_install_telegram_bot.sh [BOT_TOKEN] <ALLOWED_TELEGRAM_USER_ID> [MORE_IDS...]
#   The token is OPTIONAL here if you've already placed it yourself in the token file -- the most
#   private path: your secret goes straight from @BotFather onto this Pi, through no one else's
#   hands. Detected by shape: a Telegram token contains a ':' (12345:ABC...), a user id is digits.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_USER="${GENUS_USER:-$(id -un)}"
GENUS_HOME="${GENUS_HOME:-$HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
TOKEN_FILE="$GENUS_HOME/.genus/telegram_bot_token"
ENV_FILE="$GENUS_HOME/.genus/telegram_bot.env"
SERVICE_PATH="/etc/systemd/system/genus-telegram-bot.service"

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

mkdir -p "$(dirname "$DB_PATH")" "$LOG_DIR"

# The token lives in its own file, chmod 600, never in the world-readable unit file. Prefer a
# token you pre-placed (so it never passed through the installer's arguments at all); only write
# it here if you chose to pass it on the command line.
umask 077
if [ -n "$BOT_TOKEN" ]; then
    printf '%s' "$BOT_TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
elif [ ! -s "$TOKEN_FILE" ]; then
    echo "No token on the command line and $TOKEN_FILE is missing/empty." >&2
    echo "Place your token there first (chmod 600), or pass it as the first argument." >&2
    exit 1
fi
printf 'GENUS_TELEGRAM_ALLOWED_IDS=%s\n' "$ALLOWED_IDS" > "$ENV_FILE"
chmod 600 "$ENV_FILE"

tmp_service="$(mktemp)"
trap 'rm -f "$tmp_service"' EXIT

cat > "$tmp_service" <<EOF
[Unit]
Description=GENUS Telegram bridge (answer-only companion, no write access)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Restart=always
RestartSec=10
EnvironmentFile=-$ENV_FILE
Environment=GENUS_DB_PATH=$DB_PATH
Environment=GENUS_LOG_DIR=$LOG_DIR
Environment=GENUS_TELEGRAM_TOKEN_FILE=$TOKEN_FILE
ExecStart=$REPO_DIR/.venv/bin/python $REPO_DIR/deploy/telegram_bot.py
StandardOutput=append:$LOG_DIR/telegram_bot.log
StandardError=append:$LOG_DIR/telegram_bot.log

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$tmp_service" "$SERVICE_PATH"
sudo systemctl daemon-reload
sudo systemctl enable --now genus-telegram-bot.service

echo "[TGBOT] installed genus-telegram-bot.service — allowed id(s): $ALLOWED_IDS"
echo "[TGBOT] token file: $TOKEN_FILE (chmod 600, not in git)"
echo "[TGBOT] stop any time: sudo systemctl stop genus-telegram-bot.service"
systemctl --no-pager status genus-telegram-bot.service | head -5
