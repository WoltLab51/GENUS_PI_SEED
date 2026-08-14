#!/usr/bin/env bash
set -uo pipefail

# One-time (resumable) backfill: GENUS already knows ~5000 nouns (wortschatz_de.txt, fully
# learned), but grammatical_gender wasn't captured until observe_lexem.sh grew that capability
# (Phase B Breite, gender-by-suffix). Unlike the main round-robin learner, this is not an
# ongoing service -- a noun's gender doesn't change over time, so once every known noun has
# been through the membrane, this script is done. Skips a word that already has a recorded
# gender (idempotent, cheap to re-run after an interruption), so it never re-fetches for
# nothing. Same politeness delay + idle-priority ethos as pi_learn.sh; respects the global
# pause switch and steps aside while the box is busy.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

WORDLIST="${GENUS_BACKFILL_WORDLIST:-$SCRIPT_DIR/wortschatz_de.txt}"
CURSOR="${GENUS_BACKFILL_CURSOR:-$(dirname "$DB_PATH")/backfill_gender.cursor}"
DELAY="${GENUS_BACKFILL_DELAY:-2}"
MAX_LOAD="${GENUS_BACKFILL_MAX_LOAD:-2.0}"
IDLE_SLEEP="${GENUS_BACKFILL_IDLE_SLEEP:-60}"
PAUSED="$(dirname "$DB_PATH")/paused"

mkdir -p "$LOG_DIR"
log() { printf '[GENBACK] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

has_gender() {
    GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/python" - "$1" <<'PY'
import os, sys
from genus import db
c = db.connect_readonly(os.environ["GENUS_DB_PATH"])
subj = sys.argv[1] + "@de"
n = c.execute(
    "SELECT COUNT(*) FROM relation_projection WHERE subject=? AND predicate='grammatical_gender'",
    (subj,),
).fetchone()[0]
sys.exit(0 if n > 0 else 1)
PY
}

# Backfill the single next word from the cursor. Returns 1 when the list is exhausted.
backfill_next() {
    local start word
    start="$(cat "$CURSOR" 2>/dev/null || echo 0)"
    case "$start" in ''|*[!0-9]*) start=0 ;; esac
    word="$(grep -vE '^#|^[[:space:]]*$' "$WORDLIST" 2>/dev/null | sed -n "$((start + 1))p" | tr -d '\r' | awk '{print $1}')"
    [ -n "$word" ] || return 1
    if has_gender "$word"; then
        log "already gendered '$word' (#$((start + 1))) — skipping"
    else
        GENUS_LEXEM_LANG=de "$SCRIPT_DIR/observe_lexem.sh" "$word" >/dev/null 2>&1 || true
        log "backfilled '$word' (#$((start + 1)))"
    fi
    echo "$((start + 1))" > "$CURSOR"
    return 0
}

if [ ! -f "$WORDLIST" ]; then log "no word list at $WORDLIST — nothing to backfill"; exit 0; fi

log "gender backfill started — resumable, ${DELAY}s between words"
while true; do
    if [ -f "$PAUSED" ]; then sleep "$IDLE_SLEEP"; continue; fi
    load1="$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || echo 0)"
    if awk "BEGIN{exit !($load1 > $MAX_LOAD)}"; then sleep "$IDLE_SLEEP"; continue; fi
    if backfill_next; then
        sleep "$DELAY"
    else
        log "backfill complete — every known noun has been checked for gender"
        break
    fi
done
