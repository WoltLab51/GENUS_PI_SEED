#!/usr/bin/env bash
set -Eeuo pipefail

# Der volle Schmiede-Gang (Selbst-Codieren Stufe 2, Scheibe 2): der SCHMIED (Code-Modell,
# deploy/schmied.py) entwirft den Handler für ein Raster-Blatt, die Membran überreicht den
# Entwurf dem Kern (genus werkstatt entwerfe --code-datei, Herkunft werkstatt:schmied),
# danach fährt sofort die Probefahrt (Sandbox-pytest). Merge bleibt menschlich.
#
# Usage: deploy/werkstatt_schmiede.sh <blatt> [beschreibung...]

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <blatt> [beschreibung...]" >&2
    exit 2
fi
blatt="$1"; shift
beschreibung="$*"

tmp="$(mktemp --suffix=.py)"
trap 'rm -f "$tmp"' EXIT

echo "[SCHMIEDE] der Schmied entwirft „$blatt“ ..."
if ! "$REPO_DIR/.venv/bin/python" "$SCRIPT_DIR/schmied.py" "$blatt" $beschreibung > "$tmp"; then
    echo "[SCHMIEDE] kein Entwurf (Modell fehlt oder AST-Leitplanke nicht bestanden)" >&2
    exit 1
fi

GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" werkstatt entwerfe "$blatt" \
    --code-datei "$tmp" --quelle werkstatt:schmied

bash "$SCRIPT_DIR/werkstatt_probefahrt.sh" "$blatt"
