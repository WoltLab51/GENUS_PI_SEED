#!/usr/bin/env bash
set -uo pipefail
umask 077

# Background vocabulary learner — GENUS grows its Grundwortschatz on its own, continuously,
# in the idle gaps. It runs as a long-lived daemon: word after word, forever, learning each
# by resolving it FROM TWO SOURCES (observe_konzept.sh: Wikidata concepts, the most prominent
# exact-match Q-id; observe_lexem.sh: Wikidata lexemes -> the same concepts + word class).
# Two sources on a shared edge ignite the self-checking weave (corroboration raises
# confidence). A cursor file remembers its place, so a restart picks up where it left off.
#
# Priority each tick: a gezielte Fachliste (learn_fach, if configured) -> the general breadth
# lists (learn_next, round-robin) -> die Kette (learn_gap, only once breadth is exhausted).
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
# "Gezielt": optional domain word list(s) (Fachwissen, Punkt 3 des Gedächtnis-Konzepts, GENUS_
# GEDAECHTNIS.md) -- same file format/machinery as WORDLISTS (learn_from's cursor-naming already
# generalizes to any filename), but tried FIRST every tick, ahead of the general breadth lists.
# Equal round-robin among a 500-word Fachliste and 5000+ general words would dilute "gezielt"
# into just another equally-weighted list; trying it first instead means it grows as fast as the
# source allows while breadth keeps filling the remaining ticks. Empty by default -- zero
# behaviour change until a real domain list is configured (still waiting on which domain).
FACHLISTEN=(${GENUS_LEARN_FACHLISTEN:-})
CURSOR="${GENUS_LEARN_CURSOR:-$(dirname "$DB_PATH")/learn.cursor}"
RRSTATE="$(dirname "$DB_PATH")/learn.rr"      # which list to draw from next
DELAY="${GENUS_LEARN_DELAY:-2}"            # seconds between words -- politeness to Wikidata
MAX_LOAD="${GENUS_LEARN_MAX_LOAD:-2.0}"    # step aside while the box is busy
IDLE_SLEEP="${GENUS_LEARN_IDLE_SLEEP:-60}" # nap length while paused / busy / exhausted
PAUSED="$(dirname "$DB_PATH")/paused"
EMBED_PY="${GENUS_EMBED_PYTHON:-$GENUS_HOME/.genus/embed-venv/bin/python}"  # edge embedder (optional)
GAP_ATTEMPTS="${GENUS_LEARN_GAP_ATTEMPTS:-$(dirname "$DB_PATH")/learn.gap_attempts}"  # tried gaps + when
GAP_RETRY_TTL="${GENUS_LEARN_GAP_RETRY_TTL:-21600}"   # 6h: retry an unclosable gap at most this often
GAP_FETCH="${GENUS_LEARN_GAP_FETCH:-100}"             # how many open gaps to consider each round

mkdir -p "$LOG_DIR"
log() { printf '[LRN] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Learn the next word from ONE list (its own cursor). Returns 1 when that list is exhausted.
# Three sources per word, each a distinct voice the weave can weigh:
#  - concept membrane (Wikidata Q-ids): the clean concept backbone + is_a hierarchy
#  - lexeme membrane (Wikidata L-ids -> same concepts): corroborates expresses, adds pos
#  - dbnary membrane (German Wiktionary as RDF): the human-written MEANING layer
#    (defined_as, all word classes) -- bound sense-safe (no flat is_a), German edition only
# Shared edges (expresses, pos) gain a second/third source -> confidence rises above seed. The
# edge embedder then bridges the concepts to their senses (capped) AND weaves the word's
# verwandt edges (Bedeutungs-Nähe als Gewicht) -- both only if installed. So the similarity
# net (genus.verwandt) grows WITH the vocabulary rather than staying a one-off snapshot.
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
        # ... und die VERWANDT-Kanten dieses Worts weben (Bedeutungs-Nähe als Gewicht, gedeckelt):
        # so wächst das Ähnlichkeits-Netz MIT dem Wortschatz mit, statt ein einmaliger Schnappschuss
        # zu bleiben. Symmetrisch gelesen -- ein später gelerntes Geschwister findet dieses hier.
        GENUS_DB_PATH="$DB_PATH" "$EMBED_PY" "$SCRIPT_DIR/verwandtschaft.py" "$word" >/dev/null 2>&1 || true
    fi
    echo "$((start + 1))" > "$cur"
    log "learned '$word' (#$((start + 1)) of $(basename "$wl")) — concept + lexeme + dbnary + bridge + verwandt"
    return 0
}

