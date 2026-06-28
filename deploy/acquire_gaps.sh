#!/usr/bin/env bash
set -Eeuo pipefail

# Gap-driven (permanent) learning loop.
#
# GENUS asks ITSELF which referenced words it does not know yet (`genus gaps` -- objects
# of its own synonym/antonym edges that are not yet subjects), and the membrane fetches
# their meaning (observe_word.sh). The vocabulary grows out of its own edges, from a
# seed -- directed and bounded, never "slurp the internet". No LLM. Bounded per tick by
# GENUS_GAP_LIMIT so the dictionary API is treated gently.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
LIMIT="${GENUS_GAP_LIMIT:-5}"

mkdir -p "$LOG_DIR"

log() {
    printf '[GAP] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

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

words="$(run_genus gaps --limit "$LIMIT" 2>/dev/null || true)"

if [ -z "$words" ]; then
    log "no gaps — every referenced word is known"
    exit 0
fi

count=0
while IFS= read -r word; do
    [ -n "$word" ] || continue
    GENUS_DB_PATH="$DB_PATH" GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
        "$SCRIPT_DIR/observe_word.sh" "$word" >/dev/null 2>&1 || true
    count=$((count + 1))
done <<EOF
$words
EOF

log "acquired $count gap word(s)"
