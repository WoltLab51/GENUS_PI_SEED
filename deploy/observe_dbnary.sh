#!/usr/bin/env bash
set -Eeuo pipefail

# Third knowledge source: DBnary -- the German Wiktionary as Linguistic Linked Open Data.
#
# The living, human-written, sense-resolved lexicon Wikidata lacks. DBnary serves Wiktionary
# as clean RDF over a SPARQL endpoint, so no wikitext parsing. CORRECTNESS over volume, two
# guards so the binding never goes "beside":
#   1. Only the GERMAN Wiktionary edition (named graph dbnary/deu) -- DBnary aggregates many
#      editions (the German word "Hund" is documented in the Swedish, Spanish, ... Wiktionaries
#      too); without this guard their senses bleed into German ones.
#   2. Only edges that flatten to word level WITHOUT losing the sense: the DEFINITIONS (a word
#      legitimately has many meanings -- listing them all is correct, not contradictory) and
#      the part of speech. We do NOT emit DBnary's is_a/synonyms: those are sense-bound, and a
#      flat `Hund -is_a-> Sternbild` (true for one sense only) would re-introduce the very
#      sense-contamination the two-layer model removed. is_a stays concept-clean from Wikidata;
#      mapping a DBnary sense onto a concept is a separate bridge step (Wort != Bedeutung).
#
# Source "dbnary"; exact, case-sensitive lemma match (the SPARQL writtenRep match is exact).
# A failed fetch records nothing. HTTP lives here at the edge, never in the core.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

WORD="${1:-${GENUS_DBNARY:-Hund}}"
LANG="${GENUS_DBNARY_LANG:-de}"
GRAPH="${GENUS_DBNARY_GRAPH:-http://kaiko.getalp.org/dbnary/deu}"
ENDPOINT="${GENUS_DBNARY_ENDPOINT:-https://kaiko.getalp.org/sparql}"
SOURCE="dbnary"
UA="GENUS-PI/0.1 (epistemic core research; ronnywolter87@gmail.com)"
MAX_DEF="${GENUS_DBNARY_MAX_DEF:-200}"   # clip very long glosses

mkdir -p "$LOG_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log() { printf '[DBN] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

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

# Build the SPARQL query: German edition only, the exact word, its POS + per-sense definitions.
QUERY="$(WORD="$WORD" LANG="$LANG" GRAPH="$GRAPH" "$REPO_DIR/.venv/bin/python" - <<'PY'
import os
word, lang, graph = os.environ["WORD"], os.environ["LANG"], os.environ["GRAPH"]
word = word.replace("\\", "\\\\").replace('"', '\\"')
print(f'''PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
PREFIX lexinfo: <http://www.lexinfo.net/ontology/2.0/lexinfo#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT DISTINCT ?s ?pos ?def FROM <{graph}> WHERE {{
  ?e ontolex:canonicalForm/ontolex:writtenRep "{word}"@{lang} ;
     lexinfo:partOfSpeech ?pos ; ontolex:sense ?s .
  OPTIONAL {{ ?s skos:definition/rdf:value ?def }}
}} LIMIT 60''')
PY
)"

enc="$("$REPO_DIR/.venv/bin/python" -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$QUERY")"
curl -sS -H "User-Agent: $UA" -H "Accept: application/sparql-results+json" --max-time 30 \
    "$ENDPOINT?query=$enc&format=json" -o "$TMP/r.json" 2>/dev/null || true

# Emit triples: pos (one per part of speech) + defined_as (one per German-edition sense).
facts="$(WORD="$WORD" LANG="$LANG" MAX_DEF="$MAX_DEF" "$REPO_DIR/.venv/bin/python" - "$TMP/r.json" <<'PY'
import json, os, re, sys
word, lang, maxd = os.environ["WORD"], os.environ["LANG"], int(os.environ["MAX_DEF"])
POS = {"noun": "noun", "properNoun": "noun", "verb": "verb", "adjective": "adjective",
       "adverb": "adverb", "preposition": "preposition", "conjunction": "conjunction",
       "pronoun": "pronoun", "numeral": "numeral", "interjection": "interjection",
       "article": "article"}
POS_RANK = {"noun": 0, "verb": 1, "adjective": 2}   # prefer a noun sense as the primary
subj = f"{word}@{lang}"
out, seen_pos, seen_def = [], set(), set()
senses = []  # (pos_rank, ordinal, gloss) -- to pick the primary sense
try:
    rows = json.load(open(sys.argv[1], encoding="utf-8"))["results"]["bindings"]
except Exception:
    rows = []
for b in rows:
    raw = b["pos"]["value"].rsplit("/", 1)[-1].rsplit("#", 1)[-1] if "pos" in b else "other"
    if "pos" in b:
        p = POS.get(raw, raw)
        if p not in seen_pos:
            seen_pos.add(p)
            out.append(f"{subj}\tpos\t{p}")
    if "def" in b:
        d = re.sub(r"\s+", " ", b["def"]["value"]).strip()[:maxd]
        if d and "\t" not in d:
            if d not in seen_def:
                seen_def.add(d)
                out.append(f"{subj}\tdefined_as\t{d}")
            # Sense IRIs look like ...__ws_<group>_<word>__<POS>__<subsense>; order by the
            # ws GROUP then the subsense (the trailing number alone ties -- many senses end
            # in __1). Rank on the RAW POS so a common noun (Substantiv) beats a properNoun.
            iri = b.get("s", {}).get("value", "")
            grp = re.search(r"__ws_(\d+)", iri)
            sub = re.search(r"(\d+)\s*$", iri)
            senses.append((POS_RANK.get(raw, 9),
                           int(grp.group(1)) if grp else 999,
                           int(sub.group(1)) if sub else 999, d))
# Primary sense = first group, first subsense, of the dominant POS: a deterministic, model-free
# heuristic (Wiktionary lists the basic sense first). The embedder later refines which gloss
# truly fits the prominent concept; for now this is the honest primary.
if senses:
    out.append(f"{subj}\tprimary_gloss\t{min(senses)[3]}")
print("\n".join(out))
PY
)"

if [ -z "$facts" ]; then
    log "no German Wiktionary entry for '$WORD' — nothing recorded"
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

log "ingested $count dbnary facts for '$WORD' (source=$SOURCE)"
