#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
if [ "$GENUS_USER" = "root" ] && [ "${GENUS_ALLOW_ROOT:-0}" != "1" ]; then
    echo "[NET] refusing GENUS_USER=root; the privileged watchdog needs a non-root core owner" >&2
    exit 1
fi
PASSWD_ENTRY="$(getent passwd "$GENUS_USER" || true)"
if [ -z "$PASSWD_ENTRY" ]; then
    echo "[NET] unknown GENUS_USER: $GENUS_USER" >&2
    exit 1
fi
GENUS_HOME="${GENUS_HOME:-$(printf '%s\n' "$PASSWD_ENTRY" | cut -d: -f6)}"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
PAUSE_FILE="$(dirname "$DB_PATH")/paused"
PRIVILEGED_DIR="/usr/local/libexec/genus"
FAIL_FILE="/var/lib/genus-network-watchdog/failures"
LAST_REBOOT_FILE="/var/lib/genus-network-watchdog/last-reboot-at"
TARGET="${GENUS_NETWORK_TARGET:-}"
RUN_GENUS_TIMEOUT_SECONDS=30
RUN_GENUS_OUTPUT_BYTES=65536
ROOT_MIN_REBOOT_FAILURES=3
ROOT_MAX_REBOOT_FAILURES=12
ROOT_MIN_REBOOT_INTERVAL_SECONDS=3600

as_genus_user() {
    if [ "$(id -u)" -eq 0 ] && [ "$(id -un)" != "$GENUS_USER" ]; then
        runuser -u "$GENUS_USER" -- "$@"
    else
        "$@"
    fi
}

read_user_control_file() {
    # Open user-controlled state without following symlinks or blocking on FIFOs/devices.
    # Python itself runs as GENUS_USER and timeout is an outer fail-safe for hostile filesystems.
    local mode="$1" path="$2"
    as_genus_user /usr/bin/timeout --signal=TERM --kill-after=1s 2s \
        /usr/bin/python3 - "$mode" "$path" <<'PY'
import os
import re
import stat
import sys

mode, path = sys.argv[1:]
try:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
except OSError:
    raise SystemExit(2)
try:
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        raise SystemExit(2)
    limit = 130 if mode == "core_id" else 4097
    with os.fdopen(descriptor, "rb", closefd=False) as handle:
        raw = handle.read(limit)
finally:
    os.close(descriptor)

if mode == "core_id":
    if len(raw) > 129:
        raise SystemExit(2)
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if re.fullmatch(rb"[A-Za-z0-9._:-]{1,128}", raw) is None:
        raise SystemExit(2)
    print(raw.decode("ascii"))
elif mode == "telegram_allowlist":
    if len(raw) > 4096:
        raise SystemExit(2)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise SystemExit(2)
    match = re.fullmatch(
        r"GENUS_TELEGRAM_ALLOWED_IDS=([0-9]{1,20})\n?",
        text,
    )
    if match is None:
        raise SystemExit(2)
    print(match.group(1))
else:
    raise SystemExit(2)
PY
}

# One-time upgrade path for legacy units that still execute this user-writable
# checkout as root. Install root-owned code and rewrite the unit, then stop this
# invocation; all later timer ticks start exclusively from /usr/local/libexec.
migrate_legacy_privileged_runtime() {
    if [ "$(id -u)" -ne 0 ]; then return 0; fi
    local current target helper
    current="$(readlink -f "${BASH_SOURCE[0]}")"
    target="$PRIVILEGED_DIR/pi_network_watchdog.sh"
    if [ "$current" = "$target" ]; then return 0; fi
    printf '[NET] migrating legacy user-writable root watchdog to %s\n' "$PRIVILEGED_DIR"
    /usr/bin/install -d -o root -g root -m 0755 "$PRIVILEGED_DIR"
    for helper in pi_network_watchdog.sh pi_install_network_watchdog.sh \
                  pi_install_learner.sh pi_install_telegram_bot.sh; do
        /usr/bin/install -o root -g root -m 0755 "$SCRIPT_DIR/$helper" "$PRIVILEGED_DIR/$helper"
    done
    env GENUS_USER="$GENUS_USER" GENUS_HOME="$GENUS_HOME" \
        GENUS_REPO_DIR="$REPO_DIR" GENUS_DB_PATH="$DB_PATH" \
        GENUS_LOG_DIR="$LOG_DIR" GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
        "$PRIVILEGED_DIR/pi_install_network_watchdog.sh"
    exit 0
}

