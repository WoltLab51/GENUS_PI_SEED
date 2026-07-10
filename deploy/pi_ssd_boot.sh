#!/usr/bin/env bash
set -Eeuo pipefail

# BOOT-VON-SSD-MIGRATION (Ronny, 2026-07-10: "ja beides, leg los") -- der Pi zieht komplett
# auf die SSD um, die SD-Karte wird invertiert (Not-Boot + naechtliches Backup-Medium).
#
# Ablauf, bewusst in dieser Reihenfolge (die Boot-Umstellung ist der ALLERLETZTE Schritt --
# bis dahin bleibt das System unveraendert SD-bootfaehig, jeder Abbruch ist folgenlos):
#   1. Preflight: richtiges Geraet (Intenso TX800), nicht gemountet, Root liegt auf der SD
#   2. Explizite Bestaetigung (Tippwort FORMATIEREN)
#   3. Partitionieren (MBR wie die SD: p1 FAT32 boot, p2 ext4 root) + formatieren
#   4. BELASTUNGSTEST als Go/No-Go: 3x1 GiB fdatasync-Schreiben + Rueckleseprobe + dmesg-Wache
#      (JMicron-USB-Bridges koennen unter Dauerlast zicken -- das pruefen wir JETZT, nicht
#      beim ersten naechtlichen Lerner-Lauf)
#   5. Klon: GENUS pausiert + Bot gestoppt -> rsync (2 Paesse) -> Ledger zusaetzlich per
#      sqlite-Backup-API (transaktions-konsistent) -> Integritaets-Check DER KOPIE
#   6. SSD-Kopie bootfaehig machen: PARTUUIDs in cmdline.txt + fstab, SSD-Swapfile (2. Stufe
#      hinter zRAM), SD-User-Mount-Zeile (fuers naechtliche Backup ohne sudo)
#   7. EEPROM-Bootreihenfolge 0xf14 (USB zuerst, SD-Fallback) -- erst NACH allen Pruefungen
#
# Muss als root laufen (sudo bash deploy/pi_ssd_boot.sh). Idempotent bis Schritt 3 (danach
# ist die SSD partitioniert; ein zweiter Lauf formatiert nach erneuter Bestaetigung neu).

GENUS_USER="${GENUS_USER:-ronny}"
GENUS_HOME="$(getent passwd "$GENUS_USER" | cut -d: -f6)"
REPO_DIR="${GENUS_REPO_DIR:-$GENUS_HOME/GENUS_PI_SEED}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
SSD="${GENUS_SSD_DEV:-/dev/sda}"
BOOT_MNT=/mnt/ssd-boot
ROOT_MNT=/mnt/ssd-root
SWAP_GROESSE_MB=4096

log() { printf '[SSD] %s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fehler() { printf '[SSD] FEHLER: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fehler "bitte mit sudo ausführen"

# --- 1. Preflight ---------------------------------------------------------------------
[ -b "$SSD" ] || fehler "$SSD existiert nicht"
MODELL="$(lsblk -ndo MODEL "$SSD" | tr -d ' ')"
case "$MODELL" in
    *TX800*|*Intenso*) ;;
    *) fehler "$SSD meldet Modell '$MODELL', erwartet Intenso TX800 -- falsches Geraet? (Override: GENUS_SSD_DEV)" ;;
esac
ROOT_QUELLE="$(findmnt -no SOURCE /)"
case "$ROOT_QUELLE" in
    /dev/mmcblk0*) ;;
    *) fehler "Root liegt auf $ROOT_QUELLE, nicht auf der SD-Karte -- laeuft der Pi schon von der SSD?" ;;
esac
if lsblk -no MOUNTPOINT "$SSD" | grep -q .; then
    fehler "$SSD hat gemountete Partitionen -- bitte erst aushaengen"
fi
SD_BOOT_PARTUUID="$(lsblk -no PARTUUID "$(findmnt -no SOURCE /boot/firmware)")"
SD_ROOT_PARTUUID="$(lsblk -no PARTUUID "$ROOT_QUELLE")"
log "Preflight OK: $SSD ($MODELL, $(lsblk -ndo SIZE "$SSD")), System auf SD ($SD_ROOT_PARTUUID)"

