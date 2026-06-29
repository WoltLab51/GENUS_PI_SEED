#!/usr/bin/env bash
set -Eeuo pipefail

# Seed / refresh the German Grundwortschatz — the deliberate, reproducible foundation.
# grundwortschatz_de.tsv is just the VOCABULARY (one word per line, no Q-ids). For each word,
# observe_konzept.sh resolves it to a concept FROM THE SOURCE (Wikidata search -> the most
# prominent genuine concept by sitelinks) and learns its labels + is_a hierarchy -- GENUS
# hangs on the source, it does not trust hand-typed Q-ids. Prints a review report
# (word -> resolved concept) so the rare miss is visible and can be taken back with
# `genus unrelate`. Re-runnable; the vocabulary grows by pull request, not by Pi mutation.

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
while IFS= read -r line; do
    word="$(printf '%s' "$line" | tr -d '\r' | awk '{print $1}')"   # first token, no CR
    case "$word" in ''|\#*) continue ;; esac          # skip blanks and comments
    # GENUS resolves the word to a concept FROM THE SOURCE (observe_konzept.sh: Wikidata
    # search -> most-prominent genuine concept), then learns its labels + is_a hierarchy.
    GENUS_KONZEPT_SEARCH_LANG="$LANG_TAG" "$SCRIPT_DIR/observe_konzept.sh" "$word" >/dev/null 2>&1 || true
    resolved="$(run_genus relations "${word}@${LANG_TAG}" 2>/dev/null \
        | grep -m1 'expresses' | sed -E 's/^\[REL\] [^ ]+ -\[expresses\]-> //; s/   .*$//' || true)"
    printf '[GWS] %-12s -> %s\n' "$word" "${resolved:-(nicht aufgelöst — Quelle liefert kein Konzept)}"
    count=$((count + 1))
done < "$LIST"

log "processed $count Grundwortschatz words (resolved from source, lang=$LANG_TAG)"
