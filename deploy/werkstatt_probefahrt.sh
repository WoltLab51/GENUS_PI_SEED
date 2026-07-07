#!/usr/bin/env bash
set -Eeuo pipefail

# Die PROBEFAHRT eines Werkstatt-Entwurfs (Selbst-Codieren Stufe 2, Scheibe 1): die
# Sandbox-Tests des Entwurfs laufen HIER in der Membran als eigener pytest-Subprozess --
# nie im lebenden Kern-Prozess (der Membran-Reinheits-Test verbietet subprocess im Kern,
# und genau so ist es richtig: die Membran fährt, der Kern protokolliert das überreichte
# Ergebnis -- dasselbe Muster wie beim Uhr-Check). Der Merge bleibt danach menschlich.
#
# Usage: deploy/werkstatt_probefahrt.sh <blatt>

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"
WERKSTATT="${GENUS_WERKSTATT:-$HOME/.genus/werkstatt}"

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <blatt>  (z.B. weltfrage)" >&2
    exit 2
fi
blatt="$1"
name="${blatt//-/_}"
testdatei="$WERKSTATT/test_zelle_${name}.py"

if [ ! -f "$testdatei" ]; then
    echo "[WERKSTATT] kein Entwurf-Test für „$blatt“ unter $WERKSTATT" >&2
    exit 1
fi

echo "[WERKSTATT] Probefahrt für „$blatt“ (Sandbox-pytest, eigener Prozess)"
set +e
(cd "$WERKSTATT" && "$REPO_DIR/.venv/bin/python" -m pytest -q "$testdatei")
tests_exit=$?
set -e
echo "[WERKSTATT] tests_exit=$tests_exit — Ergebnis wird im Kern protokolliert"

GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" werkstatt pruefe "$blatt" \
    --tests-exit "$tests_exit"