# --- 2. Bestaetigung ------------------------------------------------------------------
echo
echo "  ACHTUNG: $SSD wird KOMPLETT GELOESCHT und neu partitioniert."
echo "  Danach: Belastungstest -> Klon des laufenden Systems -> Boot von SSD (SD = Fallback)."
echo
read -r -p "  Zum Bestaetigen FORMATIEREN eintippen: " ANTWORT
[ "$ANTWORT" = "FORMATIEREN" ] || fehler "abgebrochen (nichts veraendert)"

# --- 3. Partitionieren + Formatieren --------------------------------------------------
log "partitioniere $SSD (MBR: 512M FAT32 + Rest ext4)"
wipefs -a "$SSD" >/dev/null
parted -s "$SSD" mklabel msdos \
    mkpart primary fat32 4MiB 516MiB \
    mkpart primary ext4 516MiB 100% \
    set 1 lba on
udevadm settle
mkfs.vfat -F 32 -n bootfs "${SSD}1" >/dev/null
mkfs.ext4 -q -F -L rootfs "${SSD}2"
udevadm settle
DISK_ID="$(lsblk -no PARTUUID "${SSD}2" | sed 's/-02$//')"
[ -n "$DISK_ID" ] || fehler "keine PARTUUID lesbar"
log "formatiert: PARTUUIDs ${DISK_ID}-01 / ${DISK_ID}-02"

mkdir -p "$BOOT_MNT" "$ROOT_MNT"
mount "${SSD}2" "$ROOT_MNT"
mount "${SSD}1" "$BOOT_MNT"
trap 'umount -l "$BOOT_MNT" "$ROOT_MNT" 2>/dev/null || true' EXIT

# --- 4. Belastungstest (Go/No-Go) -----------------------------------------------------
log "Belastungstest: 3x1 GiB schreiben (fdatasync) + Ruecklesen + dmesg-Wache"
DMESG_MARKE="$(dmesg | wc -l)"
for i in 1 2 3; do
    dd if=/dev/zero of="$ROOT_MNT/belastung.$i" bs=64M count=16 conv=fdatasync status=none \
        || fehler "Schreibtest $i fehlgeschlagen -- Boot-Umstellung NICHT durchgefuehrt"
done
# iflag=direct: wirklich von der SSD lesen, nicht aus dem Page-Cache (sonst prueft das nur RAM)
PRUEF_A="$(dd if="$ROOT_MNT/belastung.2" bs=64M iflag=direct status=none | md5sum | cut -d' ' -f1)"
PRUEF_B="$(dd if=/dev/zero bs=64M count=16 status=none | md5sum | cut -d' ' -f1)"
[ "$PRUEF_A" = "$PRUEF_B" ] || fehler "Rueckleseprobe abweichend -- SSD/Kabel nicht vertrauenswuerdig"
NEU="$(dmesg | tail -n +"$((DMESG_MARKE + 1))" | grep -icE "reset|error|timeout|offline" || true)"
[ "$NEU" -eq 0 ] || { dmesg | tail -n +"$((DMESG_MARKE + 1))" | grep -iE "reset|error|timeout|offline" | head -5; \
                      fehler "USB-Fehler unter Last ($NEU) -- Boot-Umstellung NICHT durchgefuehrt"; }
rm -f "$ROOT_MNT"/belastung.*
log "Belastungstest BESTANDEN (kein Reset, Ruecklesen exakt)"

# --- 5. Klon (Organismus pausiert) ----------------------------------------------------
log "pausiere GENUS + stoppe den Bot fuer einen konsistenten Klon"
runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" pause --reason "ssd-migration" || true
systemctl stop genus-telegram-bot.service 2>/dev/null || true
trap 'systemctl start genus-telegram-bot.service 2>/dev/null || true; \
      runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" resume >/dev/null 2>&1 || true; \
      umount -l "$BOOT_MNT" "$ROOT_MNT" 2>/dev/null || true' EXIT

log "rsync Pass 1 (laeuft einige Minuten)"
rsync -aHAXx --info=progress2 \
    --exclude=/proc/ --exclude=/sys/ --exclude=/dev/ --exclude=/run/ --exclude=/tmp/ \
    --exclude=/mnt/ --exclude=/media/ --exclude=/lost+found --exclude=/var/swap* \
    / "$ROOT_MNT/" | tail -1
log "rsync Pass 2 (Delta, still)"
rsync -aHAXx --delete \
    --exclude=/proc/ --exclude=/sys/ --exclude=/dev/ --exclude=/run/ --exclude=/tmp/ \
    --exclude=/mnt/ --exclude=/media/ --exclude=/lost+found --exclude=/var/swap* \
    / "$ROOT_MNT/" >/dev/null
