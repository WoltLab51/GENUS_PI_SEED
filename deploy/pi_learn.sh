#!/usr/bin/env bash
set -uo pipefail

# Background vocabulary learner — GENUS grows its Grundwortschatz on its own, continuously,
# in the idle gaps. It runs as a long-lived daemon: word after word, forever, learning each
# by resolving it FROM TWO SOURCES (observe_konzept.sh: Wikidata concepts, the most prominent
# exact-match Q-id; observe_lexem.sh: Wikidata lexemes -> the same concepts + word class).
# Two sources on a shared edge ignite the self-checking weave (corroboration raises
# confidence). A cursor file remembers its place, so a restart picks up where it left off.
#
# It is the lowest-priority job (the installer gives it idle CPU and IO scheduling), so the
# kernel only lets it run in true idle time and it yields instantly to the punctual ticks.
# Between words it waits GENUS_LEARN_DELAY seconds -- not to spare the Pi but to be POLITE to
# Wikidata (no hammering). It checks the global pause switch every iteration, so `genus pause`
# stops it within one delay; and it steps aside while the box is busy. When the word list is
# exhausted it idles quietly, re-checking now and then for new words.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

# One or more frequency lists, learned ROUND-ROBIN so word CLASSES interleave (a noun, then a
# verb, then an adjective, ...) instead of finishing all nouns first. The noun list keeps the
# legacy cursor; each other list gets its own. Override via a space-separated GENUS_LEARN_WORDLIST.
WORDLISTS=(${GENUS_LEARN_WORDLIST:-$SCRIPT_DIR/wortschatz_de.txt $SCRIPT_DIR/wortschatz_de_verben.txt $SCRIPT_DIR/wortschatz_de_adjektive.txt})
CURSOR="${GENUS_LEARN_CURSOR:-$(dirname "$DB_PATH")/learn.cursor}"
RRSTATE="$(dirname "$DB_PATH")/learn.rr"      # which list to draw from next
DELAY="${GENUS_LEARN_DELAY:-2}"            # seconds between words -- politeness to Wikidata
MAX_LOAD="${GENUS_LEARN_MAX_LOAD:-2.0}"    # step aside while the box is busy
IDLE_SLEEP="${GENUS_LEARN_IDLE_SLEEP:-60}" # nap length while paused / busy / exhausted
PAUSED="$(dirname "$DB_PATH")/paused"
EMBED_PY="${GENUS_EMBED_PYTHON:-$GENUS_HOME/.genus/embed-venv/bin/python}"  # edge embedder (optional)

mkdir -p "$LOG_DIR"
log() { printf '[LRN] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Learn the next word from ONE list (its own cursor). Returns 1 when that list is exhausted.
# Three sources per word, each a distinct voice the weave can weigh:
#  - concept membrane (Wikidata Q-ids): the clean concept backbone + is_a hierarchy
#  - lexeme membrane (Wikidata L-ids -> same concepts): corroborates expresses, adds pos
#  - dbnary membrane (German Wiktionary as RDF): the human-written MEANING layer
#    (defined_as, all word classes) -- bound sense-safe (no flat is_a), German edition only
# Shared edges (expresses, pos) gain a second/third source -> confidence rises above seed. The
# edge embedder then bridges the concepts to their senses (capped) -- only if installed.
learn_from() {
    local wl="$1" cur start word
    case "$wl" in
        *wortschatz_de.txt) cur="$CURSOR" ;;                                   # legacy noun cursor
        *) cur="$(dirname "$DB_PATH")/learn.$(basename "$wl" .txt).cursor" ;;
    esac
    start="$(cat "$cur" 2>/dev/null || echo 0)"
    case "$start" in ''|*[!0-9]*) start=0 ;; esac
    word="$(grep -vE '^#|^[[:space:]]*$' "$wl" 2>/dev/null | sed -n "$((start + 1))p" | tr -d '\r' | awk '{print $1}')"
    [ -n "$word" ] || return 1
    GENUS_KONZEPT_SEARCH_LANG=de "$SCRIPT_DIR/observe_konzept.sh" "$word" >/dev/null 2>&1 || true
    GENUS_LEXEM_LANG=de "$SCRIPT_DIR/observe_lexem.sh" "$word" >/dev/null 2>&1 || true
    GENUS_DBNARY_LANG=de "$SCRIPT_DIR/observe_dbnary.sh" "$word" >/dev/null 2>&1 || true
    if [ -x "$EMBED_PY" ]; then
        GENUS_DB_PATH="$DB_PATH" "$EMBED_PY" "$SCRIPT_DIR/bridge_senses.py" "$word" >/dev/null 2>&1 || true
    fi
    echo "$((start + 1))" > "$cur"
    log "learned '$word' (#$((start + 1)) of $(basename "$wl")) — concept + lexeme + dbnary + bridge"
    return 0
}

# Round-robin across the lists so the word classes interleave; 1 only when ALL are exhausted.
learn_next() {
    local n=${#WORDLISTS[@]} i idx rr
    rr="$(cat "$RRSTATE" 2>/dev/null || echo 0)"
    case "$rr" in ''|*[!0-9]*) rr=0 ;; esac
    for ((i = 0; i < n; i++)); do
        idx=$(((rr + i) % n))
        if learn_from "${WORDLISTS[$idx]}"; then
            echo "$(((idx + 1) % n))" > "$RRSTATE"
            return 0
        fi
    done
    return 1
}

# "Die Kette": when the word list is exhausted, GENUS grows from its OWN graph -- it learns a
# concept it references as an is_a parent but has not climbed yet (gaps). So the hierarchy grows
# itself, connected, with no external list. observe_konzept accepts a Q-id directly.
learn_gap() {
    local qid
    qid="$(GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" gaps --predicate is_a --limit 1 \
           2>/dev/null | head -1)"
    [ -n "$qid" ] || return 1
    GENUS_KONZEPT_SEARCH_LANG=de "$SCRIPT_DIR/observe_konzept.sh" "$qid" >/dev/null 2>&1 || true
    log "climbed gap concept $qid (die Kette)"
    return 0
}

_have_list=0; for wl in "${WORDLISTS[@]}"; do [ -f "$wl" ] && _have_list=1; done
if [ "$_have_list" = 0 ]; then log "no word lists found — nothing to learn"; exit 0; fi

# Single step (for testing): GENUS_LEARN_ONCE=1
if [ "${GENUS_LEARN_ONCE:-0}" = "1" ]; then
    if [ -f "$PAUSED" ]; then log "paused — skipping"; exit 0; fi
    learn_next || log "word list exhausted"
    exit 0
fi

# Continuous: learn fortlaufend, in idle time, pausable.
log "learner started — continuous, ${DELAY}s between words"
while true; do
    if [ -f "$PAUSED" ]; then sleep "$IDLE_SLEEP"; continue; fi
    load1="$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || echo 0)"
    if awk "BEGIN{exit !($load1 > $MAX_LOAD)}"; then sleep "$IDLE_SLEEP"; continue; fi
    if learn_next; then
        sleep "$DELAY"
    elif learn_gap; then
        sleep "$DELAY"           # list done -> climb the graph's own gaps (die Kette)
    else
        log "word list exhausted and no open gaps — idling (re-checking every ${IDLE_SLEEP}s)"
        sleep "$IDLE_SLEEP"
    fi
done
