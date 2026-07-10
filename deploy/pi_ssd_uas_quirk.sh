#!/usr/bin/env bash
set -Eeuo pipefail

# UAS-QUIRK + LAST-PROBE (Ronny, SSD-Migration 2026-07-10): die JMicron-Bridge 152d:2320 flog
# unter der ersten Schreiblast (mkfs.ext4-Journal) komplett vom USB-Bus (error -71) -- das
# Lehrbuch-Muster einer UAS-Instabilitaet, nicht eines Stromproblems (die Pi-5-V-Schiene stand
# bei 5,11 V). Dieses Skript zwingt die Bridge auf das robuste BOT-Protokoll und BEWEIST dann,
# ob die SSD unter Last durchhaelt -- bevor die eigentliche Migration nochmal laeuft.
#
# ZWEI-PHASEN, idempotent (beide Aufrufe mit sudo, Reboot dazwischen):
#   Lauf 1 (Quirk fehlt):  traegt usb-storage.quirks=152d:2320:u in cmdline.txt ein -> "sudo reboot"
#   Lauf 2 (Quirk aktiv):  prueft, dass der Treiber jetzt usb-storage ist, und faehrt die
#                          LAST-PROBE (mkfs.ext4 + 3x1 GiB fdatasync + direct-read + dmesg-Wache)
#                          -> GO (dann die Migration erneut) oder NO-GO (dann aktiver USB-Hub).

SSD="${GENUS_SSD_DEV:-/dev/sda}"
CMDLINE="${GENUS_CMDLINE:-/boot/firmware/cmdline.txt}"
QUIRK="usb-storage.quirks=152d:2320:u"
PROBE_MNT=/mnt/ssd-probe

log() { printf '[QUIRK] %s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fehler() { printf '[QUIRK] FEHLER: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fehler "bitte mit sudo ausfuehren"
[ -f "$CMDLINE" ] || fehler "$CMDLINE nicht gefunden"

# --- Phase 1: Quirk setzen (falls fehlt) ----------------------------------------------
if ! grep -q "152d:2320:u" "$CMDLINE"; then
    cp -a "$CMDLINE" "$CMDLINE.vor-uas-quirk"
    sed -i "1 s|\$| ${QUIRK}|" "$CMDLINE"   # cmdline.txt ist EINE Zeile -> anhaengen
    grep -q "152d:2320:u" "$CMDLINE" || fehler "Quirk nicht eingetragen"
    log "Quirk eingetragen (Backup: $CMDLINE.vor-uas-quirk)"
    echo
    log "JETZT:  sudo reboot   -- danach dieses Skript ERNEUT mit sudo (dann folgt die Last-Probe)."
    exit 0
fi

# --- Phase 2: verifizieren + Last-Probe -----------------------------------------------
log "Quirk ist in cmdline.txt aktiv"
[ -b "$SSD" ] || fehler "$SSD nicht da -- SSD eingesteckt?"
TREIBER="$(lsusb -t 2>/dev/null | grep -iE "Mass Storage|152d" | grep -oE "Driver=[a-z-]+" | head -1)"
log "SSD-Treiber jetzt: ${TREIBER:-unbekannt}"
case "$TREIBER" in
    *usb-storage*) log "BOT aktiv -- gut, das ist der Sinn des Quirks" ;;
    *uas*) fehler "Treiber ist noch UAS -- Quirk nicht wirksam (Reboot gemacht? cmdline korrekt?)" ;;
    *) log "Treiber unklar, fahre die Probe trotzdem (der Test ist das Urteil)" ;;
esac
if lsblk -no MOUNTPOINT "$SSD" | grep -q .; then fehler "$SSD ist gemountet -- bitte aushaengen"; fi

log "LAST-PROBE auf ${SSD}2 -- genau die Operation, die vorhin starb (mkfs.ext4 + 3x1 GiB)"
mkfs.ext4 -q -F -L probe "${SSD}2" || fehler "mkfs.ext4 erneut gescheitert -> NO-GO (kein UAS-Fix; aktiver Hub noetig)"
mkdir -p "$PROBE_MNT"
mount "${SSD}2" "$PROBE_MNT"
trap 'umount -l "$PROBE_MNT" 2>/dev/null || true' EXIT

DMESG_MARKE="$(dmesg | wc -l)"
for i in 1 2 3; do
    dd if=/dev/zero of="$PROBE_MNT/last.$i" bs=64M count=16 conv=fdatasync status=none \
        || fehler "Schreib-Burst $i gescheitert -> NO-GO (aktiver USB-Hub noetig)"
    log "Burst $i/3 (1 GiB, fdatasync) durch"
done
A="$(dd if="$PROBE_MNT/last.2" bs=64M iflag=direct status=none | md5sum | cut -d' ' -f1)"
B="$(dd if=/dev/zero bs=64M count=16 status=none | md5sum | cut -d' ' -f1)"
[ "$A" = "$B" ] || fehler "Rueckleseprobe abweichend -> NO-GO"
NEU="$(dmesg | tail -n +"$((DMESG_MARKE + 1))" | grep -icE "reset|error|timeout|offline|-71" || true)"
if [ "$NEU" -ne 0 ]; then
    dmesg | tail -n +"$((DMESG_MARKE + 1))" | grep -iE "reset|error|timeout|offline|-71" | head -5
    fehler "USB-Fehler unter Last ($NEU) -> NO-GO (aktiver USB-Hub noetig)"
fi
rm -f "$PROBE_MNT"/last.*
umount "$PROBE_MNT"; trap - EXIT

echo
log "GO. Die SSD haelt unter Last durch (kein Reset, Ruecklesen exakt) -- der Quirk wirkt."
log "Naechster Schritt:  sudo bash deploy/pi_ssd_boot.sh   (die Migration, jetzt mit stabiler SSD)."
