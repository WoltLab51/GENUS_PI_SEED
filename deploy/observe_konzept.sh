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
    wd_get "$API?action=wbsearchentities&search=$enc&language=$SEARCH_LANG&type=item&limit=7&format=json" "$TMP/search.json"
    # Disambiguation: among the candidates, prefer the one whose canonical label EXACTLY
    # matches the word -- so "Mond"->Moon (not the fuzzy "Monat"), "Sonne"->Sun (not generic
    # "Stern"), "Blume"->the flower (not the botanist "Carl Ludwig Blume"). Fall back to the
    # top hit for words whose Wikidata label differs from the common term (Hund->"Haushund").
    QID="$(SEED="$SEED" "$REPO_DIR/.venv/bin/python" - "$TMP/search.json" <<'PY'
import json, os, sys
word = os.environ["SEED"].casefold()
try:
    hits = json.load(open(sys.argv[1])).get("search", [])
except Exception:
    hits = []
exact = [h["id"] for h in hits if h.get("label", "").casefold() == word]
print(exact[0] if exact else (hits[0]["id"] if hits else ""))
PY
)"
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

if [ -z "$facts" ]; then
    log "no labels/parents for $QID ('$SEED') — nothing recorded"
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