# The sticky core id is the runtime source of truth. An older unit may still carry
# a stale Environment= value. Read it with the core owner's permissions so a
# user-controlled symlink can never make root disclose a privileged file.
CORE_ID_FILE="${GENUS_CORE_ID_FILE:-$(dirname "$DB_PATH")/core_id}"
if core_id="$(read_user_control_file core_id "$CORE_ID_FILE" 2>/dev/null)"; then
    GENUS_CORE_ID="$core_id"
    export GENUS_CORE_ID
fi

migrate_legacy_privileged_runtime

as_genus_user mkdir -p "$LOG_DIR"
/usr/bin/install -d -o root -g root -m 0700 "$(dirname "$FAIL_FILE")"

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
        /usr/bin/timeout --signal=TERM --kill-after=5s "${RUN_GENUS_TIMEOUT_SECONDS}s" \
            runuser -u "$GENUS_USER" -- env \
                GENUS_DB_PATH="$DB_PATH" \
                GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
                "$REPO_DIR/.venv/bin/genus" "$@" 2>&1 \
            | /usr/bin/head -c "$RUN_GENUS_OUTPUT_BYTES"
    else
        /usr/bin/timeout --signal=TERM --kill-after=5s "${RUN_GENUS_TIMEOUT_SECONDS}s" \
            env \
                GENUS_DB_PATH="$DB_PATH" \
                GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
                "$REPO_DIR/.venv/bin/genus" "$@" 2>&1 \
            | /usr/bin/head -c "$RUN_GENUS_OUTPUT_BYTES"
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
    if [ -f "$PAUSE_FILE" ]; then return 0; fi
    if systemctl cat genus-learner.service >/dev/null 2>&1; then
        local unit_user unit_env unit_stdout unit_stderr
        unit_user="$(systemctl show genus-learner.service -p User --value 2>/dev/null || true)"
        unit_env="$(systemctl show genus-learner.service -p Environment --value 2>/dev/null || true)"
        unit_stdout="$(
            systemctl show genus-learner.service -p StandardOutput --value 2>/dev/null || true
        )"
        unit_stderr="$(
            systemctl show genus-learner.service -p StandardError --value 2>/dev/null || true
        )"
        if [ "$unit_user" != "$GENUS_USER" ] \
           || ! grep -Fq "GENUS_USER=$GENUS_USER" <<<"$unit_env" \
           || ! grep -Fq "GENUS_DB_PATH=$DB_PATH" <<<"$unit_env" \
           || [ "$unit_stdout" != "journal" ] \
           || [ "$unit_stderr" != "journal" ]; then
            log "learner unit identity drift — reinstalling for user=$GENUS_USER db=$DB_PATH"
            if [ -f /root/.genus/genus.sqlite3 ]; then
                log "root scatter ledger detected at /root/.genus/genus.sqlite3 — left untouched for audit"
            fi
            env GENUS_USER="$GENUS_USER" GENUS_HOME="$GENUS_HOME" \
                GENUS_REPO_DIR="$REPO_DIR" GENUS_DB_PATH="$DB_PATH" \
                GENUS_LOG_DIR="$LOG_DIR" GENUS_CORE_ID="${GENUS_CORE_ID:-}" \
                "$PRIVILEGED_DIR/pi_install_learner.sh" \
                || log "could not repair learner unit identity"
            return 0
        fi
        if systemctl is-active --quiet genus-learner.service; then return 0; fi
        log "learner down — starting installed service"
        systemctl start genus-learner.service || log "could not start learner service"
        return 0
    fi
    if pgrep -f "deploy/pi_learn.sh" >/dev/null 2>&1; then return 0; fi
    if ! command -v systemd-run >/dev/null 2>&1; then return 0; fi
    log "learner down — starting it (idle priority, own transient unit)"
    systemd-run --quiet --collect \
        --uid="$GENUS_USER" --nice=19 \
        --property=CPUSchedulingPolicy=idle \
        --property=IOSchedulingClass=idle \
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
# file and the allow-list env file exist (so an un-set-up Pi does nothing). The allow-list is
# read as the GENUS user, capped at 4 KiB, and accepted only in one canonical form; it is never
# sourced or executed. Read-only
# companion; deliberately NOT gated on pause (it responds on demand, it is not autonomous work).
unit_environment_has_exact() {
    local environment="$1"
    local assignment="$2"
    case " $environment " in
        *" $assignment "*) return 0 ;;
        *) return 1 ;;
    esac
}

