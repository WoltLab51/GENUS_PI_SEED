#!/usr/bin/env bash
set -Eeuo pipefail

# Second knowledge source: Wikidata LEXEMES — the ignition key for the self-checking weave.
#
# observe_konzept.sh feeds the graph from Wikidata *concepts* (Q-ids, one source). This feeds
# it from Wikidata *lexemes* (L-ids) under a DIFFERENT source name ("wikidata-lexemes"), and
# lands on the SAME concept level: a lexeme's sense links to a concept via P5137 ("item for
# this sense"), so we emit `<lemma>@<lang> -expresses-> Q`. When that triple already exists
# from `observe_konzept` (source "wikidata"), it now has TWO sources -> relation_confidence
# rises above the seed and the weave's ① fires. Lexemes also reach BEYOND nouns: the lexical
# category gives `<lemma>@<lang> -pos-> verb|adjective|…` so GENUS knows word classes.
#
# Semi-independent (same provider, a separate dataset/editor process). Exact-lemma discipline
# like the concept membrane: only a lexeme whose lemma is exactly the word counts; no model;
# a failed fetch records nothing. Sense-clean by construction (senses point at neutral Q).

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

WORD="${1:-${GENUS_LEXEM:-Hund}}"
LANG="${GENUS_LEXEM_LANG:-de}"
LANG_QID="${GENUS_LEXEM_LANG_QID:-Q188}"   # German; override for other lexeme languages
SOURCE="wikidata-lexemes"
API="https://www.wikidata.org/w/api.php"
UA="GENUS-PI/0.1 (epistemic core research; ronnywolter87@gmail.com)"

mkdir -p "$LOG_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log() { printf '[LEX] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

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

wd_get() { curl -sS -H "User-Agent: $UA" --max-time 25 "$1" -o "$2" 2>/dev/null || true; }

# 1. Find German lexemes for the word.
enc="$("$REPO_DIR/.venv/bin/python" -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$WORD")"
wd_get "$API?action=wbsearchentities&search=$enc&language=$LANG&uselang=$LANG&type=lexeme&limit=10&format=json" "$TMP/search.json"
lids="$("$REPO_DIR/.venv/bin/python" -c 'import json,sys; print("|".join(h["id"] for h in json.load(open(sys.argv[1])).get("search",[])))' "$TMP/search.json")"

if [ -z "$lids" ]; then
    log "no lexeme found for '$WORD' — nothing recorded"
    exit 0
fi

# 2. Fetch the lexemes (lemmas, lexical category, senses).
wd_get "$API?action=wbgetentities&ids=$lids&format=json" "$TMP/lexemes.json"

# 3. Emit triples: expresses (lemma@lang -> Q, from each sense's P5137) + pos (word class).
#    Only lexemes in the target language whose lemma is EXACTLY the word (the same exact-match
#    discipline as the concept membrane -- no prefix/inflection drift).
facts="$(WORD="$WORD" LANG="$LANG" LANG_QID="$LANG_QID" "$REPO_DIR/.venv/bin/python" - "$TMP/lexemes.json" <<'PY'
import json, os, sys

# Exact, case-sensitive lemma match: in German capitalization is semantic, so the verb
# "laufen" and the place "Laufen" are different words -- a casefold match would conflate them.
word = os.environ["WORD"]
lang = os.environ["LANG"]
lang_qid = os.environ["LANG_QID"]
# Common lexical-category Q-ids -> readable part of speech (fall back to the raw Q-id).
POS = {
    "Q1084": "noun", "Q24905": "verb", "Q34698": "adjective", "Q380057": "adverb",
    "Q4833830": "preposition", "Q36484": "conjunction", "Q147276": "pronoun",
    "Q103184": "numeral", "Q380012": "interjection", "Q468801": "article",
}
# German grammatical gender (P5185, a claim on the LEXEME itself -- not per-sense) -- the raw
# material for SYSTEME's second rule-domain (gender-by-suffix induction). Only meaningful for
# nouns; German is grammatical-gender-marked so this is a real, queryable lexical fact, not an
# inference.
GENDER = {"Q499327": "maskulin", "Q1775415": "feminin", "Q1775461": "neutrum"}
out, seen = [], set()
try:
    entities = json.load(open(sys.argv[1])).get("entities", {})
except Exception:
    entities = {}
for lid, ent in entities.items():
    if ent.get("language") != lang_qid:
        continue
    lemma = (ent.get("lemmas", {}).get(lang, {}) or {}).get("value")
    if not lemma or lemma != word or "\t" in lemma or "@" in lemma:
        continue
    subj = "%s@%s" % (lemma, lang)
    cat = ent.get("lexicalCategory")
    if cat:
        out.append("%s\tpos\t%s" % (subj, POS.get(cat, cat)))
    if cat == "Q1084":  # noun -- grammatical gender only applies here
        for claim in ent.get("claims", {}).get("P5185", []):
            dv = claim.get("mainsnak", {}).get("datavalue")
            if dv:
                gender = GENDER.get(dv["value"]["id"])
                if gender:
                    out.append("%s\tgrammatical_gender\t%s" % (subj, gender))
    for sense in ent.get("senses", []):
        for claim in sense.get("claims", {}).get("P5137", []):
            dv = claim.get("mainsnak", {}).get("datavalue")
            if dv:
                q = dv["value"]["id"]
                if (subj, q) not in seen:
                    seen.add((subj, q))
                    out.append("%s\texpresses\t%s" % (subj, q))
print("\n".join(out))
PY
)"

if [ -z "$facts" ]; then
    log "no German lexeme matched '$WORD' exactly — nothing recorded"
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

log "ingested $count lexeme relations for '$WORD' (source=$SOURCE)"
