#!/usr/bin/env bash
set -Eeuo pipefail

# Seed den Ziel-Graphen (Ronnys sieben Ziele vom 2026-07-03, Inversion 4 des Audits) in den
# Live-Ledger -- ein sauberer, idempotenter Apply. Mission, Ziele, Fähigkeiten und ihre
# dient/braucht/status-Kanten werden gewöhnliche provenancte Relationen (Quelle "ronny",
# Mensch, voll vertraut). Re-running sät nur fehlende Kanten; nichts wird dupliziert.
# Der Graph wächst per Pull-Request (genus/ziele.py editieren, erneut anwenden), nicht
# per Pi-Mutation.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"

cd "$REPO_DIR"
"$REPO_DIR/.venv/bin/python" - "$DB_PATH" <<'PY'
import sys
from genus import startup, ziele

conn = startup.connect(sys.argv[1])
neu = ziele.seed_ziele(conn)
conn.commit()
alle = ziele.ziele(conn)
fehlt = ziele.fehlende_faehigkeiten(conn)
print(f"[SEED-ZIELE] {neu} neue Kante(n) gesät; Mission + {len(alle)} Ziele im Graphen.")
print(f"[SEED-ZIELE] ehrlich offen: {len(fehlt)} Fähigkeit(en) noch nicht live:")
for f in fehlt:
    print(f"  - {f['id']} ({f['status']})")
PY
