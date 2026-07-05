#!/usr/bin/env bash
set -Eeuo pipefail

# Der HERZSCHLAG der Besinnung (Ronny 2026-07-05: „verdrahte den autonomen Herzschlag, rein
# reflektierend"). GENUS tickt in regelmäßigen Abständen SEINEN eigenen Geist: es liest sein
# Druck-Gefälle (genus/besinnung.py, REIN LESEND -- ohne den Schritt-Schalter, also keine
# Proposals, keine Außenwirkung, nichts ins Ledger) und schreibt seine gerichtete Besinnung in ein
# MEMBRAN-Tagebuch (~/.genus/besinnung.log -- Rohtext nur hier, wie der Tagespuffer;
# Ledger ≠ Memory). Rein reflektierend: der Geist bewegt sich, die Hand bleibt geparkt.
#
# Nur eine GEÄNDERTE Besinnung wird geloggt (Hash-Vergleich gegen die letzte) -- das Tagebuch
# zeigt die ENTWICKLUNG der Sorgen über die Zeit, nicht hundert identische Zeilen pro Tag.
# So wird GENUS' Innenleben beobachtbar, ohne dass es je von selbst nach außen spricht (das
# -- die proaktiven Einwürfe -- bleibt Ronnys eigene, spätere Entscheidung).

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG="$(dirname "$DB_PATH")/besinnung.log"
LAST="$(dirname "$DB_PATH")/besinnung.last"

log() { printf '[HERZSCHLAG] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Honor the global pause switch (genus pause): freeze autonomous activity.
if [ -f "$(dirname "$DB_PATH")/paused" ]; then log "paused — skipping"; exit 0; fi

# rein LESEND: genus besinnung ohne den Schritt-Schalter (kein Proposal, keine Außenwirkung)
reflexion="$(GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" besinnung 2>/dev/null \
    | sed 's/^\[BESINNUNG\] //')"
[ -n "$reflexion" ] || exit 0

hash="$(printf '%s' "$reflexion" | sha256sum | cut -d' ' -f1)"
if [ "$(cat "$LAST" 2>/dev/null || true)" = "$hash" ]; then
    exit 0                          # unverändert -> das Tagebuch zeigt nur Änderungen
fi
printf '%s' "$hash" > "$LAST"

{
    printf '=== %s ===\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s\n\n' "$reflexion"
} >> "$LOG"
# das Tagebuch bleibt gedeckelt (die jüngsten ~200 Blöcke à ~4 Zeilen)
if tail -n 800 "$LOG" > "$LOG.tmp" 2>/dev/null; then mv "$LOG.tmp" "$LOG"; else rm -f "$LOG.tmp"; fi
log "Besinnung geloggt (geändert)"
