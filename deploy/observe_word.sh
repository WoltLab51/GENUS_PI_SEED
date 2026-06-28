#!/usr/bin/env bash
set -Eeuo pipefail

# Knowledge acquisition membrane: structured word meaning.
#
# The first proof that GENUS can suck *structured* knowledge out of the internet
# WITHOUT a model -- and exactly what Ronny wants: "the meaning of a word in relationship
# x". A free, no-auth dictionary API returns word meaning as structure (part of speech,
# synonyms, antonyms); this fetches it, extracts the triples deterministically, and hands
# them in as relations -- (run, is_a, verb), (run, synonym, execute). HTTP lives HERE at
# the edge; no interpretation, just parsing -- the LLM is not involved. A failed fetch
# records nothing.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

WORD="${1:-${GENUS_WORD:-knowledge}}"
SOURCE="dictionaryapi"
URL="https://api.dictionaryapi.dev/api/v2/entries/en/${WORD}"

mkdir -p "$LOG_DIR"

log() {
    printf '[WRD] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
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

# Parse the JSON into (word, predicate, object) triples -- only the structure travels,
# no free text, no model. -L follows the API's redirect; any failure yields nothing.
facts="$(curl -sL --max-time 15 "$URL" 2>/dev/null \
    | "$REPO_DIR/.venv/bin/python" -c 'import sys, json
try:
    entry = json.load(sys.stdin)[0]
    word = entry["word"]
    rows = []
    for m in entry.get("meanings", []):
        pos = m.get("partOfSpeech")
        if pos:
            rows.append((word, "is_a", pos))
        for syn in (m.get("synonyms") or [])[:4]:
            rows.append((word, "synonym", syn))
        for ant in (m.get("antonyms") or [])[:3]:
            rows.append((word, "antonym", ant))
    for s, p, o in rows:
        if o and "\t" not in o:
            print(f"{s}\t{p}\t{o}")
except Exception:
    pass' 2>/dev/null || true)"

if [ -z "$facts" ]; then
    log "fetch failed or no meaning — nothing recorded for ${WORD}"
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

log "ingested $count structured meaning relations for '${WORD}' (source=$SOURCE)"
