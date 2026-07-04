#!/usr/bin/env bash
set -Eeuo pipefail

# Sät GENUS' Grundton (persoenlichkeit.ART_SEED: neugierig + warm) als Wissen in den
# lebenden Graphen -- art:<nutzer> -merkmal-> wert, Quelle der Nutzer selbst.
# NUR fehlende Merkmale werden gesät: eine per Chat gestellte Einstellung („sei knapper")
# überlebt jedes Re-Deploy. Idempotent: der zweite Lauf tut nichts.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"

GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/python" - << 'EOF'
import os

from genus import db, persoenlichkeit

conn = db.connect(os.environ["GENUS_DB_PATH"])
gesaet = persoenlichkeit.saet_art(conn)
werte = persoenlichkeit.art(conn)
print(f"[PERSOENLICHKEIT] {gesaet} Merkmal(e) neu gesät; Grundton jetzt: "
      + ", ".join(f"{m}={w}" for m, w in werte.items()))
conn.close()
EOF
