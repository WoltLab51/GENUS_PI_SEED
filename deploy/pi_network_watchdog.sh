#!/usr/bin/env bash
set -Eeuo pipefail

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
FAIL_FILE="${GENUS_NETWORK_FAILURE_FILE:-$GENUS_HOME/.genus/network-watchdog.failures}"
TARGET="${GENUS_NETWORK_TARGET:-}"

mkdir -p "$LOG_DIR" "$(dirname "$FAIL_FILE")"

log() {
    printf '[NET] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

detect_target() {
    if [ -n "$TARGET" ]; then
        printf '%s\n' "$TARGET"
        return
    fi
    ip route | awk '/default/ { print $3; exit }'
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

# Supervisor role: keep the background vocabulary learner alive across crashes and reboots.
# The learner is a user-level, idle-priority daemon; if it is down and GENUS is not paused,
# (re)start it as the genus user in its OWN transient unit via systemd-run, so it survives
# this watchdog tick's exit. No extra privileged install needed -- the watchdog already runs
# here, so it is the natural keeper. Pause (genus pause) is respected.
ensure_learner() {
    local learner="$REPO_DIR/deploy/pi_learn.sh"
    if [ ! -x "$learner" ]; then return 0; fi
    if [ -f "$(dirname "$DB_PATH")/paused" ]; then return 0; fi
    if pgrep -f "deploy/pi_learn.sh" >/dev/null 2>&1; then return 0; fi
    if ! command -v systemd-run >/dev/null 2>&1; then return 0; fi
    log "learner down — starting it (idle priority, own transient unit)"
    systemd-run --quiet --collect \
        --uid="$GENUS_USER" --nice=19 \
        --property=CPUSchedulingPolicy=idle \
        --property=IOSchedulingClass=idle \
        --property="StandardOutput=append:$LOG_DIR/learn.log" \
        --property="StandardError=append:$LOG_DIR/learn.log" \
        --setenv=GENUS_USER="$GENUS_USER" \
        --setenv=GENUS_HOME="$GENUS_HOME" \
        --setenv=GENUS_REPO_DIR="$REPO_DIR" \
        --setenv=GENUS_DB_PATH="$DB_PATH" \
        --setenv=GENUS_LOG_DIR="$LOG_DIR" \
        --setenv=GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
        bash "$learner" || log "could not start learner"
}

# Also keep the Telegram bridge alive (only if configured). NORMAL priority -- it answers a human,
# so it should feel responsive, unlike the deliberately idle learner. A no-op unless BOTH the token
# file and the allow-list env file exist (so an un-set-up Pi does nothing). The allowed id(s) come
# from the env file, read with grep (no sourcing -- the file is never executed). Read-only
# companion; deliberately NOT gated on pause (it responds on demand, it is not autonomous work).
ensure_telegram_bot() {
    local bot="$REPO_DIR/deploy/telegram_bot.py"
    local token_file="$GENUS_HOME/.genus/telegram_bot_token"
    local env_file="$GENUS_HOME/.genus/telegram_bot.env"
    if [ ! -f "$bot" ] || [ ! -s "$token_file" ] || [ ! -f "$env_file" ]; then return 0; fi
    # Die dauerhaft installierte, gehärtete Unit ist die EINE Eigentümerin des Pollers. Der
    # frühere direkte systemd-run-Fallback konnte während Boot/Deploy neben ihr starten und
    # Telegram-HTTP-409 erzeugen. Existiert die Unit, startet der Watchdog ausschließlich sie.
    if systemctl cat genus-telegram-bot.service >/dev/null 2>&1; then
        if systemctl is-active --quiet genus-telegram-bot.service; then return 0; fi
        log "telegram bridge down — starting installed service"
        systemctl start genus-telegram-bot.service || log "could not start telegram bridge service"
        return 0
    fi
    if pgrep -f "deploy/telegram_bot.py" >/dev/null 2>&1; then return 0; fi
    if ! command -v systemd-run >/dev/null 2>&1; then return 0; fi
    local allowed_ids
    allowed_ids="$(grep -E '^GENUS_TELEGRAM_ALLOWED_IDS=' "$env_file" | tail -1 | cut -d= -f2-)"
    if [ -z "$allowed_ids" ]; then return 0; fi
    log "telegram bridge down — no installed unit; starting one hardened fallback"
    systemd-run --quiet --collect --unit=genus-telegram-bot-fallback.service \
        --uid="$GENUS_USER" \
        --property=Restart=on-failure \
        --property=RestartSec=15 \
        --property=MemoryHigh=2500M \
        --property=MemoryMax=3G \
        --property=MemorySwapMax=512M \
        --property=TasksMax=64 \
        --property=NoNewPrivileges=true \
        --property=PrivateTmp=true \
        --property=PrivateDevices=true \
        --property=ProtectSystem=full \
        --property="StandardOutput=append:$LOG_DIR/telegram_bot.log" \
        --property="StandardError=append:$LOG_DIR/telegram_bot.log" \
        --setenv=HOME="$GENUS_HOME" \
        --setenv=GENUS_DB_PATH="$DB_PATH" \
        --setenv=GENUS_LOG_DIR="$LOG_DIR" \
        --setenv=GENUS_TELEGRAM_TOKEN_FILE="$token_file" \
        --setenv=GENUS_TELEGRAM_LOCK_FILE="$GENUS_HOME/.genus/telegram_bot.lock" \
        --setenv=GENUS_TELEGRAM_STIMME=0 \
        --setenv=GENUS_TELEGRAM_ALLOWED_IDS="$allowed_ids" \
        "$REPO_DIR/.venv/bin/python" "$bot" || log "could not start telegram bridge"
}

json_field() {
    GENUS_JSON_INPUT="$(cat)" "$REPO_DIR/.venv/bin/python" -c '
import json
import os
import sys

field = sys.argv[1]
data = json.loads(os.environ["GENUS_JSON_INPUT"])
recovery = data.get("recovery") or {}
verdict = recovery.get("verdict") or {}
if field == "recovery_id":
    print(recovery.get("recovery_id") or "")
elif field == "decision":
    print(verdict.get("decision") or "")
else:
    print("")
' "$1"
}

restart_network_service() {
    if systemctl is-active --quiet NetworkManager; then
        systemctl restart NetworkManager
        printf 'NetworkManager\n'
    elif systemctl is-active --quiet dhcpcd; then
        systemctl restart dhcpcd
        printf 'dhcpcd\n'
    elif systemctl is-active --quiet systemd-networkd; then
        systemctl restart systemd-networkd
        printf 'systemd-networkd\n'
    else
        systemctl restart networking
        printf 'networking\n'
    fi
}

# Keep the background jobs alive every tick (before the network check, so they run regardless).
ensure_learner
ensure_telegram_bot

target="$(detect_target)"
if [ -z "$target" ]; then
    log "no default gateway found"
    target="default-gateway"
fi

if ping -c 1 -W 2 "$target" >/dev/null 2>&1; then
    printf '0\n' > "$FAIL_FILE"
    log "gateway ok target=$target"
    run_genus operation network-check \
        --status ok \
        --target "$target" \
        --failures 0 \
        --detail "gateway reachable" >/dev/null
    exit 0
fi

failures=0
if [ -f "$FAIL_FILE" ]; then
    failures="$(cat "$FAIL_FILE" 2>/dev/null || printf '0')"
fi
case "$failures" in
    ''|*[!0-9]*) failures=0 ;;
esac
failures=$((failures + 1))
printf '%s\n' "$failures" > "$FAIL_FILE"

# The reboot threshold is GENUS's own, self-calibrated from its outage history (governance's
# widest-gap derivation) -- ask it live instead of carrying a second, separately-typed copy of
# the number here. GENUS_NETWORK_REBOOT_THRESHOLD stays as an explicit manual override; a failed
# or pre-migration lookup falls back to the seed (3), same as the core does internally.
if [ -n "${GENUS_NETWORK_REBOOT_THRESHOLD:-}" ]; then
    reboot_threshold="$GENUS_NETWORK_REBOOT_THRESHOLD"
else
    reboot_threshold="$(run_genus governance reboot-threshold --value-only 2>/dev/null || true)"
    case "$reboot_threshold" in
        ''|*[!0-9]*) reboot_threshold=3 ;;
    esac
