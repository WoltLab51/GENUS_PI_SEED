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
PY="$REPO_DIR/.venv/bin/python"
# alles, was die Quelle hergibt: aktuelle Werte + heutige Vorhersage (nur Zahlen queren, der
# Ort bleibt in dieser Membran). Die Temperatur bleibt der Anker (Beobachtungs-Pfad -> Trend);
# die uebrigen Felder kommen als eigene Claims ueber den allgemeinen Assertions-Eingang herein.
CURRENT="temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,precipitation"
DAILY="temperature_2m_max,temperature_2m_min,precipitation_probability_max"
URL="https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&current=${CURRENT}&daily=${DAILY}&timezone=auto&forecast_days=1"

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

# Fetch the raw JSON ONCE, then extract fields locally. Any failure (no network, bad
# payload, missing field) yields an empty string and records nothing.
roh="$(curl -s --max-time 15 "$URL" 2>/dev/null || true)"

# The temperature is the anchor: it alone gates recording (absence of a reading is not a
# reading), and it keeps the observation path (-> weather.trend belief).
temp="$(printf '%s' "$roh" | "$PY" -c 'import sys, json
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

# The rich fields — everything the source gives, each handed in as its OWN claim (number only,
# through the general assertion entry point). A missing field prints nothing and is silently
# left out; the core never sees a placeholder.
extra="$(printf '%s' "$roh" | "$PY" -c 'import sys, json
try:
    d = json.load(sys.stdin)
    cur = d.get("current", {}) or {}
    day = d.get("daily", {}) or {}
    first = lambda x: x[0] if isinstance(x, list) and x else None
    for claim, value in (
        ("weather.apparent", cur.get("apparent_temperature")),
        ("weather.humidity", cur.get("relative_humidity_2m")),
        ("weather.wind", cur.get("wind_speed_10m")),
        ("weather.code", cur.get("weather_code")),
        ("weather.temp_max", first(day.get("temperature_2m_max"))),
        ("weather.temp_min", first(day.get("temperature_2m_min"))),
        ("weather.rain_prob", first(day.get("precipitation_probability_max"))),
    ):
        if value is not None:
            print(claim, value)
except Exception:
    pass' 2>/dev/null || true)"

while read -r claim value; do
    [ -z "$claim" ] && continue
    run_genus observe-assertion --claim-key "$claim" --value "$value" --source "$SOURCE" >/dev/null
done <<< "$extra"
