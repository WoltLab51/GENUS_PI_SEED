#!/usr/bin/env bash
set -Eeuo pipefail

# Seed die kuratierte Geo-Grundierung (genus/orte.py) in den Live-Ledger -- ein sauberer,
# idempotenter Apply. Deutsche Verwaltungsgeografie (16 Bundesländer + größere Städte, jede
# located_in ihr Land, jedes Land located_in Deutschland) als gewöhnliche provenancte
# Relationen (Quelle "kuratiert", Q-IDs gegen Wikidata geprüft). Damit wird "Ist Kassel in
# Hessen?" beantwortbar (Absicht "ort", Scheibe ②). Re-running sät nur Fehlendes; nichts wird
# dupliziert. Der Graph wächst per Pull-Request (genus/orte.py editieren, erneut anwenden),
# nicht per Pi-Mutation.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"

cd "$REPO_DIR"
"$REPO_DIR/.venv/bin/python" - "$DB_PATH" <<'PY'
import sys
from genus import db, inference, orte

conn = db.connect(sys.argv[1])
neu = orte.seed_orte(conn)
conn.commit()
laender = len(orte.BUNDESLAENDER)
staedte = len(orte.STAEDTE)
print(f"[SEED-ORTE] {neu} neue Kante(n) gesät; {laender} Bundesländer + {staedte} Städte, located_in Deutschland.")
# ehrliche Selbstprobe: die Kette muss transitiv auflösen, sonst ist der Seed wirkungslos
ahnen = {a["object"] for a in inference.infer_lexeme(conn, "Kassel", orte.LOCATED_IN, "de")}
hessen = "Q1199" in ahnen
land = orte.DEUTSCHLAND in ahnen
status = "OK" if (hessen and land) else "FEHLER"
print(f"[SEED-ORTE] Selbstprobe Kassel located_in: Hessen={hessen} Deutschland={land} -> {status}")
PY