ensure_telegram_bot() {
    local bot="$REPO_DIR/deploy/telegram_bot.py"
    local token_file="$GENUS_HOME/.genus/telegram_bot_token"
    local env_file="$GENUS_HOME/.genus/telegram_bot.env"
    if [ ! -f "$bot" ] \
       || ! as_genus_user test -s "$token_file" \
       || ! as_genus_user test -f "$env_file"; then return 0; fi
    local allowed_ids
    if ! allowed_ids="$(
        read_user_control_file telegram_allowlist "$env_file" 2>/dev/null
    )"; then
        log "telegram allow-list malformed — refusing unit repair"
        return 0
    fi
    # Die dauerhaft installierte, gehärtete Unit ist die EINE Eigentümerin des Pollers. Der
    # frühere direkte systemd-run-Fallback konnte während Boot/Deploy neben ihr starten und
    # Telegram-HTTP-409 erzeugen. Existiert die Unit, startet der Watchdog ausschließlich sie.
    if systemctl cat genus-telegram-bot.service >/dev/null 2>&1; then
        local unit_user unit_env unit_env_files unit_stdout unit_stderr
        local unit_memory_high unit_memory_max unit_memory_swap_max unit_tasks_max unit_nnp
        unit_user="$(systemctl show genus-telegram-bot.service -p User --value 2>/dev/null || true)"
        unit_env="$(
            systemctl show genus-telegram-bot.service -p Environment --value 2>/dev/null || true
        )"
        unit_env_files="$(
            systemctl show genus-telegram-bot.service -p EnvironmentFiles --value 2>/dev/null || true
        )"
        unit_stdout="$(
            systemctl show genus-telegram-bot.service -p StandardOutput --value 2>/dev/null || true
        )"
        unit_stderr="$(
            systemctl show genus-telegram-bot.service -p StandardError --value 2>/dev/null || true
        )"
        unit_memory_high="$(
            systemctl show genus-telegram-bot.service -p MemoryHigh --value 2>/dev/null || true
        )"
        unit_memory_max="$(
            systemctl show genus-telegram-bot.service -p MemoryMax --value 2>/dev/null || true
        )"
        unit_memory_swap_max="$(
            systemctl show genus-telegram-bot.service -p MemorySwapMax --value 2>/dev/null || true
        )"
        unit_tasks_max="$(
            systemctl show genus-telegram-bot.service -p TasksMax --value 2>/dev/null || true
        )"
        unit_nnp="$(
            systemctl show genus-telegram-bot.service -p NoNewPrivileges --value 2>/dev/null || true
        )"
        if [ "$unit_user" != "$GENUS_USER" ] \
           || ! unit_environment_has_exact "$unit_env" "GENUS_DB_PATH=$DB_PATH" \
           || ! unit_environment_has_exact "$unit_env" "GENUS_TELEGRAM_ALLOWED_IDS=$allowed_ids" \
           || ! unit_environment_has_exact "$unit_env" "GENUS_TELEGRAM_STIMME=0" \
           || [ -n "$unit_env_files" ] \
           || [ "$unit_memory_high" != "2621440000" ] \
           || [ "$unit_memory_max" != "3221225472" ] \
           || [ "$unit_memory_swap_max" != "536870912" ] \
           || [ "$unit_tasks_max" != "64" ] \
           || [ "$unit_nnp" != "yes" ] \
           || [ "$unit_stdout" != "journal" ] \
           || [ "$unit_stderr" != "journal" ]; then
            local ids
            IFS=',' read -r -a ids <<<"$allowed_ids"
            log "telegram unit hardening drift — reinstalling bounded service"
            env GENUS_USER="$GENUS_USER" GENUS_HOME="$GENUS_HOME" \
                GENUS_REPO_DIR="$REPO_DIR" GENUS_DB_PATH="$DB_PATH" \
                GENUS_LOG_DIR="$LOG_DIR" \
                "$PRIVILEGED_DIR/pi_install_telegram_bot.sh" "${ids[@]}" \
                || log "could not repair telegram unit hardening"
            return 0
        fi
        if systemctl is-active --quiet genus-telegram-bot.service; then return 0; fi
        log "telegram bridge down — starting installed service"
        systemctl start genus-telegram-bot.service || log "could not start telegram bridge service"
        return 0
    fi
    if pgrep -f "deploy/telegram_bot.py" >/dev/null 2>&1; then return 0; fi
    if ! command -v systemd-run >/dev/null 2>&1; then return 0; fi
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
        --setenv=HOME="$GENUS_HOME" \
        --setenv=GENUS_DB_PATH="$DB_PATH" \
        --setenv=GENUS_LOG_DIR="$LOG_DIR" \
        --setenv=GENUS_TELEGRAM_TOKEN_FILE="$token_file" \
        --setenv=GENUS_TELEGRAM_LOCK_FILE="$GENUS_HOME/.genus/telegram_bot.lock" \
        --setenv=GENUS_TELEGRAM_STIMME=0 \
        --setenv=GENUS_CHAT_WORD_LEARNING=0 \
        --setenv=GENUS_TELEGRAM_ALLOWED_IDS="$allowed_ids" \
        "$REPO_DIR/.venv/bin/python" "$bot" || log "could not start telegram bridge"
}

