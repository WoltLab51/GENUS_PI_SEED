#!/usr/bin/env bash
set -Eeuo pipefail

# ZRAM-FEINSCHLIFF v2 (2026-07-11): auf dem VENDOR-WEG. Der erste Versuch schrieb den
# systemd-zram-generator direkt um -- aber auf Raspberry Pi OS verwaltet das Paket rpi-swap
# das zram (eigener Generator, /etc/rpi/swap.conf, BindsTo auf den /var/swap-Loop beim
# Hybrid-Mechanismus). Gegen das Vendor-Tooling zu arbeiten erzeugte genau den Fehler
# "Failed to configure write-back device". Lehre: konfigurieren, wo der Eigentuemer liest.
#
# Ziel unveraendert: zRAM 4 GB, KEIN Writeback auf die SD (Mechanism=zram statt auto/hybrid).
# Laut man rpi-swap brauchen Aenderungen einen REBOOT -- das Skript konfiguriert nur und
# raeumt die Reste von v1 auf; danach: sudo reboot (bzw. shutdown fuer den Kabel-Tausch).

CONF_D=/etc/rpi/swap.conf.d
ALT=/etc/systemd/zram-generator.conf

log() { printf '[ZRAM] %s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fehler() { printf '[ZRAM] FEHLER: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fehler "bitte mit sudo ausfuehren"
[ -d /etc/rpi ] || fehler "/etc/rpi fehlt -- kein rpi-swap-System?"

# --- 1. v1-Reste zuruecknehmen (mein direkter zram-generator-Eingriff) ------------------
if [ -f "$ALT.vor-feinschliff" ]; then
    mv "$ALT.vor-feinschliff" "$ALT"
    log "zram-generator.conf auf den Originalzustand zurueckgesetzt"
elif [ -f "$ALT" ] && grep -q "GENUS zRAM-Feinschliff" "$ALT"; then
    rm -f "$ALT"
    log "v1-Konfig entfernt"
fi

# --- 2. Der Vendor-Weg: rpi-swap-Drop-in (empfohlener Pfad laut swap.conf-Kopf) ---------
mkdir -p "$CONF_D"
cat > "$CONF_D/50-genus.conf" <<'EOF'
# GENUS zRAM-Feinschliff (deploy/pi_zram_feinschliff.sh v2, 2026-07-11):
# reines zram (KEIN Hybrid, kein Writeback-Loop auf die SD -- die wird geschont,
# die SSD gehoert dem Ledger), 4 GB komprimierter RAM-Swap.
[Main]
Mechanism=zram

[Zram]
FixedSizeMiB=4096
EOF
log "geschrieben: $CONF_D/50-genus.conf (Mechanism=zram, 4096 MiB)"

# --- 3. /var/swap bleibt geloescht (Mechanism=zram referenziert ihn nicht mehr) ---------
[ ! -f /var/swap ] && log "/var/swap ist weg (2 GB SD frei) -- bleibt so" || true

echo
log "FERTIG konfiguriert. Laut man rpi-swap greift das erst nach einem Neustart:"
log "  sudo reboot     (oder: sudo shutdown now, falls du dabei das Kabel tauschst)"
log "Erwartung danach: zram0 = 4 GB (prio hoch), kein loop0, kein /var/swap."
