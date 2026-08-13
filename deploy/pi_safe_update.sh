#!/usr/bin/env bash
set -Eeuo pipefail

# Bewusst manueller, konservativer Pi-Updateweg. Das Skript nimmt weder einen
# Feature-Branch an noch fuehrt es Migrationen, Merges oder unbeaufsichtigte Updates aus.

BRANCH="${GENUS_DEPLOY_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_HOME="${GENUS_HOME:-$HOME}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
BACKUP_DIR="${GENUS_SD_BACKUP:-$GENUS_HOME/genus-sd-backup}"
BACKUP_SCRIPT="${GENUS_UPDATE_BACKUP_SCRIPT:-$SCRIPT_DIR/backup_ledger_to_sd.sh}"
SUDO_BIN="${GENUS_UPDATE_SUDO-sudo}"
GIT_BIN="${GENUS_UPDATE_GIT:-git}"
SYSTEMCTL_BIN="${GENUS_UPDATE_SYSTEMCTL:-systemctl}"
DRY_RUN=0
UPDATED=0
PAUSED=0
DEPENDENCIES_CHANGED=0
PREVIOUS_COMMIT=""
NEW_COMMIT=""
MARKER=""
ACTIVE_SERVICES=()
SERVICES=(genus-learner.service genus-telegram-bot.service)

log() { printf '[SAFE-UPDATE] %s\n' "$*"; }
fail() { printf '[SAFE-UPDATE] FEHLER: %s\n' "$*" >&2; exit "${2:-1}"; }

