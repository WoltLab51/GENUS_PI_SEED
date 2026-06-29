#!/usr/bin/env bash
set -Eeuo pipefail

# Background vocabulary learner — GENUS grows its Grundwortschatz on its own, in the gaps.
#
# Reads a German word list (the breadth driver) and learns the next bounded BATCH each run
# by resolving each word FROM THE SOURCE (observe_konzept.sh: Wikidata -> the most prominent
# exact-match concept), then climbing the chain. A cursor file remembers how far it got, so
# it picks up where it left off. It is the LOWEST priority job: the installer runs it with
# idle CPU/IO scheduling (nice/ionice), so it yields instantly to the punctual sensor ticks
# and only fills true idle time. It honors the global pause switch (genus pause) before and
# DURING the batch, so it can be stopped at any moment. Gentle on the source by design.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

WORDLIST="${GENUS_LEARN_WORDLIST:-$SCRIPT_DIR/wortschatz_de.txt}"
CURSOR="${GENUS_LEARN_CURSOR:-$(dirname "$DB_PATH")/learn.cursor}"
BATCH="${GENUS_LEARN_BATCH:-10}"
MAX_LOAD="${GENUS_LEARN_MAX_LOAD:-2.0}"   # skip a run if the box is already busy
PAUSED="$(dirname "$DB_PATH")/paused"

mkdir -p "$LOG_DIR"
log() { printf '[LRN] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# --- gates: pause first, then "is the box busy right now?" ---------------------------
if [ -f "$PAUSED" ]; then log "paused — skipping"; exit 0; fi
if [ ! -f "$WORDLIST" ]; then log "no word list at $WORDLIST — nothing to learn"; exit 0; fi
load1="$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || echo 0)"
if awk "BEGIN{exit !($load1 > $MAX_LOAD)}"; then
    log "load $load1 > $MAX_LOAD — yielding, will try again later"
    exit 0
fi

# --- the next bounded batch, resuming from the cursor --------------------------------
start="$(cat "$CURSOR" 2>/dev/null || echo 0)"
case "$start" in ''|*[!0-9]*) start=0 ;; esac
words="$(grep -vE '^#|^[[:space:]]*$' "$WORDLIST" | sed -n "$((start + 1)),$((start + BATCH))p")"
if [ -z "$words" ]; then
    log "word list exhausted at $start — nothing new to learn"
    exit 0
fi

n=0
while IFS= read -r line; do
    if [ -f "$PAUSED" ]; then log "paused mid-batch — stopping at +$n"; break; fi
    word="$(printf '%s' "$line" | tr -d '\r' | awk '{print $1}')"
    [ -n "$word" ] || continue
    GENUS_KONZEPT_SEARCH_LANG=de "$SCRIPT_DIR/observe_konzept.sh" "$word" >/dev/null 2>&1 || true
    n=$((n + 1))
done <<EOF
$words
EOF

echo "$((start + n))" > "$CURSOR"
log "learned $n word(s) from the source; cursor now $((start + n))"
