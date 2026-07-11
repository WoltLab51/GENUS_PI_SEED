#!/usr/bin/env bash
set -Eeuo pipefail

# HYBRID-BOOT (Plan B der SSD-Migration, 2026-07-11): BOOT von SD, ROOT von SSD.
#
# Befund: der EEPROM-Bootloader haengt beim USB-Boot an der JMicron-Bridge (LED durchgehend,
# Luefter Vollgas, kein Boot -- sein eigener USB-Treiber, unser Linux-Quirk gilt dort nicht).
# LINUX dagegen faehrt die Bridge mit dem BOT-Quirk bewiesen stabil (Last-Probe + kompletter
# Klon). Der Hybrid nutzt genau das: der Bootloader liest Kernel+initramfs von der SD (wie
# immer), die Kernel-cmdline zeigt root= auf die SSD -- ab Sekunde zwei laeuft alles von der
# SSD, die SD wird nur noch beim Kernel-Update beschrieben (~99 % der Schreiblast weg).
#
# Schritte (idempotent, Reihenfolge so, dass jeder Abbruch SD-bootfaehig bleibt):
#   1. Preflight: Root laeuft auf SD, SSD-Klon vorhanden (rootfs-Label, /etc/fstab da)
#   2. SSD-fstab: /boot/firmware kommt im Hybrid von der SD-Boot-Partition (Kernel-Updates
#      muessen dort landen, wo der Bootloader liest)
#   3. SD-cmdline: root= auf die SSD-PARTUUID (Backup: cmdline.txt.vor-hybrid; Quirk bleibt)
#   4. EEPROM: BOOT_ORDER=0xf41 (SD ZUERST -- der Bootloader probiert USB nur noch, wenn
#      gar keine SD steckt)
#
# NOT-RUECKWEG (falls der Hybrid nicht bootet, z.B. SSD ab): SD-Boot-Partition ist FAT32 --
# an jedem PC einlesbar; dort cmdline.txt.vor-hybrid zurueck nach cmdline.txt kopieren,
# Karte rein, bootet wieder komplett von SD.

SSD="${GENUS_SSD_DEV:-/dev/sda}"
CMDLINE="${GENUS_CMDLINE:-/boot/firmware/cmdline.txt}"
ROOT_MNT=/mnt/ssd-root

log() { printf '[HYBRID] %s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fehler() { printf '[HYBRID] FEHLER: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fehler "bitte mit sudo ausfuehren"

# --- 1. Preflight ----------------------------------------------------------------------
ROOT_QUELLE="$(findmnt -no SOURCE /)"
case "$ROOT_QUELLE" in
    /dev/mmcblk0*) ;;
    *) fehler "Root laeuft auf $ROOT_QUELLE -- der Hybrid wird von der SD aus eingerichtet" ;;
esac
[ -b "${SSD}2" ] || fehler "${SSD}2 nicht da -- SSD eingesteckt?"
SSD_PARTUUID="$(lsblk -no PARTUUID "${SSD}2")"
[ -n "$SSD_PARTUUID" ] || fehler "keine PARTUUID auf ${SSD}2"
SD_BOOT_PARTUUID="$(lsblk -no PARTUUID "$(findmnt -no SOURCE /boot/firmware)")"
grep -q "152d:2320:u" "$CMDLINE" || fehler "UAS-Quirk fehlt in $CMDLINE -- erst pi_ssd_uas_quirk.sh"

mkdir -p "$ROOT_MNT"
mount "${SSD}2" "$ROOT_MNT"
trap 'umount -l "$ROOT_MNT" 2>/dev/null || true' EXIT
[ -f "$ROOT_MNT/etc/fstab" ] || fehler "SSD traegt keinen Klon (/etc/fstab fehlt) -- erst pi_ssd_boot.sh bis zum Klon"
log "Preflight OK: SSD-Klon da (PARTUUID ${SSD_PARTUUID}), Boot bleibt auf SD (${SD_BOOT_PARTUUID})"

# --- 2. SSD-fstab: /boot/firmware von der SD -------------------------------------------
sed -i "s|^PARTUUID=[^ ]*  */boot/firmware|PARTUUID=${SD_BOOT_PARTUUID}  /boot/firmware|" "$ROOT_MNT/etc/fstab"
grep -q "PARTUUID=${SD_BOOT_PARTUUID}.*boot/firmware" "$ROOT_MNT/etc/fstab" \
    || fehler "SSD-fstab: /boot/firmware-Zeile nicht angepasst"
log "SSD-fstab: /boot/firmware kommt von der SD (Kernel-Updates landen beim Bootloader)"
sync
umount "$ROOT_MNT"; trap - EXIT

# --- 3. SD-cmdline: root= auf die SSD ---------------------------------------------------
if ! grep -q "root=PARTUUID=${SSD_PARTUUID}" "$CMDLINE"; then
    cp -a "$CMDLINE" "$CMDLINE.vor-hybrid"
    sed -i "s|root=PARTUUID=[^ ]*|root=PARTUUID=${SSD_PARTUUID}|" "$CMDLINE"
    grep -q "root=PARTUUID=${SSD_PARTUUID}" "$CMDLINE" || fehler "cmdline nicht angepasst"
    grep -q "rootwait" "$CMDLINE" || sed -i "1 s|\$| rootwait|" "$CMDLINE"
    log "SD-cmdline: root -> SSD (Backup: $CMDLINE.vor-hybrid)"
else
    log "SD-cmdline zeigt schon auf die SSD (idempotent)"
fi

# --- 4. EEPROM: SD zuerst (Bootloader laesst USB in Ruhe) -------------------------------
TMP_CONF="$(mktemp)"
rpi-eeprom-config > "$TMP_CONF"
if grep -q '^BOOT_ORDER=' "$TMP_CONF"; then
    sed -i 's/^BOOT_ORDER=.*/BOOT_ORDER=0xf41/' "$TMP_CONF"
else
    echo "BOOT_ORDER=0xf41" >> "$TMP_CONF"
fi
rpi-eeprom-config --apply "$TMP_CONF" >/dev/null
rm -f "$TMP_CONF"
log "EEPROM: BOOT_ORDER=0xf41 (SD zuerst; USB nur noch ohne SD)"

echo
log "FERTIG. Naechster Schritt:  sudo reboot"
log "Danach: / von der SSD, /boot/firmware von der SD, Bootloader beruehrt USB nie."
