#!/usr/bin/env bash
set -Eeuo pipefail

# Die NACHT-KONSOLIDIERUNG (docs/design/MEMORY.md, „Tagesrhythmus“): liest den Tagespuffer
# EINMAL, verdichtet die bereits rohtextfreie Struktur (Themen + Warum-Folgen-Kennzahl)
# und legt den Morgen-Bericht für die 06:00-Nachricht ab. Die Rotation ist mit dem Bot-
# Schreiber verriegelt und atomar: ein gleichzeitig ankommender Zug landet sicher im neuen
# Puffer. Häufigkeit erzeugt keine dauerhafte persönliche Episode.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
PUFFER="${GENUS_TAGESPUFFER:-$GENUS_HOME/.genus/chat_tag.jsonl}"
BERICHT="${GENUS_MORGEN_BERICHT:-$GENUS_HOME/.genus/morgen.bericht}"

log() { printf '[NACHT] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Honor the global pause switch (genus pause): freeze autonomous activity.
if [ -f "$(dirname "$DB_PATH")/paused" ]; then log "paused — skipping"; exit 0; fi

GENUS_DB_PATH="$DB_PATH" GENUS_TAGESPUFFER="$PUFFER" GENUS_MORGEN_BERICHT="$BERICHT" \
    "$REPO_DIR/.venv/bin/python" - << 'EOF'
import json
import os
import fcntl
import sys

from genus import konsolidierung, startup

puffer = os.environ["GENUS_TAGESPUFFER"]
verarbeitung = puffer + ".nacht"
lock_path = puffer + ".lock"
os.makedirs(os.path.dirname(puffer) or ".", exist_ok=True)

# Ein eigener Lauf-Lock bleibt bis nach Report + Cleanup offen. Ein zweiter Cron-/Handlauf
# verarbeitet damit nie dieselbe .nacht-Datei parallel und kann keinen richtigen Bericht
# nachträglich durch einen leeren ersetzen.
run_lock = open(puffer + ".nacht.lock", "a", encoding="ascii")
os.chmod(puffer + ".nacht.lock", 0o600)
try:
    fcntl.flock(run_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("[NACHT] another consolidation run is active — skipping")
    sys.exit(0)

# Erst unter demselben Lock wie der Telegram-Schreiber rotieren, dann außerhalb des Locks
# verarbeiten. Bleibt nach einem Absturz eine .nacht-Datei liegen, wird genau sie erneut
# verarbeitet; der inzwischen neue Puffer wartet verlustfrei auf den nächsten Lauf.
with open(lock_path, "a", encoding="ascii") as lock:
    os.chmod(lock_path, 0o600)
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    if not os.path.exists(verarbeitung):
        try:
            os.replace(puffer, verarbeitung)
        except FileNotFoundError:
            pass
    with open(puffer, "a", encoding="utf-8"):
        pass
    os.chmod(puffer, 0o600)

zuege = []
try:
    with open(verarbeitung, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile:
                try:
                    zuege.append(json.loads(zeile))
                except ValueError:
                    pass
except FileNotFoundError:
    pass

conn = startup.connect(os.environ["GENUS_DB_PATH"])
bericht = konsolidierung.konsolidiere(conn, zuege)
conn.close()

bericht_path = os.environ["GENUS_MORGEN_BERICHT"]
tmp_path = bericht_path + f".tmp-{os.getpid()}"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(bericht, f, ensure_ascii=False)
os.chmod(tmp_path, 0o600)
os.replace(tmp_path, bericht_path)
try:
    os.remove(verarbeitung)
except FileNotFoundError:
    pass
print(f"[NACHT] {bericht['zuege']} Züge konsolidiert, {len(bericht['themen'])} Thema/Themen, "
      "keine Häufigkeit als persönliche Episode gespeichert")
EOF

log "Nachtlauf beendet"
