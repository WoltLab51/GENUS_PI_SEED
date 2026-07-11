#!/usr/bin/env bash
set -Eeuo pipefail

# ZRAM-FEINSCHLIFF (2026-07-11, nach dem SSD-Umzug): zwei Handgriffe, beide im Geist der
# SD-Schonung und des 7B-Waage-Plans.
#
#   1. zRAM 2 GB -> 4 GB (zstd bleibt): mehr komprimierter RAM-Puffer = Luft fuer das warme
#      7B-Praezisionswaage-Experiment, ohne je eine Platte zu beruehren.
#   2. zram-WRITEBACK entsorgen: der (inaktive) Mechanismus haengt an loop0 -> /var/swap,
#      und die liegt auf der SD -- genau die Schreiblast, die der SSD-Umzug eliminiert hat.
#      Swap-Nutzung ist ohnehin 0 B; /var/swap loeschen gibt 2 GB SD-Platz frei.
#
# Provider ist der systemd-zram-generator (dpkg: systemd-zram-generator); die Konfig gehoert
# nach /etc/systemd/zram-generator.conf (Override-Pfad, bootfest). Idempotent; swapoff bei
# 0 B Nutzung ist augenblicklich und beruehrt Bot/GENUS nicht.

CONF=/etc/systemd/zram-generator.conf

log() { printf '[ZRAM] %s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fehler() { printf '[ZRAM] FEHLER: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fehler "bitte mit sudo ausfuehren"

log "vorher: $(swapon --show --noheadings | tr '\n' ' ' || true)"

# --- 1. Konfig schreiben (Override in /etc, bootfest) ----------------------------------
if [ -f "$CONF" ]; then cp -a "$CONF" "$CONF.vor-feinschliff"; fi
cat > "$CONF" <<'EOF'
# GENUS zRAM-Feinschliff (deploy/pi_zram_feinschliff.sh, 2026-07-11):
# 4 GB komprimierter Swap im RAM (zstd), KEIN writeback-device -- die SD wird geschont,
# die SSD bleibt dem Ledger. Bei 8 GB RAM ist min(ram/2, 4096) = 4096 MB.
[zram0]
zram-size = min(ram / 2, 4096)
compression-algorithm = zstd
swap-priority = 100
EOF
log "Konfig geschrieben: $CONF (4 GB, zstd, kein writeback)"

# --- 2. Writeback-Reste entsorgen -------------------------------------------------------
systemctl disable --now rpi-zram-writeback.service 2>/dev/null || true
systemctl disable --now rpi-zram-writeback.timer 2>/dev/null || true
if losetup /dev/loop0 >/dev/null 2>&1; then
    losetup -d /dev/loop0 2>/dev/null || true
    log "loop0 abgehaengt"
fi
if [ -f /var/swap ]; then
    rm -f /var/swap
    log "/var/swap geloescht (2 GB SD-Platz frei)"
fi

# --- 3. zram0 mit neuer Groesse neu aufsetzen -------------------------------------------
swapoff /dev/zram0 2>/dev/null || true
systemctl daemon-reload
systemctl restart systemd-zram-setup@zram0.service
systemctl restart dev-zram0.swap 2>/dev/null || swapon /dev/zram0 2>/dev/null || true

# --- 4. Verifikation ---------------------------------------------------------------------
GROESSE="$(cat /sys/block/zram0/disksize)"
[ "$GROESSE" = "4294967296" ] || fehler "zram0 ist $GROESSE Bytes, erwartet 4294967296 (4 GB)"
swapon --show | grep -q zram0 || fehler "zram0 ist nicht als Swap aktiv"
! losetup /dev/loop0 >/dev/null 2>&1 || fehler "loop0 haengt noch"
[ ! -f /var/swap ] || fehler "/var/swap existiert noch"

log "nachher: $(swapon --show --noheadings | tr '\n' ' ')"
log "FERTIG. zRAM = 4 GB (zstd, prio 100), kein Writeback, SD um 2 GB leichter."
log "Bootfest via $CONF -- ein Reboot ist NICHT noetig."
