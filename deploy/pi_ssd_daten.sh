#!/usr/bin/env bash
set -Eeuo pipefail

# DATEN-MIGRATION (der verlaessliche Weg, 2026-07-11 -- nach zwei Boot-von-SSD-Fehlschlaegen):
# ~/.genus (Ledger + Modelle + Logs + Anker -- die 5-Minuten-Schreiblast, der Organismus) zieht
# auf die SSD, das OS bleibt KOMPLETT auf der SD. KEINE Boot-Aenderung (kein EEPROM, kein
# cmdline) -- kann den Boot nicht bricken. Die SSD wird nur zur LAUFZEIT angefasst, wo Linux sie
# mit dem BOT-Quirk (usb-storage.quirks=152d:2320:u) bewiesen stabil faehrt.
#
# Der Clou: gemountet WIRD an ~/.genus SELBST -- damit bleiben ALLE Pfade wortgleich (die
# Modell-/venv-Pfade zeigen unveraendert nach ~/.genus, nichts an der Konfiguration aendert sich).
#
# DIVERGENZ-SCHUTZ: ist die SSD NICHT gemountet, bleibt der Mountpunkt ~/.genus auf mode 000/root
# -- so kann kein Cron/Bot bei fehlender SSD still ein leeres Zweit-Ledger auf die SD schreiben
# (fail-loud statt stiller Divergenz). nofail -> der Boot haengt nie an der SSD.
#
# Muss als root laufen (sudo). Idempotenz-Grenze: bis zum Format (danach ist die SSD neu).

GENUS_USER="${GENUS_USER:-ronny}"
GENUS_HOME="$(getent passwd "$GENUS_USER" | cut -d: -f6)"
REPO_DIR="${GENUS_REPO_DIR:-$GENUS_HOME/GENUS_PI_SEED}"
DOT="$GENUS_HOME/.genus"
DB_PATH="${GENUS_DB_PATH:-$DOT/genus.sqlite3}"
SSD="${GENUS_SSD_DEV:-/dev/sda}"
SETUP_MNT=/mnt/ssd-setup
CMDLINE="${GENUS_CMDLINE:-/boot/firmware/cmdline.txt}"

log() { printf '[DATEN] %s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fehler() { printf '[DATEN] FEHLER: %s\n' "$*" >&2; exit 1; }
gpause() { runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" "$@"; }

[ "$(id -u)" -eq 0 ] || fehler "bitte mit sudo ausfuehren"

# --- 1. Preflight ---------------------------------------------------------------------
[ -b "$SSD" ] || fehler "$SSD nicht da -- SSD eingesteckt?"
MODELL="$(lsblk -ndo MODEL "$SSD" | tr -d ' ')"
case "$MODELL" in *TX800*|*Intenso*) ;; *) fehler "$SSD ist '$MODELL', erwartet Intenso TX800" ;; esac
case "$(findmnt -no SOURCE /)" in /dev/mmcblk0*) ;; *) fehler "Root nicht auf der SD -- unerwartet" ;; esac
[ -f "$DB_PATH" ] || fehler "kein Ledger unter $DB_PATH -- nichts zu migrieren"
if findmnt "$DOT" >/dev/null 2>&1; then fehler "$DOT ist bereits ein Mountpunkt -- schon migriert?"; fi
grep -q "152d:2320:u" "$CMDLINE" || fehler "UAS-Quirk fehlt in $CMDLINE -- erst pi_ssd_uas_quirk.sh (sonst UAS-Absturz unter Last)"
if lsblk -no MOUNTPOINT "$SSD" | grep -q .; then
    log "haenge alte SSD-Partitionen aus"; umount "${SSD}"?* 2>/dev/null || true
fi
LEDGER_GB="$(du -sBG "$DOT" 2>/dev/null | cut -f1)"
log "Preflight OK: $SSD ($MODELL), Root auf SD, ~/.genus = ${LEDGER_GB:-?} zu migrieren, Quirk aktiv (BOT)"

# --- 2. Bestaetigung ------------------------------------------------------------------
echo
echo "  $SSD wird KOMPLETT GELOESCHT und als EINE ext4-Datenplatte fuer ~/.genus formatiert."
echo "  OS + Boot bleiben unberuehrt auf der SD. Die alte ~/.genus bleibt als Fallback liegen."
echo
read -r -p "  Zum Bestaetigen FORMATIEREN eintippen: " A
[ "$A" = "FORMATIEREN" ] || fehler "abgebrochen (nichts veraendert)"

# --- 3. Partitionieren + Formatieren (eine ext4 ueber die ganze Platte) ---------------
log "formatiere $SSD -> eine ext4 'genusdata'"
wipefs -a "$SSD" >/dev/null
parted -s "$SSD" mklabel gpt mkpart genusdata ext4 0% 100%
udevadm settle
mkfs.ext4 -q -F -L genusdata "${SSD}1"
udevadm settle
PARTUUID="$(lsblk -no PARTUUID "${SSD}1")"
[ -n "$PARTUUID" ] || fehler "keine PARTUUID auf ${SSD}1"
mkdir -p "$SETUP_MNT"
mount "${SSD}1" "$SETUP_MNT"
trap 'umount -l "$SETUP_MNT" 2>/dev/null || true' EXIT
chown "$GENUS_USER:$GENUS_USER" "$SETUP_MNT"
log "formatiert (PARTUUID $PARTUUID), gemountet nach $SETUP_MNT"

