#!/usr/bin/env bash
set -Eeuo pipefail

# Install the Telegram bridge as a long-lived systemd service. Unlike the background learner
# (deliberately idle-priority, defers to everything), this answers a human directly, so it runs
# at NORMAL priority -- it should feel responsive. The bot token and allow-list are secrets: kept
# in files outside the repo with restrictive permissions (0600), never in the world-readable
# systemd unit file (0644) and never committed to git.
#
# Usage: deploy/pi_install_telegram_bot.sh <BOT_TOKEN> <ALLOWED_TELEGRAM_USER_ID> [MORE_IDS...]

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <BOT_TOKEN> <ALLOWED_TELEGRAM_USER_ID> [MORE_IDS...]" >&2
    echo "  BOT_TOKEN: from @BotFather on Telegram" >&2
    echo "  ALLOWED_TELEGRAM_USER_ID: your own numeric Telegram id (e.g. from @userinfobot)" >&2
    exit 1
fi

BOT_TOKEN="$1"; shift
ALLOWED_IDS="$(IFS=,; echo "$*")"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_USER="${GENUS_USER:-$(id -un)}"
GENUS_HOME="${GENUS_HOME:-$HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
TOKEN_FILE="$GENUS_HOME/.genus/telegram_bot_token"
ENV_FILE="$GENUS_HOME/.genus/telegram_bot.env"
SERVICE_PATH="/etc/systemd/system/genus-telegram-bot.service"

mkdir -p "$(dirname "$DB_PATH")" "$LOG_DIR"

# The token: its own file, chmod 600, never in the unit file or an env var visible to `systemctl
# show`. telegram_bot.py reads it from here automatically when GENUS_TELEGRAM_BOT_TOKEN isn't set.
umask 077
printf '%s' "$BOT_TOKEN" > "$TOKEN_FILE"
printf 'GENUS_TELEGRAM_ALLOWED_IDS=%s\n' "$ALLOWED_IDS" > "$ENV_FILE"
chmod 600 "$TOKEN_FILE" "$ENV_FILE"

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
