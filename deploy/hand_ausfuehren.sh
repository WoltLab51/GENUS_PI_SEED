#!/usr/bin/env bash
set -Eeuo pipefail

# Die erste HAND ausführen (P4): fällige, FREIGEGEBENE Hände (genus/hand.py) senden.
#
# Der Kern hält das Gate und sendet NIE selbst (HTTP-frei). Diese Membran führt aus: sie
# BEANSPRUCHT jede fällige Hand atomar (markiere_ausgefuehrt = genau einmal) und sendet ERST
# DANN über Telegram. Claim-vor-Senden heißt: zwei überlappende Cron-Ticks senden nie doppelt
# (nur der Gewinner des Anspruchs sendet); ein Absturz zwischen Anspruch und Senden verliert
# höchstens EINE Erinnerung — nie eine doppelte (bei einer Erinnerung die sichere Richtung).

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
TOKEN_FILE="${GENUS_TELEGRAM_TOKEN_FILE:-$GENUS_HOME/.genus/telegram_bot_token}"
ENV_FILE="$GENUS_HOME/.genus/telegram_bot.env"

mkdir -p "$LOG_DIR"
log() { printf '[HAND] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Honor the global pause switch (genus pause): freeze autonomous activity.
if [ -f "$(dirname "$DB_PATH")/paused" ]; then log "paused — skipping"; exit 0; fi

token="$(cat "$TOKEN_FILE" 2>/dev/null || true)"
chat_id="$(grep -o 'GENUS_TELEGRAM_ALLOWED_IDS=[0-9]*' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || true)"
if [ -z "$token" ] || [ -z "$chat_id" ]; then log "kein Token/Empfänger — nichts zu senden"; exit 0; fi

GENUS_DB_PATH="$DB_PATH" HAND_TOKEN="$token" HAND_CHAT="$chat_id" \
    "$REPO_DIR/.venv/bin/python" - << 'EOF'
import os
import urllib.parse
import urllib.request
from datetime import datetime

from genus import hand, startup

conn = startup.connect(os.environ["GENUS_DB_PATH"])
jetzt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
token = os.environ["HAND_TOKEN"]
chat_id = os.environ["HAND_CHAT"]

for h in hand.faellige(conn, jetzt):
    # ATOMAR beanspruchen (genau einmal) -- nur wer den Anspruch gewinnt, sendet
    if not hand.markiere_ausgefuehrt(conn, h["hand_id"]).get("ausgefuehrt"):
        continue
    daten = urllib.parse.urlencode({"chat_id": chat_id, "text": h["inhalt"]}).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        urllib.request.urlopen(url, data=daten, timeout=15).read()
        print(f"[HAND] gesendet: Hand {h['hand_id']}")
    except Exception as exc:  # der Anspruch steht schon; ein Fehler hier = verloren, nie doppelt
        print(f"[HAND] Senden fehlgeschlagen fuer Hand {h['hand_id']}: {exc}")

conn.close()
EOF
