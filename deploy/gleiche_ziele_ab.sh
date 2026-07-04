#!/usr/bin/env bash
set -Eeuo pipefail

# Der Selbst-Bild-Abgleich (ziele.gleiche_seed_ab): zieht den lebenden Ziel-Graphen auf
# den ehrlichen Stand der Saat nach -- veraltete inhalt/status-Kanten der Seed-Quelle
# werden zurückgenommen (relation_retracted, ehrliche Historie), die aktuellen gesät.
# Idempotent: ein sauberer Apply, ein zweiter Lauf tut nichts. Danach läuft seed_ziele
# für additive Kanten (dient/braucht) gleich mit.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"

GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/python" - << 'EOF'
import os

from genus import db, ziele

conn = db.connect(os.environ["GENUS_DB_PATH"])
abgleich = ziele.gleiche_seed_ab(conn)
neu = ziele.seed_ziele(conn)
print(f"[ZIELE-ABGLEICH] {abgleich['zurueckgenommen']} veraltete Kante(n) zurückgenommen, "
      f"{abgleich['gesaet']} aktualisiert, {neu} additive Kante(n) neu gesät")
fehlend = ziele.fehlende_faehigkeiten(conn)
print(f"[ZIELE-ABGLEICH] offene Fähigkeiten jetzt: "
      + (", ".join(f["id"] + " (" + f["status"] + ")" for f in fehlend) or "keine"))
conn.close()
EOF
