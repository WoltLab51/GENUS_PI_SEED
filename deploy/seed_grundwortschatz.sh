#!/usr/bin/env bash
set -Eeuo pipefail

# Seed / refresh the curated German Grundwortschatz — the deliberate, reproducible
# foundation. For each (word, Q-id) in grundwortschatz_de.tsv it (1) GUARANTEES the
# word->concept mapping via `relate <word>@de expresses <Q> --source curated`, and (2) pulls
# the concept's labels + is_a hierarchy from Wikidata via observe_konzept.sh. Deterministic,
# reviewable, re-runnable (relate upserts; observe_konzept refreshes). The list grows by
# pull request, not by ad-hoc Pi mutation -- and each Q-id is verified by its label first.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
export GENUS_DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

LIST="${GENUS_GRUNDWORTSCHATZ:-$SCRIPT_DIR/grundwortschatz_de.tsv}"
LANG_TAG="${GENUS_GRUNDWORTSCHATZ_LANG:-de}"

mkdir -p "$LOG_DIR"
log() { printf '[GWS] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

run_genus() {
    if [ "$(id -u)" -eq 0 ] && command -v runuser >/dev/null 2>&1; then
        runuser -u "$GENUS_USER" -- env \
            GENUS_DB_PATH="$GENUS_DB_PATH" GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    else
        env GENUS_DB_PATH="$GENUS_DB_PATH" GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    fi
}

if [ ! -f "$LIST" ]; then
    log "no Grundwortschatz list at $LIST — nothing to seed"
    exit 0
fi

count=0
while IFS=$'\t' read -r word qid gloss; do
    case "$word" in ''|\#*) continue ;; esac          # skip blanks and comments
    [ -n "$qid" ] || continue
    run_genus relate "${word}@${LANG_TAG}" expresses "$qid" --source curated >/dev/null
    "$SCRIPT_DIR/observe_konzept.sh" "$qid" >/dev/null 2>&1 || true
    count=$((count + 1))
done < "$LIST"

log "seeded $count curated Grundwortschatz entries (source=curated, lang=$LANG_TAG)"
