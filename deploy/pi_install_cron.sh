#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$HOME/.genus/logs}"
PROFILE_DIR="${GENUS_PROFILE_DIR:-$(dirname "$DB_PATH")/betriebsprofil}"
STATUS_REPO_DIR="${GENUS_STATUS_REPO_DIR:-$HOME/GENUS_PI_STATUS}"
STATUS_REPO_URL="${GENUS_STATUS_REPO_URL:-git@github-genus-pi-status:WoltLab51/GENUS_PI_STATUS.git}"
CRON_BEGIN="# BEGIN GENUS_PI_SEED"
CRON_END="# END GENUS_PI_SEED"

mkdir -p "$(dirname "$DB_PATH")" "$LOG_DIR" "$PROFILE_DIR"
chmod 700 "$PROFILE_DIR"

# Status-publish is STICKY: enabling it once (GENUS_ENABLE_STATUS_PUBLISH=1) persists a
# marker on the Pi, so later reinstalls -- which may not carry the env flag -- keep the
# tick instead of silently dropping it. Delete the marker to disable.
STATUS_FLAG_FILE="${GENUS_STATUS_FLAG_FILE:-$(dirname "$DB_PATH")/status_publish.enabled}"
if [ "${GENUS_ENABLE_STATUS_PUBLISH:-0}" = "1" ]; then
    : > "$STATUS_FLAG_FILE"
fi
if [ -f "$STATUS_FLAG_FILE" ]; then STATUS_PUBLISH=1; else STATUS_PUBLISH=0; fi

# GENUS_CORE_ID ist EBENFALLS STICKY (Ronny 2026-07-08, Betriebsdrift-Fix): einmal gesetzt,
# persistiert der Wert in einer Marker-Datei; spätere Reinstalls ohne die Env-Variable lassen ihn
# NICHT mehr still fallen. Genau dieses Fallenlassen war die Ursache, warum Status-Publish nächtlich
# mit „GENUS_CORE_ID is required" scheiterte und der versiegelte Anker-Export übersprungen wurde.
CORE_ID_FILE="${GENUS_CORE_ID_FILE:-$(dirname "$DB_PATH")/core_id}"
if [ -n "${GENUS_CORE_ID:-}" ]; then
    printf '%s' "$GENUS_CORE_ID" > "$CORE_ID_FILE"
elif [ -f "$CORE_ID_FILE" ]; then
    GENUS_CORE_ID="$(cat "$CORE_ID_FILE")"
fi

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
    echo "GENUS_PROFILE_DIR=$PROFILE_DIR"
    echo "GENUS_STATUS_REPO_DIR=$STATUS_REPO_DIR"
    echo "GENUS_STATUS_REPO_URL=$STATUS_REPO_URL"
    echo "GENUS_WEATHER_LAT=${GENUS_WEATHER_LAT:-51.31}"
    echo "GENUS_WEATHER_LON=${GENUS_WEATHER_LON:-9.50}"
    if [ -n "${GENUS_CORE_ID:-}" ]; then
        echo "GENUS_CORE_ID=$GENUS_CORE_ID"
    fi
    echo '*/5 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] observe-all $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus observe-all >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '1-59/5 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] state-refresh $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus state refresh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '*/15 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] clock-check $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && ./deploy/pi_clock_check.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '7 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] weather $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && ./deploy/observe_weather.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '12 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] weather-2 $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && ./deploy/observe_weather_second.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '*/20 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] news $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && ./deploy/observe_news.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '*/3 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] gedanken-push $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus gedanken-push >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '*/2 * * * * cd "$GENUS_REPO_DIR" && ./deploy/hand_ausfuehren.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '7 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] ledger-backup $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && ./deploy/backup_ledger_to_sd.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '17 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] experience-scan $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus experience scan >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '57 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] nacht-konsolidierung $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && bash ./deploy/nacht_konsolidierung.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '*/10 5-9 * * * cd "$GENUS_REPO_DIR" && bash ./deploy/morgen_push.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    echo '6,21,36,51 * * * * cd "$GENUS_REPO_DIR" && bash ./deploy/besinnung.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    # H0.1 is deliberately started once by a human.  Before that, and after h72,
    # this hourly due check is completely silent and never opens the ledger.
    echo '23 * * * * cd "$GENUS_REPO_DIR" && /usr/bin/bash ./deploy/pi_betriebsprofil_capture.sh'
    echo '27 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] doctor $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/doctor.log" 2>&1 && .venv/bin/genus doctor >> "$GENUS_LOG_DIR/doctor.log" 2>&1'
    echo '47 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] repo-observe $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && ./deploy/observe_repo_on_pi.sh >> "$GENUS_LOG_DIR/cron.log" 2>&1'
    if [ "$STATUS_PUBLISH" = "1" ]; then
        echo '37 3 * * * cd "$GENUS_REPO_DIR" && echo "[TICK] status-publish $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/status.log" 2>&1 && ./deploy/pi_publish_status.sh >> "$GENUS_LOG_DIR/status.log" 2>&1'
    fi
    echo "$CRON_END"
} >> "$tmp_new"

crontab "$tmp_new"

echo "[CRON] installed GENUS cron block"
echo "[CRON] repo=$REPO_DIR"
echo "[CRON] db=$DB_PATH"
echo "[CRON] logs=$LOG_DIR"
echo "[CRON] profile=$PROFILE_DIR"
echo "[CRON] status_repo=$STATUS_REPO_DIR"
if [ -n "${GENUS_CORE_ID:-}" ]; then
    echo "[CRON] core_id=$GENUS_CORE_ID"
else
    echo "[CRON] GENUS_CORE_ID not set; doctor will warn until it is configured"
fi
if [ "$STATUS_PUBLISH" = "1" ]; then
    echo "[CRON] status publish enabled (sticky marker: $STATUS_FLAG_FILE)"
else
    echo "[CRON] status publish disabled (enable once with GENUS_ENABLE_STATUS_PUBLISH=1; it then sticks)"
fi
echo "[CRON] current GENUS block:"
crontab -l | awk -v begin="$CRON_BEGIN" -v end="$CRON_END" '
    $0 == begin { show = 1 }
    show == 1 { print }
    $0 == end { show = 0 }
'