# Vokabel-bei-Begegnung (Ronny 2026-07-05): der gesprächsnahe Zwilling des Lücken-Detektors.
# Der Bot (Membran) schreibt ein im Chat begegnetes, unbekanntes Wort in die Warteschlange;
# hier wird das erste (FIFO) VOR allen Frequenzlisten gelernt -- das Wort, das der Nutzer
# gerade benutzt hat, springt an die Spitze statt auf die Liste zu warten. One-shot: ein nicht
# auflösbares Wort (Tippfehler/fremd) wird trotzdem entfernt (kein Retry-Hämmern). 1, wenn die
# Schlange leer ist.
LERNWUNSCH="${GENUS_LERNWUNSCH:-$(dirname "$DB_PATH")/lernwunsch.txt}"
CHAT_WORD_STATUS_FILE="${GENUS_CHAT_WORD_STATUS_FILE:-$(dirname "$DB_PATH")/chat_word_learning_status.json}"
CHAT_WORD_LEARNING="${GENUS_CHAT_WORD_LEARNING:-0}"
CHAT_WORD_CONSENT_FILE="${GENUS_CHAT_WORD_CONSENT_FILE:-$(dirname "$DB_PATH")/chat_word_learning.enabled}"
CHAT_WORD_CONSENT_VALUE="external-lexicon:definition-term"
if [ "$CHAT_WORD_LEARNING" != "1" ] \
   && [ -f "$CHAT_WORD_CONSENT_FILE" ] \
   && [ ! -L "$CHAT_WORD_CONSENT_FILE" ] \
   && [ "$(stat -c '%U:%a' "$CHAT_WORD_CONSENT_FILE" 2>/dev/null || true)" = "$GENUS_USER:600" ] \
   && [ "$(tr -d '\r\n' < "$CHAT_WORD_CONSENT_FILE" 2>/dev/null || true)" = "$CHAT_WORD_CONSENT_VALUE" ]; then
    CHAT_WORD_LEARNING=1
fi
learn_begegnung() {
    local word tmp lock_fd dequeued=0
    [ "$CHAT_WORD_LEARNING" = "1" ] || return 1
    mkdir -p "$(dirname "$LERNWUNSCH")" || return 1
    exec {lock_fd}>"$LERNWUNSCH.lock" || return 1
    chmod 600 "$LERNWUNSCH.lock" 2>/dev/null || true
    flock -x "$lock_fd" || { exec {lock_fd}>&-; return 1; }
    if [ ! -s "$LERNWUNSCH" ]; then
        flock -u "$lock_fd"
        exec {lock_fd}>&-
        return 1
    fi
    word="$(sed -n '1p' "$LERNWUNSCH" | tr -d '\r' | awk '{print $1}')"
    # das erste Wort aus der Schlange nehmen (auch wenn das Lernen scheitert -- one-shot)
    tmp="$LERNWUNSCH.tmp.$$"
    if tail -n +2 "$LERNWUNSCH" > "$tmp" 2>/dev/null \
       && chmod 600 "$tmp" \
       && mv "$tmp" "$LERNWUNSCH"; then
        dequeued=1
    else
        rm -f "$tmp"
    fi
    flock -u "$lock_fd"
    exec {lock_fd}>&-
    [ "$dequeued" = "1" ] && [ -n "$word" ] || return 1
    GENUS_CHAT_WORD_STATUS_FILE="$CHAT_WORD_STATUS_FILE" \
        "$REPO_DIR/.venv/bin/python" "$SCRIPT_DIR/chat_word_learning.py" \
        mark "$word" learning >/dev/null 2>&1 || true
    GENUS_KONZEPT_SEARCH_LANG=de "$SCRIPT_DIR/observe_konzept.sh" "$word" >/dev/null 2>&1 || true
    GENUS_LEXEM_LANG=de "$SCRIPT_DIR/observe_lexem.sh" "$word" >/dev/null 2>&1 || true
    GENUS_DBNARY_LANG=de "$SCRIPT_DIR/observe_dbnary.sh" "$word" >/dev/null 2>&1 || true
    if [ -x "$EMBED_PY" ]; then
        GENUS_DB_PATH="$DB_PATH" "$EMBED_PY" "$SCRIPT_DIR/bridge_senses.py" "$word" >/dev/null 2>&1 || true
        GENUS_DB_PATH="$DB_PATH" "$EMBED_PY" "$SCRIPT_DIR/verwandtschaft.py" "$word" >/dev/null 2>&1 || true
    fi
    if GENUS_CHAT_WORD_STATUS_FILE="$CHAT_WORD_STATUS_FILE" \
       "$REPO_DIR/.venv/bin/python" "$SCRIPT_DIR/chat_word_learning.py" \
       finish "$word" "$DB_PATH" >/dev/null 2>&1; then
        log "learned one encountered chat word (content redacted; explicit opt-in)"
    else
        log "could not resolve one encountered chat word (content redacted; explicit opt-in)"
    fi
    return 0
}

