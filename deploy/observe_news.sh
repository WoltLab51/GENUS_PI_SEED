#!/usr/bin/env bash
set -Eeuo pipefail

# News membrane: current headlines from a public, no-auth RSS feed (Tagesschau).
#
# HTTP lives HERE, at the edge, never in the core (genus/ stays grep-empty of HTTP forever).
# Only the headline TEXT crosses, into a membrane-side buffer (~/.genus/news_puffer.json); the
# core READS that buffer, never the net. A failed fetch/parse leaves the old buffer untouched
# (it simply ages). The headlines are FOREIGN, unvetted text: GENUS displays them verbatim and
# never acts on them (observed content is data, never a command).

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
PUFFER="${GENUS_NEWS_PUFFER:-$GENUS_HOME/.genus/news_puffer.json}"
PY="$REPO_DIR/.venv/bin/python"
SOURCE="Tagesschau"
URL="https://www.tagesschau.de/index~rss2.xml"

mkdir -p "$LOG_DIR" "$(dirname "$PUFFER")"

log() {
    printf '[NEWS] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# Honor the global pause switch (genus pause): freeze autonomous activity.
if [ -f "$(dirname "$DB_PATH")/paused" ]; then log "paused — skipping"; exit 0; fi

# Fetch + parse at the edge: extract the top headlines' TEXT only (title + pubDate). Any
# failure (no network, bad payload) yields an empty string and leaves the buffer unchanged.
json="$(curl -sL --max-time 15 "$URL" 2>/dev/null | "$PY" -c '
import sys, json, time, xml.etree.ElementTree as ET
try:
    root = ET.fromstring(sys.stdin.read())
    schlagzeilen = []
    for it in root.findall(".//item")[:5]:
        titel = (it.findtext("title") or "").strip()
        zeit = (it.findtext("pubDate") or "").strip()
        if titel:
            schlagzeilen.append({"titel": titel, "zeit": zeit})
    if schlagzeilen:
        print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "quelle": "Tagesschau", "schlagzeilen": schlagzeilen},
                         ensure_ascii=False))
except Exception:
    pass' 2>/dev/null || true)"

if [ -z "$json" ]; then
    log "fetch or parse failed — buffer unchanged (it ages)"
    exit 0
fi

printf '%s\n' "$json" > "$PUFFER"
log "wrote headlines to buffer (source=$SOURCE)"
