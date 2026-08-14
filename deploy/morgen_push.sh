#!/usr/bin/env bash
set -Eeuo pipefail

# Der MORGEN-PUSH (Ronnys Entscheidungen 2026-07-04): genau EINE Nachricht am Morgen,
# 06:00 (änderbar über ~/.genus/morgenpush.zeit -- per Chat: „stell den Push auf 7",
# telegram_bot._morgenzeit_antwort schreibt genau diese Datei), nie leer (wenn nichts
# wartet, erzählt GENUS, was es nachts gelernt hat), warm und nativ formuliert
# (genus/konsolidierung.morgen_nachricht, deterministisch).
# Läuft alle 10 Minuten im Morgenfenster (Cron) und feuert genau einmal pro Tag
# (Datums-Marker) -- der erste bewusste PUSH der sonst rein reaktiven Membran.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
BERICHT="${GENUS_MORGEN_BERICHT:-$GENUS_HOME/.genus/morgen.bericht}"
ZEIT_DATEI="$GENUS_HOME/.genus/morgenpush.zeit"
MARKER="$GENUS_HOME/.genus/morgenpush.gesendet"
TOKEN_FILE="${GENUS_TELEGRAM_TOKEN_FILE:-$GENUS_HOME/.genus/telegram_bot_token}"
ENV_FILE="$GENUS_HOME/.genus/telegram_bot.env"

log() { printf '[MORGEN] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Honor the global pause switch (genus pause): freeze autonomous activity.
if [ -f "$(dirname "$DB_PATH")/paused" ]; then log "paused — skipping"; exit 0; fi

zeit="$(cat "$ZEIT_DATEI" 2>/dev/null || echo 06:00)"
jetzt="$(date +%H:%M)"
heute="$(date +%Y-%m-%d)"

if [ "$jetzt" \< "$zeit" ]; then exit 0; fi
if [ "$(cat "$MARKER" 2>/dev/null || true)" = "$heute" ]; then exit 0; fi

token="$(cat "$TOKEN_FILE" 2>/dev/null || true)"
if [ -z "$token" ]; then log "kein Bot-Token — kein Push"; exit 0; fi
chat_id="$(grep -o 'GENUS_TELEGRAM_ALLOWED_IDS=[0-9]*' "$ENV_FILE" 2>/dev/null | cut -d= -f2)"
if [ -z "$chat_id" ]; then log "keine Empfänger-Id — kein Push"; exit 0; fi

nachricht="$(GENUS_DB_PATH="$DB_PATH" GENUS_MORGEN_BERICHT="$BERICHT" \
    "$REPO_DIR/.venv/bin/python" - << 'EOF'
import json
import os

from genus import konsolidierung, startup

bericht = None
try:
    with open(os.environ["GENUS_MORGEN_BERICHT"], encoding="utf-8") as f:
        bericht = json.load(f)
except (FileNotFoundError, ValueError):
    pass

conn = startup.connect(os.environ["GENUS_DB_PATH"])
print(konsolidierung.morgen_nachricht(conn, bericht))
conn.close()
EOF
)"

antwort="$(curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${chat_id}" \
    --data-urlencode "text=${nachricht}")"
if printf '%s' "$antwort" | grep -q '"ok":true'; then
    printf '%s' "$heute" > "$MARKER"
    log "Morgen-Nachricht gesendet (genau eine, Marker gesetzt)"
else
    log "Senden fehlgeschlagen: $antwort"
    exit 1
fi