# Tries each configured Fach-list in order (not round-robin -- a small, prioritized set, not
# competing classes); 1 if none are configured or all are exhausted for this tick.
learn_fach() {
    local wl
    for wl in "${FACHLISTEN[@]}"; do
        [ -n "$wl" ] && [ -f "$wl" ] && learn_from "$wl" && return 0
    done
    return 1
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

# "Die Kette": when the word list is exhausted, GENUS grows from its OWN graph -- it climbs a
# concept it references as an is_a parent but has not learned yet (a gap). observe_konzept takes
# a Q-id directly, so the hierarchy grows itself, connected, with no external list.
#
# NOT every gap is closable: a concept whose Wikidata item has no subclass_of (P279) -- e.g. a
# taxon leaf that carries "parent taxon" instead -- can never gain an is_a subject edge from this
# source, so it stays a gap forever. `gaps` returns them in a STABLE order, so naively taking the
# first one PINS the learner on the first unclosable gap (observed live: 20k+ repeats of the same
# Q-id in ~24h, learning nothing, hammering Wikidata for no gain). Fix the class, not the
# instance: remember each attempted gap with a timestamp and skip it for GAP_RETRY_TTL, so the
# learner rotates through the OTHER gaps. A closable gap vanishes from `gaps` after its first
# climb (it becomes a subject); an unclosable one is retried at most once per TTL, in case the
# source later grows a P279. Membrane-local -- which gaps a source *can* close is edge knowledge.
learn_gap() {
    local now qid
    now="$(date +%s)"
    [ -f "$GAP_ATTEMPTS" ] || : > "$GAP_ATTEMPTS"
    # prune attempts older than the TTL (keeps the file bounded and re-opens old gaps for retry)
    if awk -v now="$now" -v ttl="$GAP_RETRY_TTL" '($2 + ttl) > now' "$GAP_ATTEMPTS" > "$GAP_ATTEMPTS.tmp" 2>/dev/null; then
        mv "$GAP_ATTEMPTS.tmp" "$GAP_ATTEMPTS"
    else
        rm -f "$GAP_ATTEMPTS.tmp"
    fi
    # the first open is_a gap not attempted within the TTL (rotate past the unclosable ones).
    # grep -f against the tried-qids column: an empty attempts file matches nothing, so every gap
    # is fresh -- unlike an awk NR==FNR trick, which mis-handles a zero-line first file.
    qid="$(GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" gaps --predicate is_a --limit "$GAP_FETCH" 2>/dev/null \
           | grep -vxF -f <(cut -d' ' -f1 "$GAP_ATTEMPTS") 2>/dev/null | head -1)"
    [ -n "$qid" ] || return 1        # nothing fresh to climb -> idle (every open gap tried recently)
    GENUS_KONZEPT_SEARCH_LANG=de "$SCRIPT_DIR/observe_konzept.sh" "$qid" >/dev/null 2>&1 || true
    printf '%s %s\n' "$qid" "$now" >> "$GAP_ATTEMPTS"
    log "climbed gap concept $qid (die Kette)"
    return 0
}

_have_list=0; for wl in "${WORDLISTS[@]}"; do [ -f "$wl" ] && _have_list=1; done
if [ "$_have_list" = 0 ]; then log "no word lists found — nothing to learn"; exit 0; fi

# Single step (for testing): GENUS_LEARN_ONCE=1 -- one full learn step, a word OR a gap climb,
# the same choice the continuous loop makes.
if [ "${GENUS_LEARN_ONCE:-0}" = "1" ]; then
    if [ -f "$PAUSED" ]; then log "paused — skipping"; exit 0; fi
    learn_begegnung || learn_fach || learn_next || learn_gap || log "nothing to learn (list exhausted, no fresh gaps)"
    exit 0
fi

# Continuous: learn fortlaufend, in idle time, pausable.
log "learner started — continuous, ${DELAY}s between words"
while true; do
    if [ -f "$PAUSED" ]; then sleep "$IDLE_SLEEP"; continue; fi
    load1="$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || echo 0)"
    if awk "BEGIN{exit !($load1 > $MAX_LOAD)}"; then sleep "$IDLE_SLEEP"; continue; fi
    if learn_begegnung; then
        sleep "$DELAY"           # ein im Chat begegnetes Wort geht VOR allem (gesprächsnah)
    elif learn_fach; then
        sleep "$DELAY"           # gezielte Fachliste geht vor der allgemeinen Breite
    elif learn_next; then
        sleep "$DELAY"
    elif learn_gap; then
        sleep "$DELAY"           # list done -> climb the graph's own gaps (die Kette)
    else
        log "word list exhausted and no open gaps — idling (re-checking every ${IDLE_SLEEP}s)"
        sleep "$IDLE_SLEEP"
    fi
done
