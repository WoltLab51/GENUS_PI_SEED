#!/usr/bin/env bash
set -Eeuo pipefail

# Knowledge acquisition membrane: a CONCEPT from Wikidata — language-neutral, multilingual.
#
# Wikidata *is* a language-neutral concept graph: Q-ids are concepts, subclass_of (P279)
# is the is_a hierarchy, and labels + aliases in every language are the lexemes. This
# fetches ONE concept (given a Q-id, or a word resolved to its top Q-id) and feeds the two
# layers: `<term>@<lang> -expresses-> Q` for each language (label + aliases) and
# `Q -is_a-> <parentQ>` for each subclass-of parent. The gap-loop then climbs the parents
# (they are Q-id objects not yet subjects). Small REST calls (wbgetclaims + wbgetentities),
# hop by hop — never the expensive transitive closure. No model. A failed fetch records
# nothing. Sense-clean by construction: the hierarchy lives on neutral concepts, not words.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

SEED="${1:-${GENUS_KONZEPT:-Q144}}"
LANGS="${GENUS_KONZEPT_LANGS:-de en fr}"
SEARCH_LANG="${GENUS_KONZEPT_SEARCH_LANG:-de}"
SOURCE="wikidata"
API="https://www.wikidata.org/w/api.php"
UA="GENUS-PI/0.1 (epistemic core research; ronnywolter87@gmail.com)"

mkdir -p "$LOG_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log() { printf '[KON] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

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

# Resolve a word to its top Q-id (a Q-id seed passes through unchanged). Top hit only --
# crude disambiguation, refine later (e.g. prefer the hit whose chain reaches a known root).
if printf '%s' "$SEED" | grep -Eq '^Q[0-9]+$'; then
    QID="$SEED"
else
    enc="$("$REPO_DIR/.venv/bin/python" -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$SEED")"
    wd_get "$API?action=wbsearchentities&search=$enc&language=$SEARCH_LANG&uselang=$SEARCH_LANG&type=item&limit=10&format=json" "$TMP/search.json"
    cand="$("$REPO_DIR/.venv/bin/python" -c 'import json,sys; print(" ".join(h["id"] for h in json.load(open(sys.argv[1])).get("search",[])))' "$TMP/search.json")"
    if [ -n "$cand" ]; then
        ids_pipe="$(printf '%s' "$cand" | tr ' ' '|')"
        wd_get "$API?action=wbgetentities&ids=$ids_pipe&props=sitelinks&format=json" "$TMP/sitelinks.json"
        # Resolve word -> concept FROM THE SOURCE, not by guessing. Two signals from the
        # search + sitelinks:
        #  - a LEXICAL match: the word must be the candidate's exact label (tier 0) or an
        #    exact alias (tier 1) -- this rejects prefix hits (Haus -> Haushund) and slang
        #    that only contains the word; no exact match -> record NOTHING (honest gap).
        #  - PROMINENCE: among equal-tier matches, the most Wikipedia sitelinks (the
        #    source's own notability) -- dog over the surname, Sun over generic star.
        # Reject non-concept hits (family/given names, disambiguation pages, articles).
        QID="$(SEED="$SEED" "$REPO_DIR/.venv/bin/python" - "$TMP/search.json" "$TMP/sitelinks.json" <<'PY'
import json, os, sys
word = os.environ["SEED"].casefold()
BAD = ("family name", "given name", "disambiguation", "scholarly article", "wikimedia",
       "surname", "familienname", "vorname", "begriffsklarung", "nachname")
search = json.load(open(sys.argv[1])).get("search", [])
ent = json.load(open(sys.argv[2])).get("entities", {})
def sitelinks(i): return len(ent.get(i, {}).get("sitelinks", {}))
def tier(h):
    if h.get("label", "").casefold() == word: return 0          # exact canonical label
    m = h.get("match", {})
    if m.get("text", "").casefold() == word and m.get("type") == "alias": return 1  # exact alias
    return 2                                                     # only a partial/prefix hit
pool = [h for h in search if not any(b in h.get("description", "").lower() for b in BAD)]
pool.sort(key=lambda h: (tier(h), -sitelinks(h["id"])))
print(pool[0]["id"] if pool and tier(pool[0]) < 2 else "")
PY
)"
    fi
fi

if [ -z "$QID" ]; then
    log "no concept found for '$SEED' — nothing recorded"
    exit 0
fi

langs_pipe="$(printf '%s' "$LANGS" | tr ' ' '|')"
wd_get "$API?action=wbgetentities&ids=$QID&props=labels|aliases&languages=$langs_pipe&format=json" "$TMP/labels.json"
wd_get "$API?action=wbgetclaims&entity=$QID&property=P279&format=json" "$TMP/p279.json"

# Emit (subject, predicate, object) triples: expresses (word@lang -> Q) + is_a (Q -> parentQ).
facts="$(QID="$QID" LANGS="$LANGS" "$REPO_DIR/.venv/bin/python" - "$TMP/labels.json" "$TMP/p279.json" <<'PY'
import json, os, sys
qid = os.environ["QID"]
langs = os.environ["LANGS"].split()
out, seen = [], set()
try:
    ent = json.load(open(sys.argv[1]))["entities"][qid]
    labels, aliases = ent.get("labels", {}), ent.get("aliases", {})
    def ok(t):
        return t and "\t" not in t and "@" not in t
    for lg in langs:
        canon = labels.get(lg, {}).get("value")
        # the ONE canonical label -> `label` (for readable display) AND `expresses`
        if ok(canon):
            out.append("%s@%s\tlabel\t%s" % (canon, lg, qid))
        # every form (label + aliases) -> `expresses`, so any synonym resolves to the concept
        forms = ([canon] if canon else []) + [a["value"] for a in aliases.get(lg, [])]
        for t in forms:
            if ok(t) and (t, lg) not in seen:
                seen.add((t, lg))
                out.append("%s@%s\texpresses\t%s" % (t, lg, qid))
except Exception:
    pass
try:
    for c in json.load(open(sys.argv[2]))["claims"].get("P279", []):
        ms = c.get("mainsnak", {})
        if ms.get("datavalue"):
            out.append("%s\tis_a\t%s" % (qid, ms["datavalue"]["value"]["id"]))
except Exception:
    pass
print("\n".join(out))
PY
)"

# The resolution itself is a fact from the source: the searched WORD expresses the concept
# we picked. Wikidata may not list that exact form as a label/alias, so record it explicitly
# (otherwise e.g. "Hund" would be lost when the label is "Haushund").
if ! printf '%s' "$SEED" | grep -Eq '^Q[0-9]+$'; then
    facts="$(printf '%s\n%s@%s\texpresses\t%s' "$facts" "$SEED" "$SEARCH_LANG" "$QID")"
fi

if [ -z "$facts" ]; then
    log "no concept resolved for '$SEED' — nothing recorded"
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

log "ingested $count relations for concept $QID ('$SEED', source=$SOURCE)"
