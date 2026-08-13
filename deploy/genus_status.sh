#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_HOME="${GENUS_HOME:-$HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
BACKUP_DIR="${GENUS_SD_BACKUP:-$GENUS_HOME/genus-sd-backup}"
SERVICES=(genus-learner.service genus-telegram-bot.service genus-network-watchdog.timer)

field() { printf '%-12s %s\n' "$1" "$2"; }
unknown() { printf '%s' 'nicht verfuegbar'; }

cd "$REPO_DIR" 2>/dev/null || {
    printf '[STATUS] FEHLER: Repo nicht erreichbar: %s\n' "$REPO_DIR" >&2
    exit 66
}

field "Host" "$(hostname 2>/dev/null || unknown)"
field "Zeit" "$(date --iso-8601=seconds 2>/dev/null || date)"

if [ -x .venv/bin/python ]; then
    version="$(.venv/bin/python -c 'import genus; print(genus.__version__)' 2>/dev/null || true)"
else
    version=""
fi
field "GENUS" "${version:-$(unknown)}"

if [ -d .git ]; then
    branch="$(git branch --show-current 2>/dev/null || true)"
    commit="$(git rev-parse --short=12 HEAD 2>/dev/null || true)"
    if [ -n "$(git status --porcelain=v1 2>/dev/null || printf '?')" ]; then
        tree="VERAENDERT"
    else
        tree="sauber"
    fi
else
    branch=""
    commit=""
    tree="kein Git-Checkout"
fi
field "Branch" "${branch:-detached/unbekannt}"
field "Commit" "${commit:-$(unknown)}"
field "Git" "$tree"

if command -v systemctl >/dev/null 2>&1; then
    for service in "${SERVICES[@]}"; do
        state="$(systemctl is-active "$service" 2>/dev/null || true)"
        field "Dienst" "$service: ${state:-unbekannt}"
    done
else
    field "Dienst" "systemd nicht verfuegbar"
fi

cpu="$(LC_ALL=C top -bn1 2>/dev/null | awk -F',' '/^%?Cpu\(s\):/ {
    idle=$4; gsub(/[^0-9.]/, "", idle); printf "%.1f%% genutzt", 100-idle; exit
}' || true)"
field "CPU" "${cpu:-$(unknown)}"
ram="$(free -h 2>/dev/null | awk '/^Mem:/ {printf "%s / %s genutzt", $3, $2}' || true)"
field "RAM" "${ram:-$(unknown)}"
disk="$(df -h -- "$DB_PATH" 2>/dev/null | awk 'NR==2 {printf "%s frei (%s belegt)", $4, $5}' || true)"
field "Speicher" "${disk:-$(unknown)}"

if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
    temp_raw="$(< /sys/class/thermal/thermal_zone0/temp)"
    temp="$(awk -v value="$temp_raw" 'BEGIN {printf "%.1f C", value/1000}')"
else
    temp="$(unknown)"
fi
field "CPU-Temp" "$temp"

if [ -f "$DB_PATH" ]; then
    db_size="$(du -h -- "$DB_PATH" 2>/dev/null | awk '{print $1}' || true)"
    field "Datenbank" "vorhanden, ${db_size:-Groesse unbekannt}"
else
    field "Datenbank" "FEHLT: $DB_PATH"
fi

last_backup="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'genus-*.sqlite3' \
    -printf '%T@ %TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
field "Backup" "${last_backup:-keines feststellbar}"

printf '%s\n' 'Fehler (letzte 5):'
if command -v journalctl >/dev/null 2>&1; then
    errors="$(journalctl -p err \
        -u genus-learner.service -u genus-telegram-bot.service -u genus-network-watchdog.service \
        -n 5 --no-pager --output short-iso 2>/dev/null || true)"
else
    errors=""
fi
if [ -n "$errors" ]; then
    printf '%s\n' "$errors" | cut -c1-120 | sed 's/^/  /'
else
    printf '  keine im Journal feststellbar\n'
fi
