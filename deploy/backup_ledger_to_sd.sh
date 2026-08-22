#!/usr/bin/env bash
set -Eeuo pipefail

# NAECHTLICHES LEDGER-BACKUP SSD -> SD (2026-07-11, Abschluss der Invertierung): das Ledger
# lebt jetzt auf der SSD; die SD wird ihr Sicherungs-Medium. EIN Schreibvorgang pro Nacht
# statt alle 5 Minuten -- so liegt der Organismus wieder auf ZWEI Medien, ohne die SD zu
# verschleissen.
#
# TRANSAKTIONS-KONSISTENT ohne Pause: die sqlite-Backup-API zieht einen sauberen Snapshot,
# waehrend GENUS weiterschreibt (kein Anfassen des laufenden Ledgers). VERIFIZIERT, bevor es
# zaehlt: das Backup wird erst per Integritaets- + Seal-Check geprueft und dann eingereiht --
# ein korrupter Dump loescht nie ein gutes altes. Behaelt die letzten N, raeumt aeltere ab.
#
# Sicher fuer den Cron: bricht ehrlich ab (Log + Exit != 0), fasst aber nie das Live-Ledger an.

umask 077

GENUS_HOME="${GENUS_HOME:-$HOME}"
REPO_DIR="${GENUS_REPO_DIR:-$GENUS_HOME/GENUS_PI_SEED}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
ANCHOR_DIR="${GENUS_ANCHOR_DIR:-$GENUS_HOME/.genus/anchors}"
BACKUP_DIR="${GENUS_SD_BACKUP:-$GENUS_HOME/genus-sd-backup}"
BACKUP_LOCK_FILE="$(dirname "$DB_PATH")/backup-ledger.lock"
KEEP="${GENUS_BACKUP_KEEP:-5}"
GENUS="$REPO_DIR/.venv/bin/genus"
PY="$REPO_DIR/.venv/bin/python"

log() { printf '[BACKUP] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fehler() { printf '[BACKUP] FEHLER: %s\n' "$*" >&2; exit 1; }

[ -f "$DB_PATH" ] || fehler "kein Ledger unter $DB_PATH (SSD nicht gemountet?) -- nichts gesichert"
command -v flock >/dev/null 2>&1 || fehler "flock fehlt -- Backup-Konkurrenz ist nicht sicher pruefbar"
LOCK_PARENT="$(realpath -e -- "$(dirname "$DB_PATH")")" \
    || fehler "Backup-Lock-Elternverzeichnis ist nicht kanonisch aufloesbar"
BACKUP_LOCK_FILE="$LOCK_PARENT/backup-ledger.lock"
[ -d "$LOCK_PARENT" ] && [ ! -L "$LOCK_PARENT" ] \
    && [ "$(stat -c %u "$LOCK_PARENT")" -eq "$(id -u)" ] \
    && [ "$(stat -c %a "$LOCK_PARENT")" = 700 ] \
    || fehler "Backup-Lock-Elternverzeichnis ist nicht operator-eigen/privat"
if [ -e "$BACKUP_LOCK_FILE" ] || [ -L "$BACKUP_LOCK_FILE" ]; then
    [ -f "$BACKUP_LOCK_FILE" ] && [ ! -L "$BACKUP_LOCK_FILE" ] \
        && [ "$(stat -c %u "$BACKUP_LOCK_FILE")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$BACKUP_LOCK_FILE")" = 600 ] \
        && [ "$(stat -c %h "$BACKUP_LOCK_FILE")" -eq 1 ] \
        || fehler "Backup-Lock ist nicht regulaer/operator-eigen/0600/einfach verlinkt"
fi
exec 8>>"$BACKUP_LOCK_FILE"
[ -f "$BACKUP_LOCK_FILE" ] && [ ! -L "$BACKUP_LOCK_FILE" ] \
    && [ "$(stat -c %u "$BACKUP_LOCK_FILE")" -eq "$(id -u)" ] \
    && [ "$(stat -c %a "$BACKUP_LOCK_FILE")" = 600 ] \
    && [ "$(stat -c %h "$BACKUP_LOCK_FILE")" -eq 1 ] \
    || fehler "Backup-Lock ist nicht regulaer/operator-eigen/0600/einfach verlinkt"
LOCK_PATH_IDENTITY="$(stat -c '%d:%i' "$BACKUP_LOCK_FILE")"
LOCK_FD_IDENTITY="$(stat -Lc '%d:%i' "/proc/$BASHPID/fd/8")"
[ "$LOCK_PATH_IDENTITY" = "$LOCK_FD_IDENTITY" ] \
    || fehler "Backup-Lock-FD ist nicht an den validierten Pfad gebunden"
flock -n 8 || fehler "ein anderer Ledger-Backup-/Runtimewechsel haelt den Backup-Lock"
[ "$(stat -c '%d:%i' "$BACKUP_LOCK_FILE")" = "$LOCK_FD_IDENTITY" ] \
    || fehler "Backup-Lock-Pfad wurde beim Sperren ersetzt"
mkdir -p "$BACKUP_DIR"

# SICHERHEIT: das Ziel muss auf einem ANDEREN Geraet liegen als das Ledger (SD != SSD) --
# sonst waere es kein echtes Backup, nur eine zweite Datei auf derselben Platte.
DEV_DB="$(stat -c %d "$DB_PATH")"
DEV_BK="$(stat -c %d "$BACKUP_DIR")"
[ "$DEV_DB" != "$DEV_BK" ] \
    || fehler "Backup-Ziel liegt auf demselben Geraet wie das Ledger -- kein echtes Backup (GENUS_SD_BACKUP setzen)"

TS="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/genus-$TS.sqlite3"
TMP="$DEST.partial"
trap 'rm -f "$TMP" "$TMP-wal" "$TMP-shm" 2>/dev/null || true' EXIT

log "Snapshot (sqlite backup API, kein Pause) -> $DEST"
"$PY" - "$DB_PATH" "$TMP" <<'PY'
import sqlite3, sys
q = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
z = sqlite3.connect(sys.argv[2])
q.backup(z)
z.close(); q.close()
PY
rm -f "$TMP-wal" "$TMP-shm"

log "verifiziere den Dump (Integritaet + Seal), bevor er zaehlt"
GENUS_DB_PATH="$TMP" "$GENUS" integrity check >/dev/null \
    || fehler "Backup-Integritaet verletzt -- verworfen (gute alte Backups bleiben)"
GENUS_DB_PATH="$TMP" "$GENUS" ledger verify >/dev/null \
    || fehler "Backup-Seal verletzt -- verworfen"
mv "$TMP" "$DEST"
trap - EXIT

# Anker mitsichern (klein, die Manipulations-Evidenz)
if [ -d "$ANCHOR_DIR" ]; then
    rsync -a --delete "$ANCHOR_DIR/" "$BACKUP_DIR/anchors/" && log "Anker mitgesichert"
fi

# Rotation: nur die letzten KEEP behalten
mapfile -t ALT < <(ls -1t "$BACKUP_DIR"/genus-*.sqlite3 2>/dev/null | tail -n +"$((KEEP + 1))")
if [ "${#ALT[@]}" -gt 0 ]; then
    rm -f "${ALT[@]}"
    log "abgeraeumt: ${#ALT[@]} aeltere(s) Backup(s)"
fi

ANZAHL="$(ls -1 "$BACKUP_DIR"/genus-*.sqlite3 2>/dev/null | wc -l)"
log "OK: $DEST ($(du -h "$DEST" | cut -f1)); $ANZAHL Backup(s) behalten in $BACKUP_DIR"
