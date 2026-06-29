#!/usr/bin/env bash
set -Eeuo pipefail

# External-material membrane: outside temperature.
#
# This is the first sensor that reaches the internet. HTTP lives HERE, at the
# edge, never in the core (genus/ stays grep-empty of HTTP forever). The script
# fetches the current outside temperature from a public, no-auth source
# (open-meteo), extracts only the number, and hands it to GENUS. The location
# (latitude/longitude) lives only in this membrane's configuration and never
# enters the ledger. A failed fetch records nothing — absence of a reading is
# not a reading, so the belief simply ages.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

# Location lives ONLY here, never in the ledger. Default: Kassel.
LAT="${GENUS_WEATHER_LAT:-51.31}"
LON="${GENUS_WEATHER_LON:-9.50}"
SOURCE="open-meteo"
URL="https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&current=temperature_2m"

mkdir -p "$LOG_DIR"

log() {
    printf '[WTR] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# Honor the global pause switch (genus pause): freeze autonomous activity.
if [ -f "$(dirname "$DB_PATH")/paused" ]; then log "paused — skipping"; exit 0; fi

run_genus() {
    if [ "$(id -u)" -eq 0 ] && command -v runuser >/dev/null 2>&1; then
        runuser -u "$GENUS_USER" -- env \
            GENUS_DB_PATH="$DB_PATH" \
            GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    else
        env \
            GENUS_DB_PATH="$DB_PATH" \
            GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    fi
}

# Fetch the raw JSON and extract just the temperature. Any failure (no network,
# bad payload, missing field) yields an empty string and records nothing.
temp="$(curl -s --max-time 15 "$URL" 2>/dev/null \
    | "$REPO_DIR/.venv/bin/python" -c 'import sys, json
try:
    print(json.load(sys.stdin)["current"]["temperature_2m"])
except Exception:
    pass' 2>/dev/null || true)"

if [ -z "$temp" ]; then
    log "fetch failed or no temperature — no observation recorded"
    exit 0
fi

log "outside temperature=${temp}C (source=$SOURCE)"
run_genus observe-weather --temp-outside "$temp" --source "$SOURCE" >/dev/null
