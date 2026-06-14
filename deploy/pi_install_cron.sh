#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$HOME/.genus/logs}"
STATUS_REPO_DIR="${GENUS_STATUS_REPO_DIR:-$HOME/GENUS_PI_STATUS}"
STATUS_REPO_URL="${GENUS_STATUS_REPO_URL:-git@github-genus-pi-status:WoltLab51/GENUS_PI_STATUS.git}"
CRON_BEGIN="# BEGIN GENUS_PI_SEED"
CRON_END="# END GENUS_PI_SEED"

mkdir -p "$(dirname "$DB_PATH")" "$LOG_DIR"

tmp_existing="$(mktemp)"
tmp_new="$(mktemp)"
cleanup() {
    rm -f "$tmp_existing" "$tmp_new"
}
trap cleanup EXIT

(crontab -l 2>/dev/null || true) | awk -v begin="$CRON_BEGIN" -v end="$CRON_END" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    skip != 1 { print }
' > "$tmp_existing"

cat "$tmp_existing" > "$tmp_new"
if [ -s "$tmp_new" ] && [ "$(tail -c 1 "$tmp_new")" != "" ]; then
    printf '\n' >> "$tmp_new"
fi

{
    echo "$CRON_BEGIN"
    echo "GENUS_REPO_DIR=$REPO_DIR"
    echo "GENUS_DB_PATH=$DB_PATH"
    echo "GENUS_LOG_DIR=$LOG_DIR"
    echo "GENUS_STATUS_REPO_DIR=$STATUS_REPO_DIR"
    echo "GENUS_STATUS_REPO_URL=$STATUS_REPO_URL"
    if [ -n "${GENUS_CORE_ID:-}" ]; then
        echo "GENUS_CORE_ID=$GENUS_CORE_ID"
    fi
    echo '*/5 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] observe-all $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus observe-all >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '1-59/5 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] state-refresh $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus state refresh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '17 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] experience-scan $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus experience scan >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '27 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] doctor $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/doctor.log" 2>&1 && .venv/bin/genus doctor >> "$GENUS_LOG_DIR/doctor.log" 2>&1'
    if [ "${GENUS_ENABLE_STATUS_PUBLISH:-0}" = "1" ]; then
        echo '37 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] status-publish $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/status.log" 2>&1 && ./deploy/pi_publish_status.sh >> "$GENUS_LOG_DIR/status.log" 2>&1'
    fi
    echo "$CRON_END"
} >> "$tmp_new"

crontab "$tmp_new"

echo "[CRON] installed GENUS cron block"
echo "[CRON] repo=$REPO_DIR"
echo "[CRON] db=$DB_PATH"
echo "[CRON] logs=$LOG_DIR"
echo "[CRON] status_repo=$STATUS_REPO_DIR"
if [ -n "${GENUS_CORE_ID:-}" ]; then
    echo "[CRON] core_id=$GENUS_CORE_ID"
else
    echo "[CRON] GENUS_CORE_ID not set; doctor will warn until it is configured"
fi
if [ "${GENUS_ENABLE_STATUS_PUBLISH:-0}" = "1" ]; then
    echo "[CRON] status publish enabled"
else
    echo "[CRON] status publish disabled (set GENUS_ENABLE_STATUS_PUBLISH=1)"
fi
echo "[CRON] current GENUS block:"
crontab -l | awk -v begin="$CRON_BEGIN" -v end="$CRON_END" '
    $0 == begin { show = 1 }
    show == 1 { print }
    $0 == end { show = 0 }
'