rsync -aHAX --delete /boot/firmware/ "$BOOT_MNT/" >/dev/null

log "Ledger zusaetzlich transaktions-konsistent kopieren (sqlite backup API)"
SSD_DB="$ROOT_MNT/${DB_PATH#/}"
"$REPO_DIR/.venv/bin/python" - "$DB_PATH" "$SSD_DB" <<'PY'
import sqlite3, sys
quelle = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
ziel = sqlite3.connect(sys.argv[2])
quelle.backup(ziel)
ziel.close(); quelle.close()
print("[SSD] Ledger-Backup geschrieben")
PY

log "Integritaets-Check der SSD-KOPIE (nicht des Originals)"
runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$SSD_DB" "$REPO_DIR/.venv/bin/genus" integrity check \
    || fehler "Integritaet der Kopie verletzt -- Boot-Umstellung NICHT durchgefuehrt"
runuser -u "$GENUS_USER" -- env GENUS_DB_PATH="$SSD_DB" "$REPO_DIR/.venv/bin/genus" ledger verify \
    || fehler "Seal-Kette der Kopie verletzt -- Boot-Umstellung NICHT durchgefuehrt"

# --- 6. SSD-Kopie bootfaehig machen ----------------------------------------------------
log "PARTUUIDs eintragen (cmdline.txt + fstab)"
sed -i "s/root=PARTUUID=[^ ]*/root=PARTUUID=${DISK_ID}-02/" "$BOOT_MNT/cmdline.txt"
grep -q "PARTUUID=${DISK_ID}-02" "$BOOT_MNT/cmdline.txt" || fehler "cmdline.txt nicht angepasst"
sed -i "s|PARTUUID=${SD_BOOT_PARTUUID}|PARTUUID=${DISK_ID}-01|; s|PARTUUID=${SD_ROOT_PARTUUID}|PARTUUID=${DISK_ID}-02|" \
    "$ROOT_MNT/etc/fstab"

log "SSD-Swapfile (${SWAP_GROESSE_MB}M, 2. Stufe hinter zRAM) + SD-User-Mount vorbereiten"
fallocate -l "${SWAP_GROESSE_MB}M" "$ROOT_MNT/var/swap.genus"
chmod 600 "$ROOT_MNT/var/swap.genus"
mkswap "$ROOT_MNT/var/swap.genus" >/dev/null
{
    echo "/var/swap.genus  none  swap  sw,pri=10,nofail  0  0"
    echo "PARTUUID=${SD_ROOT_PARTUUID}  /mnt/sd  ext4  noauto,user,noatime,nofail  0  0"
} >> "$ROOT_MNT/etc/fstab"
mkdir -p "$ROOT_MNT/mnt/sd"
if [ -f "$ROOT_MNT/etc/dphys-swapfile" ]; then
    sed -i 's/^#\?CONF_SWAPSIZE=.*/CONF_SWAPSIZE=0/' "$ROOT_MNT/etc/dphys-swapfile"
    log "dphys-swapfile in der Kopie auf 0 gesetzt (zRAM + swap.genus uebernehmen)"
fi

sync
log "Klon vollstaendig und geprueft"

# --- 7. EEPROM: USB zuerst, SD als Fallback -------------------------------------------
log "setze Bootreihenfolge 0xf14 (USB -> SD -> wiederholen)"
TMP_CONF="$(mktemp)"
rpi-eeprom-config > "$TMP_CONF"
if grep -q '^BOOT_ORDER=' "$TMP_CONF"; then
    sed -i 's/^BOOT_ORDER=.*/BOOT_ORDER=0xf14/' "$TMP_CONF"
else
    echo "BOOT_ORDER=0xf14" >> "$TMP_CONF"
fi
rpi-eeprom-config --apply "$TMP_CONF"
rm -f "$TMP_CONF"

echo
log "FERTIG. Naechster Schritt:  sudo reboot"
log "Der Pi bootet dann von der SSD; die SD bleibt als Not-Boot im Slot."
log "(Bot + GENUS werden vom EXIT-trap dieses Skripts bis zum Reboot wieder gestartet --"
log " nach dem Reboot laeuft ohnehin alles frisch von der SSD.)"
