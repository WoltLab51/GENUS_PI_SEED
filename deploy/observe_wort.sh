#!/usr/bin/env bash
set -Eeuo pipefail

# Knowledge acquisition membrane: German word meaning WITH hierarchy.
#
# Ronny's language first. OpenThesaurus (free, no-auth, German-native) returns word
# meaning as structure: synonyms AND Oberbegriffe (hypernyms = is_a) -- exactly the
# hierarchy inference needs. This fetches it, takes the PRIMARY sense (first synset --
# German words are polysemous; full sense-handling is the next dimension), extracts the
# triples deterministically, and feeds them as relations. HTTP at the edge, no model.
# A failed fetch records nothing.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

WORT="${1:-${GENUS_WORT:-Hund}}"
SOURCE="openthesaurus"
URL="https://www.openthesaurus.de/synonyme/search"

mkdir -p "$LOG_DIR"

log() {
    printf '[WRT] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
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

# Parse the primary synset into (word, predicate, object) triples -- synonyms and
# Oberbegriffe (is_a). Only the structure travels, no model. Any failure yields nothing.
facts="$(curl -sLG --max-time 15 \
        --data-urlencode "q=$WORT" \
        --data-urlencode "format=application/json" \
        --data-urlencode "supersynsets=true" \
        "$URL" 2>/dev/null \
    | WORT="$WORT" "$REPO_DIR/.venv/bin/python" -c 'import os, sys, json
word = os.environ["WORT"]
try:
    synsets = json.load(sys.stdin).get("synsets", [])
    rows = []
    if synsets:
        primary = synsets[0]  # the dominant sense
        for t in primary.get("terms", []):
            term = t.get("term", "")
            if term and term != word and not t.get("level"):
                rows.append((word, "synonym", term))
        for sup in primary.get("supersynsets", []):
            for t in sup:
                if not t.get("level") and t.get("term"):
                    rows.append((word, "is_a", t["term"]))
                    break
    for s, p, o in rows:
        if "\t" not in o:
            print(f"{s}\t{p}\t{o}")
except Exception:
    pass' 2>/dev/null || true)"

if [ -z "$facts" ]; then
    log "fetch failed or no meaning — nothing recorded for '${WORT}'"
    exit 0
fi

count=0
while IFS=$'\t' read -r subject predicate object; do
    [ -n "$object" ] || continue
    run_genus relate "$subject" "$predicate" "$object" --source "$SOURCE" >/dev/null
    count=$((count + 1))
done <<EOF
$facts
EOF

log "ingested $count structured German relations for '${WORT}' (source=$SOURCE)"
