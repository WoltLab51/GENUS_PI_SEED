#!/usr/bin/env bash
set -Eeuo pipefail

# Seed the Absichts-Raster (der Verstehens-Würfel als Wissen) into the live ledger — one
# clean, idempotent apply. The raster (genus.verstehen.RASTER_SEED, Ronnys Tabelle vom
# 2026-07-03) becomes ordinary is_a relations under absicht:*, Quelle "ronny" (Mensch, voll
# vertraut). Re-running sows only edges that are missing; nothing is duplicated. The raster
# grows by pull request (edit RASTER_SEED, re-run), not by Pi mutation.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"

cd "$REPO_DIR"
"$REPO_DIR/.venv/bin/python" - "$DB_PATH" <<'PY'
import sys
from genus import db, verstehen

conn = db.connect(sys.argv[1])
sown = verstehen.seed_raster(conn)
conn.commit()
kinds = sorted(verstehen.kinds(conn))
print(f"[SEED-VERSTEHEN] {sown} neue Kante(n) gesät; Raster kennt {len(kinds)} Ausprägungen:")
print("  " + ", ".join(kinds))
PY