json_field() {
    GENUS_JSON_INPUT="$(cat)" /usr/bin/python3 -c '
import json
import os
import sys

field = sys.argv[1]
data = json.loads(os.environ["GENUS_JSON_INPUT"])
recovery = data.get("recovery") or {}
verdict = recovery.get("verdict") or {}
if field == "recovery_id":
    print(str(recovery.get("recovery_id") or "")[:128])
elif field == "decision":
    decision = verdict.get("decision") or ""
    print(decision if decision in {"allowed", "blocked"} else "")
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

# A deploy/replay pause is a complete autonomous-write boundary.  The old code only gated the
# learner, then still recorded ``network.gateway`` below; that exact event raced a live replay.
# Exit before supervision, observation and recovery so the pause contract is behavioural, not
# merely a marker string somewhere in this file.  The installed Telegram unit remains available
# through systemd and continues to serve the human independently.
if [ -f "$PAUSE_FILE" ]; then
    log "paused — watchdog supervision, network observation, and recovery skipped"
    exit 0
fi

# Keep the background jobs alive every unpaused tick (before the network check).
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
fi
case "$reboot_threshold" in
    ''|*[!0-9]*) reboot_threshold="$ROOT_MIN_REBOOT_FAILURES" ;;
esac
if [ "$reboot_threshold" -lt "$ROOT_MIN_REBOOT_FAILURES" ]; then
    reboot_threshold="$ROOT_MIN_REBOOT_FAILURES"
elif [ "$reboot_threshold" -gt "$ROOT_MAX_REBOOT_FAILURES" ]; then
    reboot_threshold="$ROOT_MAX_REBOOT_FAILURES"
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

# GENUS may veto a recovery, but user-owned code can never widen root authority.
# Root independently requires a genuine ping failure, a bounded failure threshold,
# and a one-hour reboot cooldown kept in root-only state.
if [ "$action" = "reboot" ]; then
    now_epoch="$(date +%s)"
    last_reboot=0
    if [ -f "$LAST_REBOOT_FILE" ]; then
        last_reboot="$(cat "$LAST_REBOOT_FILE" 2>/dev/null || printf '0')"
    fi
    case "$last_reboot" in
        ''|*[!0-9]*) last_reboot=0 ;;
    esac
    if [ $((now_epoch - last_reboot)) -lt "$ROOT_MIN_REBOOT_INTERVAL_SECONDS" ]; then
        log "root safety veto action=reboot cooldown=${ROOT_MIN_REBOOT_INTERVAL_SECONDS}s"
        exit 0
    fi
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
printf '%s\n' "$(date +%s)" > "$LAST_REBOOT_FILE"
run_genus operation recovery-result \
    --recovery-id "$recovery_id" \
    --result scheduled \
    --detail "reboot scheduled after network failures" >/dev/null
systemctl reboot
