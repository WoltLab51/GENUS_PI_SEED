#!/usr/bin/env bash
set -Eeuo pipefail

# Einmalige, idempotente Migration (Punkt 1 von docs/design/MEMORY.md, 2026-07-03): die
# alten flachen Notizen (genus:notizen -notiz-> "<Text>") werden zu echten, vernetzten Episoden
# (genus.erinnerung) und danach zurückgenommen -- kein Duplikat, kein stiller Doppel-Stand.
# Re-running findet beim zweiten Mal keine genus:notizen-Kanten mehr und tut nichts.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"

cd "$REPO_DIR"
"$REPO_DIR/.venv/bin/python" - "$DB_PATH" <<'PY'
import sys
from genus import db, erinnerung

conn = db.connect(sys.argv[1])
migriert = erinnerung.migriere_notizen(conn)
conn.commit()
print(f"[MIGRIERE-NOTIZEN] {migriert} alte Notiz(en) zu Episoden überführt.")
print(f"  bestätigt: {len(erinnerung.bestaetigte_episoden(conn))}, "
      f"vermutet: {len(erinnerung.vermutete_episoden(conn))}")
PY