# --- 4. Belastungstest (das Ledger ist heilig -- BOT ist bewiesen, aber wir pruefen) --
log "Belastungstest: 3x1 GiB (fdatasync) + direct-read + dmesg-Wache"
MARKE="$(dmesg | wc -l)"
for i in 1 2 3; do
    dd if=/dev/zero of="$SETUP_MNT/probe.$i" bs=64M count=16 conv=fdatasync status=none \
        || fehler "Schreib-Burst $i gescheitert -> Abbruch (SSD nicht vertrauenswuerdig)"
done
A="$(dd if="$SETUP_MNT/probe.2" bs=64M iflag=direct status=none | md5sum | cut -d' ' -f1)"
B="$(dd if=/dev/zero bs=64M count=16 status=none | md5sum | cut -d' ' -f1)"
[ "$A" = "$B" ] || fehler "Rueckleseprobe abweichend -> Abbruch"
NEU="$(dmesg | tail -n +"$((MARKE + 1))" | grep -icE "reset|error|timeout|offline|-71" || true)"
[ "$NEU" -eq 0 ] || { dmesg | tail -n +"$((MARKE + 1))" | grep -iE "reset|error|timeout|-71" | head -5; fehler "USB-Fehler unter Last ($NEU) -> Abbruch"; }
rm -f "$SETUP_MNT"/probe.*
log "Belastungstest BESTANDEN"

# --- 5. Migration (Organismus pausiert, transaktions-konsistent) ----------------------
log "pausiere GENUS + stoppe den Bot"
gpause pause --reason "daten-migration" || true
systemctl stop genus-telegram-bot.service 2>/dev/null || true
trap 'systemctl start genus-telegram-bot.service 2>/dev/null || true; \
      gpause resume >/dev/null 2>&1 || true; \
      umount -l "$SETUP_MNT" 2>/dev/null || true' EXIT

log "rsync ~/.genus -> SSD (Modelle inklusive, kann etwas dauern)"
rsync -aHAX --info=progress2 "$DOT/" "$SETUP_MNT/" | tail -1

log "Ledger transaktions-konsistent drueber (sqlite backup API) + WAL-Reste entfernen"
"$REPO_DIR/.venv/bin/python" - "$DB_PATH" "$SETUP_MNT/$(basename "$DB_PATH")" <<'PY'
import sqlite3, sys
q = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
z = sqlite3.connect(sys.argv[2]); q.backup(z); z.close(); q.close()
print("[DATEN] Ledger-Backup geschrieben")
PY
rm -f "$SETUP_MNT/$(basename "$DB_PATH")-wal" "$SETUP_MNT/$(basename "$DB_PATH")-shm"

log "Integritaets- + Seal-Check der SSD-KOPIE (nicht des Originals)"
KOPIE="$SETUP_MNT/$(basename "$DB_PATH")"
pruefe_kopie() { runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$KOPIE" "$REPO_DIR/.venv/bin/genus" "$@"; }
pruefe_kopie integrity check || fehler "Integritaet der Kopie verletzt -> Abbruch (Original unangetastet)"
pruefe_kopie ledger verify   || fehler "Seal-Kette der Kopie verletzt -> Abbruch"
sync
umount "$SETUP_MNT"

# --- 6. Einwechseln: ~/.genus wird der SSD-Mount (Divergenz-Schutz via 000-Boden) ------
SICHER="$DOT.sd-backup-$(date +%Y%m%d-%H%M%S)"
mv "$DOT" "$SICHER"
log "alte Daten als Fallback: $SICHER"
mkdir "$DOT"
chown root:root "$DOT"; chmod 000 "$DOT"   # geschlossen, solange die SSD NICHT gemountet ist
if ! grep -q "[[:space:]]$DOT[[:space:]]" /etc/fstab; then
    cp -a /etc/fstab "/etc/fstab.vor-genusdata"
    echo "PARTUUID=${PARTUUID}  ${DOT}  ext4  nofail,noatime,x-systemd.device-timeout=10s  0  2" >> /etc/fstab
fi
systemctl daemon-reload
mount "$DOT" || fehler "Mount von ~/.genus fehlgeschlagen"
findmnt "$DOT" >/dev/null || fehler "~/.genus ist nach dem Mount kein Mountpunkt"
chown "$GENUS_USER:$GENUS_USER" "$DOT"      # SSD-Wurzel dem Nutzer (Schreibrecht); 000-Boden liegt darunter
log "~/.genus ist jetzt die SSD ($(findmnt -no SOURCE "$DOT"))"

# --- 7. Verifikation am LIVE-Pfad + Neustart ------------------------------------------
runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" integrity check \
    || fehler "Live-Integritaet nach dem Umzug verletzt"
runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" ledger verify | tail -1
systemctl start genus-telegram-bot.service 2>/dev/null || true
gpause resume >/dev/null 2>&1 || true
trap - EXIT

echo
log "FERTIG. ~/.genus laeuft von der SSD, OS + Boot unberuehrt auf der SD."
log "Fallback (loeschbar, wenn alles laeuft):  $SICHER"
log "Gegenprobe nach Reboot:  findmnt $DOT   (muss ${SSD}1 zeigen)"
