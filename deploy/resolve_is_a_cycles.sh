#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve the is_a cycles GENUS's reflexive rule-check found in its own graph.
#
# A transitive predicate must be ACYCLIC: if is_a closes a ring A->...->A, transitivity would
# derive A is_a A and the whole ring collapses into one class -- a self-contradiction, not a fact
# (see genus/inference.py `cycles`, surfaced in `genus knowledge`). Wikidata itself carries these
# P279 rings (verified live: both directions are asserted upstream), so the acquisition faithfully
# ingested a real upstream contradiction. Here we take back the ONE reverse edge per ring whose
# direction is clearly wrong, keeping the correct subtype direction. Each edge is Wikidata-only, so
# `--source wikidata` removes it precisely; retraction is event-sourced (a `relation_retracted`
# fact), reversible, and idempotent -- safe to re-run.
#
# Three rings had an unambiguous direction and are resolved below. A FOURTH ring is left standing
# on purpose: Datenträger -> manifestation -> Kommunikationsmedien -> (back) is abstract
# upper-ontology where no single edge is clearly wrong. Per "nichts blind löschen" it stays flagged
# (the detector keeps surfacing it in `genus knowledge`) until it can be settled by teaching.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"

run_genus() {
    if [ "$(id -u)" -eq 0 ] && command -v runuser >/dev/null 2>&1; then
        runuser -u "$GENUS_USER" -- env \
            GENUS_DB_PATH="$DB_PATH" GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    else
        env GENUS_DB_PATH="$DB_PATH" GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    fi
}

# Each line: WRONG_SUBJECT WRONG_OBJECT  # retract WRONG (keep the reverse, the true subtype)
#   Q41415  (Suppe)   is_a Q118489612 (minestra)  -> WRONG; keep minestra is_a Suppe
#   Q1137365(Eingang) is_a Q854429    (Portal)     -> WRONG; keep Portal   is_a Eingang
#   Q1756942(part.Fkt)is_a Q11348     (Funktion)   -> WRONG; keep Funktion is_a partielle Funktion (total ⊂ partial)
while read -r subj obj; do
    [ -n "${subj:-}" ] || continue
    case "$subj" in \#*) continue ;; esac
    run_genus unrelate "$subj" is_a "$obj" --source wikidata
done <<'EOF'
Q41415    Q118489612
Q1137365  Q854429
Q1756942  Q11348
EOF

echo "[FIX] is_a cycles resolved (3 reverse edges retracted); run 'genus knowledge' to confirm."