fi

if [ "$failures" -ge "$reboot_threshold" ]; then
    action="reboot"
else
    action="restart_network"
fi

log "gateway fail target=$target failures=$failures action=$action"
output="$(
    run_genus operation network-check \
        --status fail \
        --target "$target" \
        --failures "$failures" \
        --action "$action" \
        --detail "gateway unreachable" \
        --json
)"
decision="$(printf '%s' "$output" | json_field decision)"
recovery_id="$(printf '%s' "$output" | json_field recovery_id)"

if [ "$decision" != "allowed" ]; then
    log "recovery blocked action=$action recovery_id=${recovery_id:-none}"
    exit 0
fi

if [ "$action" = "restart_network" ]; then
    if service_name="$(restart_network_service)"; then
        log "network service restarted service=$service_name recovery_id=$recovery_id"
        run_genus operation recovery-result \
            --recovery-id "$recovery_id" \
            --result succeeded \
            --detail "restarted $service_name" >/dev/null
        exit 0
    fi
    log "network service restart failed recovery_id=$recovery_id"
    run_genus operation recovery-result \
        --recovery-id "$recovery_id" \
        --result failed \
        --detail "network service restart failed" >/dev/null
    exit 1
fi

log "reboot scheduled recovery_id=$recovery_id"
run_genus operation recovery-result \
    --recovery-id "$recovery_id" \
    --result scheduled \
    --detail "reboot scheduled after network failures" >/dev/null
systemctl reboot
