#!/usr/bin/env bash
set -Eeuo pipefail

# Die NACHT-KONSOLIDIERUNG (docs/design/MEMORY.md, Punkt ④): liest den Tagespuffer
# EINMAL, destilliert Struktur (Themen als gedeckelte Episoden, Quelle model:nacht;
# Warum-Folgen-Kennzahl), legt den Morgen-Bericht für die 06:00-Nachricht ab -- und
# VERGISST den Rest (der Puffer wird geleert; Rohtext hat den Ledger nie berührt).

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

from genus import db, konsolidierung

puffer = os.environ["GENUS_TAGESPUFFER"]
zuege = []
try:
    with open(puffer, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile:
                try:
                    zuege.append(json.loads(zeile))
                except ValueError:
                    pass
except FileNotFoundError:
    pass

conn = db.connect(os.environ["GENUS_DB_PATH"])
bericht = konsolidierung.konsolidiere(conn, zuege)
conn.close()

with open(os.environ["GENUS_MORGEN_BERICHT"], "w", encoding="utf-8") as f:
    json.dump(bericht, f, ensure_ascii=False)
print(f"[NACHT] {bericht['zuege']} Züge konsolidiert, {len(bericht['themen'])} Thema/Themen, "
      f"{len(bericht['episoden'])} Episode(n) still gemerkt")
EOF

# Vergessen ist Funktion: der Puffer verfällt nach der einen Lesung.
: > "$PUFFER"
log "Tagespuffer geleert"
