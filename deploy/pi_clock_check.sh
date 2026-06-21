#!/usr/bin/env bash
set -Eeuo pipefail

# Probe the system clock's NTP synchronization and feed the result into GENUS as
# self-operation evidence. The probe lives here, in the membrane, not in the
# deterministic core: the core only records the ok/fail status it is handed.
# Without an RTC battery a power loss can bring the Pi up with a stale clock;
# this check turns that into visible material (a system.clock belief and, on a
# fresh drop to unsynchronized, one review-only proposal) instead of silent
# corruption of the timestamps that the temporal patterns depend on.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"

mkdir -p "$LOG_DIR"

log() {
    printf '[CLK] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

run_genus() {
    if [ "$(id -u)" -eq 0 ] && command -v runuser >/dev/null 2>&1; then
        runuser -u "$GENUS_USER" -- env \
            GENUS_DB_PATH="$DB_PATH" \
            GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    else
        env \
            GENUS_DB_PATH="$DB_PATH" \
            GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
            "$REPO_DIR/.venv/bin/genus" "$@"
    fi
}

detect_sync() {
    # Prefer timedatectl; fall back to the systemd-timesyncd marker file.
    if command -v timedatectl >/dev/null 2>&1; then
        timedatectl show -p NTPSynchronized --value 2>/dev/null
        return
    fi
    if [ -f /run/systemd/timesync/synchronized ]; then
        printf 'yes\n'
    else
        printf 'no\n'
    fi
}

synced="$(detect_sync)"
if [ "$synced" = "yes" ]; then
    log "clock synchronized"
    run_genus operation clock-check --status ok --detail "ntp synchronized" >/dev/null
else
    log "clock not synchronized (synced=${synced:-unknown})"
    run_genus operation clock-check --status fail --detail "ntp not synchronized" >/dev/null
fi