usage() {
    cat <<'EOF'
Aufruf: ./deploy/pi_safe_update.sh [--dry-run]

Aktualisiert ausschliesslich den konfigurierten Deploy-Branch (Default: main),
nach verifiziertem Ledger- und Konfigurationsbackup. --dry-run schreibt nichts.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; fail "unbekannte Option: $arg" 64 ;;
    esac
done

run_systemctl_restart() {
    [ "$#" -gt 0 ] || return 0
    if [ -n "$SUDO_BIN" ]; then
        "$SUDO_BIN" "$SYSTEMCTL_BIN" restart "$@"
    else
        "$SYSTEMCTL_BIN" restart "$@"
    fi
}

resume_activity() {
    if [ "$PAUSED" -eq 1 ] && [ -x "$REPO_DIR/.venv/bin/genus" ]; then
        GENUS_DB_PATH="$DB_PATH" "$REPO_DIR/.venv/bin/genus" resume >/dev/null 2>&1 || true
        PAUSED=0
        log "autonome Aktivitaet wieder freigegeben"
    fi
}

cleanup() {
    [ -z "$MARKER" ] || rm -f -- "$MARKER"
    resume_activity
}
trap cleanup EXIT

remember_active_services() {
    local service
    ACTIVE_SERVICES=()
    command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1 || return 0
    for service in "${SERVICES[@]}"; do
        if "$SYSTEMCTL_BIN" is-active --quiet "$service"; then
            ACTIVE_SERVICES+=("$service")
        fi
    done
}

restart_active_services() {
    if [ "${#ACTIVE_SERVICES[@]}" -eq 0 ]; then
        log "keine aktive langlebige GENUS-Unit neu zu starten"
        return 0
    fi
    log "starte kontrolliert neu: ${ACTIVE_SERVICES[*]}"
    run_systemctl_restart "${ACTIVE_SERVICES[@]}"
}

healthcheck() {
    local service
    log "Healthcheck: doctor, Integritaet und Seal"
    GENUS_DB_PATH="$DB_PATH" .venv/bin/genus doctor
    GENUS_DB_PATH="$DB_PATH" .venv/bin/genus integrity check
    GENUS_DB_PATH="$DB_PATH" .venv/bin/genus ledger verify
    for service in "${ACTIVE_SERVICES[@]}"; do
        "$SYSTEMCTL_BIN" is-active --quiet "$service" \
            || { printf '[SAFE-UPDATE] Unit nicht aktiv: %s\n' "$service" >&2; return 1; }
    done
}

restore_dependencies() {
    [ "$DEPENDENCIES_CHANGED" -eq 1 ] || return 0
    log "stelle Abhaengigkeiten fuer den vorherigen Commit wieder her"
    .venv/bin/python -m pip install -e '.[dev]'
}

rollback() {
    local original_status="$1"
    trap - ERR
    log "Rollback auf $PREVIOUS_COMMIT"
    if ! "$GIT_BIN" reset --keep "$PREVIOUS_COMMIT"; then
        printf '[SAFE-UPDATE] FEHLER: automatischer Rollback nicht moeglich; Checkout nicht weiter anfassen\n' >&2
        return 72
    fi
    if ! restore_dependencies; then
        printf '[SAFE-UPDATE] FEHLER: Code ist zurueckgerollt, alte Abhaengigkeiten aber nicht wiederhergestellt\n' >&2
        return 72
    fi
    if ! restart_active_services; then
        printf '[SAFE-UPDATE] FEHLER: Code ist zurueckgerollt, Dienst-Neustart fehlgeschlagen\n' >&2
        return 72
    fi
    if ! healthcheck; then
        printf '[SAFE-UPDATE] FEHLER: vorheriger Commit wiederhergestellt, aber Healthcheck bleibt rot\n' >&2
        return 72
    fi
    log "Rollback erfolgreich; Ledger und Konfiguration wurden nicht zurueckgespielt oder veraendert"
    return "$original_status"
}

on_error() {
    local status="$1"
    local line="$2"
    trap - ERR
    printf '[SAFE-UPDATE] FEHLER: Schritt in Zeile %s scheiterte (Exit %s)\n' "$line" "$status" >&2
    if [ "$UPDATED" -eq 1 ]; then
        rollback "$status"
        exit $?
    fi
    exit "$status"
}
trap 'on_error $? $LINENO' ERR

copy_configuration_snapshot() {
    local target="$1"
    local source
    local copied=0
    local config_files=(
        core_id
        status_publish.enabled
        chat_word_learning.enabled
        remote_deuter.enabled
        coder.enabled
        github_models_token
        telegram_bot_token
        telegram_bot.env
    )

    install -d -m 700 "$target"
    for source in "${config_files[@]}"; do
        source="$(dirname "$DB_PATH")/$source"
        [ ! -e "$source" ] && continue
        [ -f "$source" ] && [ ! -L "$source" ] \
            || fail "Konfiguration ist keine regulaere Datei: $source" 66
        install -m 600 "$source" "$target/$(basename "$source")"
        copied=$((copied + 1))
    done
    [ "$copied" -gt 0 ] || fail "keine relevante Konfiguration zum Sichern gefunden" 66
    printf '%s\n' "$PREVIOUS_COMMIT" > "$target/previous-commit"
    printf '%s\n' "$BRANCH" > "$target/branch"
    chmod 600 "$target/previous-commit" "$target/branch"
}

create_verified_backup() {
    local latest_backup
    local stamp
    local config_target

    [ -x "$BACKUP_SCRIPT" ] || fail "Backup-Skript fehlt oder ist nicht ausfuehrbar: $BACKUP_SCRIPT" 66
    install -d -m 700 "$BACKUP_DIR"
    MARKER="$(mktemp "$BACKUP_DIR/.safe-update-marker.XXXXXX")"
    log "erstelle verifiziertes Ledger-Backup auf dem konfigurierten Zweitmedium"
    GENUS_REPO_DIR="$REPO_DIR" GENUS_DB_PATH="$DB_PATH" GENUS_SD_BACKUP="$BACKUP_DIR" \
        "$BACKUP_SCRIPT"
    latest_backup="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'genus-*.sqlite3' -newer "$MARKER" \
        -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"
    [ -n "$latest_backup" ] && [ -s "$latest_backup" ] \
        || fail "Backup-Skript lieferte kein neues, nicht-leeres Ledger-Backup" 66

    stamp="$(date -u +%Y%m%d-%H%M%S)"
    config_target="$BACKUP_DIR/update-config-$stamp-${PREVIOUS_COMMIT:0:12}"
    copy_configuration_snapshot "$config_target"
    printf '%s\n' "$latest_backup" > "$config_target/ledger-backup"
    chmod 600 "$config_target/ledger-backup"
    log "Backup bestaetigt: $latest_backup; Konfiguration: $config_target"
    rm -f -- "$MARKER"
    MARKER=""
}

cd "$REPO_DIR"
[ -d .git ] || fail "kein Git-Checkout: $REPO_DIR" 65
[ -f "$DB_PATH" ] || fail "produktives Ledger fehlt: $DB_PATH" 65
[ -x .venv/bin/python ] && [ -x .venv/bin/genus ] \
    || fail "produktive virtuelle Umgebung fehlt oder ist unvollstaendig: $REPO_DIR/.venv" 65

if [ -n "$("$GIT_BIN" status --porcelain=v1)" ]; then
    "$GIT_BIN" status --short >&2
    fail "Git-Arbeitsbaum ist veraendert; Update abgebrochen" 65
fi

current_branch="$("$GIT_BIN" branch --show-current)"
[ "$current_branch" = "$BRANCH" ] \
    || fail "erwarteter Deploy-Branch $BRANCH, gefunden: ${current_branch:-detached}" 65

PREVIOUS_COMMIT="$("$GIT_BIN" rev-parse HEAD)"
remote_line="$("$GIT_BIN" ls-remote --exit-code origin "refs/heads/$BRANCH")" \
    || fail "origin/$BRANCH ist nicht erreichbar" 69
remote_commit="${remote_line%%[[:space:]]*}"
[ -n "$remote_commit" ] || fail "origin/$BRANCH lieferte keine Commit-ID" 69

log "Repo: $REPO_DIR"
log "Branch: $BRANCH"
log "Aktuell: $PREVIOUS_COMMIT"
log "Remote:  $remote_commit"

if [ "$PREVIOUS_COMMIT" = "$remote_commit" ]; then
    log "bereits aktuell; nichts zu tun"
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY-RUN: wuerde Backup erstellen, Fast-Forward pruefen, testen, neu starten und Healthcheck ausfuehren"
    exit 0
fi

create_verified_backup
remember_active_services

log "pausiere autonome Aktivitaet"
GENUS_DB_PATH="$DB_PATH" .venv/bin/genus pause --reason "manual safe update"
PAUSED=1

log "lade origin/$BRANCH und akzeptiere ausschliesslich Fast-Forward"
"$GIT_BIN" fetch origin "$BRANCH"
NEW_COMMIT="$("$GIT_BIN" rev-parse "origin/$BRANCH")"
"$GIT_BIN" merge-base --is-ancestor "$PREVIOUS_COMMIT" "$NEW_COMMIT" \
    || fail "origin/$BRANCH ist kein Fast-Forward von $PREVIOUS_COMMIT" 70
"$GIT_BIN" merge --ff-only "$NEW_COMMIT"
UPDATED=1

if "$GIT_BIN" diff --quiet "$PREVIOUS_COMMIT" "$NEW_COMMIT" -- pyproject.toml requirements.txt; then
    log "Abhaengigkeitsdeklarationen unveraendert"
else
    diff_status=$?
    [ "$diff_status" -eq 1 ] || exit "$diff_status"
    DEPENDENCIES_CHANGED=1
    log "Abhaengigkeitsdeklarationen geaendert; aktualisiere bestehende .venv"
    .venv/bin/python -m pip install -e '.[dev]'
fi

log "fuehre hermetische Tests vor jedem Neustart aus"
env -u GENUS_DB_PATH -u GENUS_CORE_ID -u GENUS_PAUSE_FILE .venv/bin/python -m pytest -q

restart_active_services
healthcheck

printf '%s %s -> %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PREVIOUS_COMMIT" "$NEW_COMMIT" \
    > "$(dirname "$DB_PATH")/last_safe_update"
chmod 600 "$(dirname "$DB_PATH")/last_safe_update"
log "Update erfolgreich: $PREVIOUS_COMMIT -> $NEW_COMMIT"
