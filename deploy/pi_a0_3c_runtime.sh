#!/usr/bin/env bash
set -Eeuo pipefail

# A0.3c installs one versioned, private CPython/SQLite runtime and stages two
# package environments as a single manifest-bound activation unit.  It never
# replaces a distribution library. The published runtime never relies on
# LD_LIBRARY_PATH/LD_PRELOAD; it resolves libsqlite3 through its own RUNPATH.

PYTHON_VERSION="3.13.15"
PYTHON_ARCHIVE="Python-${PYTHON_VERSION}.tar.xz"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_ARCHIVE}"
PYTHON_SHA256="1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76"
SQLITE_VERSION="3.53.4"
SQLITE_NUMBER="3530400"
SQLITE_ARCHIVE="sqlite-autoconf-${SQLITE_NUMBER}.tar.gz"
SQLITE_URL="https://www.sqlite.org/2026/${SQLITE_ARCHIVE}"
SQLITE_SHA3_256="454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338"
SQLITE_SOURCE_ID="2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc"
PIP_VERSION="26.1.2"
SETUPTOOLS_VERSION="84.0.0"
PYPI_INDEX_URL="https://pypi.org/simple"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd -P)}"
GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
BACKUP_DIR="${GENUS_SD_BACKUP:-$GENUS_HOME/genus-sd-backup}"
BACKUP_SCRIPT="${GENUS_A03C_BACKUP_SCRIPT:-$SCRIPT_DIR/backup_ledger_to_sd.sh}"
RUNTIME_PREFIX="${GENUS_A03C_RUNTIME_PREFIX:-/opt/genus/runtime/cpython-${PYTHON_VERSION}-sqlite-${SQLITE_VERSION}}"
STATE_ROOT="${GENUS_A03C_STATE_ROOT:-$GENUS_HOME/.genus/runtime-a0.3c}"
SETS_ROOT="$STATE_ROOT/sets"
ACTIVE_LINK="$STATE_ROOT/active"
PREVIOUS_LINK="$STATE_ROOT/previous"
STAGED_LINK="$STATE_ROOT/staged"
DOWNLOAD_ROOT="$STATE_ROOT/downloads"
RECEIPT_ROOT="$STATE_ROOT/receipts"
LOCK_FILE="$STATE_ROOT/operator.lock"
ACTIVATION_JOURNAL="$STATE_ROOT/activation.pending"
ACTIVATION_CRON_SNAPSHOT="$STATE_ROOT/activation.crontab.original"
ACTIVATION_CRON_DISABLED="$STATE_ROOT/activation.crontab.disabled"
AUTOSTART_APPROVAL="$STATE_ROOT/runtime.start-authorized"
OPERATOR_REAUTH_TOKEN="$STATE_ROOT/operator.reauthorized"
CORE_POINTER="$REPO_DIR/.venv"
EMBED_POINTER="$GENUS_HOME/.genus/embed-venv"
RUNTIME_PARENT="$(dirname "$RUNTIME_PREFIX")"
RUNTIME_PENDING="${RUNTIME_PREFIX}.building"
RUNTIME_PUBLICATION="${RUNTIME_PREFIX}.publication.pending"
RUNTIME_INVENTORY_REL="share/genus/RUNTIME.inventory.json"
RUNTIME_INVENTORY="$RUNTIME_PREFIX/$RUNTIME_INVENTORY_REL"
SUDO_BIN="${GENUS_A03C_SUDO:-/usr/bin/sudo}"
SYSTEMCTL_BIN="${GENUS_A03C_SYSTEMCTL:-/usr/bin/systemctl}"
FUSER_BIN="${GENUS_A03C_FUSER:-/usr/bin/fuser}"
GIT_BIN="${GENUS_A03C_GIT:-/usr/bin/git}"
SYSTEM_PYTHON_BIN="/usr/bin/python3"
ROOT_ENV_BIN="/usr/bin/env"
ROOT_FIND_BIN="/usr/bin/find"
ROOT_INSTALL_BIN="/usr/bin/install"
ROOT_CP_BIN="/usr/bin/cp"
ROOT_CHOWN_BIN="/usr/bin/chown"
ROOT_CHMOD_BIN="/usr/bin/chmod"
ROOT_MV_BIN="/usr/bin/mv"
ROOT_TEST_BIN="/usr/bin/test"
ROOT_STAT_BIN="/usr/bin/stat"
ROOT_CMP_BIN="/usr/bin/cmp"
ROOT_SYNC_BIN="/usr/bin/sync"
ROOT_RM_BIN="/usr/bin/rm"
ROOT_RMDIR_BIN="/usr/bin/rmdir"
ROOT_SYSTEMD_RUN_BIN="/usr/bin/systemd-run"
ROOT_MKTEMP_BIN="/usr/bin/mktemp"
CURL_BIN="${GENUS_A03C_CURL:-curl}"
MAKE_BIN="${GENUS_A03C_MAKE:-make}"
TAR_BIN="${GENUS_A03C_TAR:-tar}"
OPENSSL_BIN="${GENUS_A03C_OPENSSL:-openssl}"
READELF_BIN="${GENUS_A03C_READELF:-readelf}"
APT_GET_BIN="${GENUS_A03C_APT_GET:-/usr/bin/apt-get}"
APT_CACHE_BIN="${GENUS_A03C_APT_CACHE:-apt-cache}"
DPKG_QUERY_BIN="${GENUS_A03C_DPKG_QUERY:-dpkg-query}"
CRONTAB_BIN="${GENUS_A03C_CRONTAB:-/usr/bin/crontab}"
SYSTEMD_GUARD_ROOT="${GENUS_A03C_SYSTEMD_GUARD_ROOT:-/etc/systemd/system}"
BOOT_GUARD_PATH="${GENUS_A03C_BOOT_GUARD_PATH:-/usr/local/libexec/genus-a0-3c-boot-guard}"
MODEL="${GENUS_EMBED_MODEL:-sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2}"
SERVICES=(genus-network-watchdog.timer genus-learner.service genus-telegram-bot.service genus-telegram-bot-fallback.service)
AUTOSTART_UNITS=(genus-network-watchdog.timer genus-network-watchdog.service genus-learner.service genus-telegram-bot.service genus-telegram-bot-fallback.service)
CRON_BEGIN="# BEGIN GENUS_PI_SEED"
CRON_END="# END GENUS_PI_SEED"
BOOTSTRAP_PACKAGES=(build-essential cmake ninja-build pkg-config ca-certificates curl xz-utils psmisc libssl-dev zlib1g-dev libbz2-dev libreadline-dev libffi-dev liblzma-dev libncurses-dev libgdbm-dev libgdbm-compat-dev libexpat1-dev uuid-dev tk-dev)

umask 077

PRIVILEGED_BOUNDARY_READY=0
OPERATOR_REAUTH_RECEIPT=""

# Ein errexit-Abbruch ohne eigene Meldung ist nicht diagnostizierbar: Der Lauf
# endet stumm, und aus dem Log laesst sich die Stelle nicht rekonstruieren (live
# belegt 2026-08-21 nach der Supply-Freigabe). set -E vererbt diesen Trap in
# Funktionen und Subshells; fail() bleibt unberuehrt, weil exit kein ERR ausloest.
trap 'genus_a03c_status=$?; { printf "[A0.3c] ABBRUCH: Zeile %s, Kommando <%s>, Status %s" "$LINENO" "$BASH_COMMAND" "$genus_a03c_status"; echo; } >&2' ERR

log() { printf '[A0.3c] %s\n' "$*"; }
fail() { printf '[A0.3c] FEHLER: %s\n' "$1" >&2; exit "${2:-1}"; }

usage() {
    cat <<'EOF'
Aufruf:
  ./deploy/pi_a0_3c_runtime.sh status [--json]
  ./deploy/pi_a0_3c_runtime.sh stage [EXPECTED_SUPPLY_SEAL]
  ./deploy/pi_a0_3c_runtime.sh verify [active|MANIFEST]
  ./deploy/pi_a0_3c_runtime.sh activate EXPECTED_COMMIT READINESS_MANIFEST [SET_MANIFEST]
  ./deploy/pi_a0_3c_runtime.sh rollback EXPECTED_COMMIT
  ./deploy/pi_a0_3c_runtime.sh reauthorize EXPECTED_OLD_COMMIT EXPECTED_NEW_COMMIT

stage/verify beruehren weder Dienste noch Produktdatenbank. activate und
rollback schalten core+embed ueber genau einen atomar ersetzten Selector.
EOF
}

require_command() { command -v "$1" >/dev/null 2>&1 || fail "Werkzeug fehlt: $1" 69; }

validate_root_owned_program() {
    local candidate="$1" expected="$2" label="$3" resolved uid mode
    [ "$candidate" = "$expected" ] \
        || fail "$label darf im Produktionsmodus nicht umgebogen werden" 77
    [[ "$candidate" = /* ]] && [ -x "$candidate" ] \
        || fail "$label ist kein absoluter ausfuehrbarer Systempfad" 77
    resolved="$(/usr/bin/readlink -f -- "$candidate" 2>/dev/null)" \
        || fail "$label ist nicht kanonisch aufloesbar" 77
    [[ "$resolved" = /usr/bin/* ]] && [ -f "$resolved" ] && [ ! -L "$resolved" ] \
        || fail "$label endet nicht in einem regulaeren /usr/bin-Programm" 77
    uid="$(/usr/bin/stat -Lc %u -- "$resolved")"
    mode="$(/usr/bin/stat -Lc %a -- "$resolved")"
    [ "$uid" -eq 0 ] && (( (8#$mode & 8#22) == 0 )) \
        || fail "$label ist nicht root-owned oder ist gruppen-/welt-schreibbar" 77
}

harden_privileged_boundary() {
    [ "$PRIVILEGED_BOUNDARY_READY" -eq 0 ] || return 0
    if [ "${GENUS_A03C_TEST_MODE:-0}" = 1 ] && [ "${GENUS_A03C_SOURCE_ONLY:-0}" = 1 ]; then
        PRIVILEGED_BOUNDARY_READY=1
        return 0
    fi
    [ "$RUNTIME_PREFIX" = "/opt/genus/runtime/cpython-${PYTHON_VERSION}-sqlite-${SQLITE_VERSION}" ] \
        || fail "privilegierter Runtime-Prefix darf im Produktionsmodus nicht umgebogen werden" 77
    [ "$SYSTEMD_GUARD_ROOT" = /etc/systemd/system ] \
        || fail "systemd Guard-Root darf im Produktionsmodus nicht umgebogen werden" 77
    [ "$BOOT_GUARD_PATH" = /usr/local/libexec/genus-a0-3c-boot-guard ] \
        || fail "Boot-Guard-Pfad darf im Produktionsmodus nicht umgebogen werden" 77
    validate_root_owned_program "$SUDO_BIN" /usr/bin/sudo sudo
    validate_root_owned_program "$SYSTEMCTL_BIN" /usr/bin/systemctl systemctl
    validate_root_owned_program "$FUSER_BIN" /usr/bin/fuser fuser
    validate_root_owned_program "$GIT_BIN" /usr/bin/git git
    validate_root_owned_program "$APT_GET_BIN" /usr/bin/apt-get apt-get
    validate_root_owned_program "$CRONTAB_BIN" /usr/bin/crontab crontab
    validate_root_owned_program "$SYSTEM_PYTHON_BIN" /usr/bin/python3 system-python
    validate_root_owned_program "$ROOT_ENV_BIN" /usr/bin/env env
    validate_root_owned_program "$ROOT_FIND_BIN" /usr/bin/find find
    validate_root_owned_program "$ROOT_INSTALL_BIN" /usr/bin/install install
    validate_root_owned_program "$ROOT_CP_BIN" /usr/bin/cp cp
    validate_root_owned_program "$ROOT_CHOWN_BIN" /usr/bin/chown chown
    validate_root_owned_program "$ROOT_CHMOD_BIN" /usr/bin/chmod chmod
    validate_root_owned_program "$ROOT_MV_BIN" /usr/bin/mv mv
    validate_root_owned_program "$ROOT_TEST_BIN" /usr/bin/test test
    validate_root_owned_program "$ROOT_STAT_BIN" /usr/bin/stat stat
    validate_root_owned_program "$ROOT_CMP_BIN" /usr/bin/cmp cmp
    validate_root_owned_program "$ROOT_SYNC_BIN" /usr/bin/sync sync
    validate_root_owned_program "$ROOT_RM_BIN" /usr/bin/rm rm
    validate_root_owned_program "$ROOT_RMDIR_BIN" /usr/bin/rmdir rmdir
    validate_root_owned_program "$ROOT_SYSTEMD_RUN_BIN" /usr/bin/systemd-run systemd-run
    validate_root_owned_program "$ROOT_MKTEMP_BIN" /usr/bin/mktemp mktemp
    PRIVILEGED_BOUNDARY_READY=1
}

as_root() {
    harden_privileged_boundary
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        [ -n "$SUDO_BIN" ] || fail "Root-Schritt noetig; GENUS_A03C_SUDO ist leer" 77
        "$SUDO_BIN" "$@"
    fi
}

systemctl_root() {
    harden_privileged_boundary
    if [ "$(id -u)" -eq 0 ]; then
        "$SYSTEMCTL_BIN" "$@"
    else
        "$SUDO_BIN" "$SYSTEMCTL_BIN" "$@"
    fi
}

sha256_file() { sha256sum "$1" | awk '{print $1}'; }

sha3_file() {
    "$OPENSSL_BIN" dgst -sha3-256 "$1" | awk '{print $NF}'
}

atomic_link() {
    local target="$1" link="$2" tmp
    tmp="${link}.tmp.$$.$RANDOM"
    ln -s -- "$target" "$tmp"
    mv -Tf -- "$tmp" "$link"
    sync -f "$link"
    sync -f "$(dirname "$link")"
}

fsync_dir() { sync -f "$1"; }

publication_fault_point() {
    local phase="$1" configured="${GENUS_A03C_TEST_PUBLICATION_FAULT_PHASE:-}"
    [ "$configured" = "$phase" ] || return 0
    [ "${GENUS_A03C_TEST_MODE:-0}" = 1 ] \
        || fail "Publication-Fault-Injection ist ausserhalb des Testmodus verboten" 70
    case "${GENUS_A03C_TEST_PUBLICATION_FAULT_KIND:-explicit-fail}" in
        explicit-fail) fail "injected publication failure at $phase" 96 ;;
        set-e) false ;;
        KILL) kill -KILL "$$" ;;
        *) fail "unbekannte Publication-Fault-Injection" 70 ;;
    esac
}

receipt_target() {
    local prefix="$1"
    printf '%s/%s-%s-%s-%s.json\n' "$RECEIPT_ROOT" "$prefix" \
        "$(date -u +%Y%m%dT%H%M%S%N)" "$$" "$RANDOM"
}

safe_manifest_id() {
    [[ "$1" =~ ^(legacy-)?[a-f0-9]{64}$ ]] || fail "ungueltige Manifest-ID" 64
}

set_path() {
    safe_manifest_id "$1"
    printf '%s/%s\n' "$SETS_ROOT" "$1"
}

init_user_roots() {
    [ "$(id -u)" -ne 0 ] || fail "Ganzskript-sudo ist verboten; als GENUS-Login starten" 77
    [ "$(id -un)" = "$GENUS_USER" ] || fail "GENUS_USER stimmt nicht mit dem ausfuehrenden Login ueberein" 77
    [ "$GENUS_USER" != root ] || [ "${GENUS_ALLOW_ROOT:-0}" = 1 ] \
        || fail "GENUS_USER=root ist ohne GENUS_ALLOW_ROOT=1 verboten" 77
    harden_privileged_boundary
    install -d -m 0700 "$STATE_ROOT" "$SETS_ROOT" "$DOWNLOAD_ROOT" "$RECEIPT_ROOT"
}

acquire_operator_lock() {
    [ "${OPERATOR_LOCK_HELD:-0}" -eq 0 ] || return 0
    require_command flock
    exec 9>"$LOCK_FILE"
    flock -n 9 || fail "ein anderer A0.3c-Lauf haelt den Operator-Lock" 75
    OPERATOR_LOCK_HELD=1
}

repo_commit() {
    "$GIT_BIN" -C "$REPO_DIR" rev-parse --verify HEAD
}

assert_expected_commit() {
    local expected="$1" actual
    [[ "$expected" =~ ^[a-f0-9]{40}$ ]] || fail "EXPECTED_COMMIT muss eine volle SHA-1 sein" 64
    actual="$(repo_commit)"
    [ "$actual" = "$expected" ] || fail "Repo-Commit weicht vom gebundenen Expected-Commit ab" 65
    [ -z "$("$GIT_BIN" -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all)" ] \
        || fail "Repo ist nicht exakt clean" 65
}

normalize_freeze() {
    local source="$1" target="$2" editable_policy="$3"
    local line editable=0
    : > "$target"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|'# '*) continue ;;
            -e\ *) editable=$((editable + 1)); continue ;;
        esac
        [[ "$line" =~ ^[A-Za-z0-9_.-]+==[^[:space:]]+$ ]] \
            || fail "nicht reproduzierbarer Eintrag im Paketinventar" 65
        case "${line%%==*}" in
            pip|setuptools|genus-pi-seed) continue ;;
        esac
        printf '%s\n' "$line" >> "$target"
    done < "$source"
    if [ "$editable_policy" = one ]; then
        [ "$editable" -eq 1 ] || fail "Core-Inventar muss genau ein kontrolliertes Editable enthalten" 65
        printf 'pip==%s\nsetuptools==%s\n' "$PIP_VERSION" "$SETUPTOOLS_VERSION" >> "$target"
    else
        [ "$editable" -eq 0 ] || fail "Embed-Inventar darf kein Editable enthalten" 65
        printf 'pip==%s\nsetuptools==%s\n' "$PIP_VERSION" "$SETUPTOOLS_VERSION" >> "$target"
    fi
    LC_ALL=C sort -fu -o "$target" "$target"
}

normalize_legacy_freeze() {
    local source="$1" target="$2" editable_policy="$3" line editable=0
    : > "$target"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|'# '*) continue ;;
            -e\ *) editable=$((editable + 1)); continue ;;
        esac
        [[ "$line" =~ ^[A-Za-z0-9_.-]+==[^[:space:]]+$ ]] \
            || fail "nicht reproduzierbarer Legacy-Inventareintrag" 65
        printf '%s\n' "$line" >> "$target"
    done < "$source"
    if [ "$editable_policy" = one ]; then
        [ "$editable" -eq 1 ] || fail "Legacy-Core braucht genau ein Editable" 65
        printf '%s\n' 'genus-pi-seed==editable-repo-bound' >> "$target"
    else
        [ "$editable" -eq 0 ] || fail "Legacy-Embed darf kein Editable enthalten" 65
    fi
    LC_ALL=C sort -fu -o "$target" "$target"
}

capture_locks() {
    local work="$1" core_python="$CORE_POINTER/bin/python" embed_python="$EMBED_POINTER/bin/python"
    [ -x "$core_python" ] && [ -x "$embed_python" ] \
        || fail "bestehende Core-/Embed-Venvs fehlen; kein belastbares Paketinventar" 65
    "$core_python" - "$REPO_DIR" <<'PY'
import pathlib, sys
import genus
repo = pathlib.Path(sys.argv[1]).resolve()
module = pathlib.Path(genus.__file__).resolve()
if repo not in module.parents:
    raise SystemExit("Core-Editable stammt nicht aus dem gebundenen Repo")
PY
    "$core_python" -m pip freeze --all > "$work/core.raw"
    "$embed_python" -m pip freeze --all > "$work/embed.raw"
    normalize_freeze "$work/core.raw" "$work/core.lock" one
    normalize_freeze "$work/embed.raw" "$work/embed.lock" none
    rm -f -- "$work/core.raw" "$work/embed.raw"
}

verify_archive() {
    local path="$1" algorithm="$2" expected="$3" actual
    case "$algorithm" in
        sha256) actual="$(sha256_file "$path")" ;;
        sha3) actual="$(sha3_file "$path")" ;;
        *) fail "interner Hashalgorithmus unbekannt" 70 ;;
    esac
    [ "$actual" = "$expected" ] || fail "Quellarchiv-Hash stimmt nicht: $(basename "$path")" 65
}

archive_digest() {
    local path="$1" algorithm="$2"
    case "$algorithm" in
        sha256) sha256_file "$path" ;;
        sha3) sha3_file "$path" ;;
        *) fail "interner Hashalgorithmus unbekannt" 70 ;;
    esac
}

bootstrap_build_dependencies() {
    local output="$1" package candidate
    local specs=()
    require_command "$APT_GET_BIN"
    require_command "$APT_CACHE_BIN"
    require_command "$DPKG_QUERY_BIN"
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$APT_GET_BIN" update
    for package in "${BOOTSTRAP_PACKAGES[@]}"; do
        candidate="$($APT_CACHE_BIN policy "$package" | awk '/Candidate:/ {print $2; exit}')"
        [ -n "$candidate" ] && [ "$candidate" != '(none)' ] \
            || fail "kein APT-Kandidat fuer Bootstrap-Paket $package" 69
        specs+=("$package=$candidate")
    done
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin DEBIAN_FRONTEND=noninteractive \
        "$APT_GET_BIN" install --no-install-recommends -y "${specs[@]}"
    : > "$output"
    for package in "${BOOTSTRAP_PACKAGES[@]}"; do
        "$DPKG_QUERY_BIN" -W -f='${binary:Package}=${Version}\n' "$package" >> "$output"
    done
    LC_ALL=C sort -u -o "$output" "$output"
}

download_source() {
    local url="$1" path="$2" algorithm="$3" expected="$4" actual temp quarantine
    if [ -e "$path" ] || [ -L "$path" ]; then
        [ -f "$path" ] && [ ! -L "$path" ] && [ "$(stat -c %h "$path")" -eq 1 ] \
            || fail "Quellarchiv-Cache ist kein regulaerer Einzel-Link" 65
        actual="$(archive_digest "$path" "$algorithm")"
        if [ "$actual" = "$expected" ]; then return 0; fi
        quarantine="${path}.failed.$(date -u +%Y%m%dT%H%M%S%N).$$.$RANDOM"
        [ ! -e "$quarantine" ] || fail "Quellarchiv-Quarantaene kollidiert" 70
        mv -T -- "$path" "$quarantine"
        fsync_dir "$DOWNLOAD_ROOT"
    fi
    temp="$(mktemp "$DOWNLOAD_ROOT/.source.partial.XXXXXX")"
    trap 'rm -f -- "$temp"' RETURN
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin HOME="$STATE_ROOT" LC_ALL=C \
        "$CURL_BIN" -q --fail --location --proto '=https' --tlsv1.2 \
        --output "$temp" "$url"
    verify_archive "$temp" "$algorithm" "$expected"
    sync -f "$temp"
    mv -T -- "$temp" "$path"
    fsync_dir "$DOWNLOAD_ROOT"
    trap - RETURN
}

runtime_tree_inventory() {
    local root="$1"
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$root" "$RUNTIME_INVENTORY_REL" <<'PY'
import hashlib
import json
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1])
excluded = pathlib.PurePosixPath(sys.argv[2]).as_posix()
before_root = root.lstat()
if not stat.S_ISDIR(before_root.st_mode) or stat.S_ISLNK(before_root.st_mode):
    raise SystemExit("runtime inventory root is not a real directory")
resolved_root = root.resolve(strict=True)
entries = []

def stable_digest(path, before):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns")
        if any(getattr(opened, key) != getattr(before, key) for key in fields):
            raise SystemExit("runtime file changed during open")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        final = os.fstat(fd)
        if size != before.st_size or any(getattr(final, key) != getattr(opened, key) for key in fields):
            raise SystemExit("runtime file changed during read")
        return digest.hexdigest()
    finally:
        os.close(fd)

def walk(directory):
    try:
        with os.scandir(directory) as scan:
            children = sorted(list(scan), key=lambda item: os.fsencode(item.name))
    except OSError as exc:
        raise SystemExit(f"runtime directory scan failed: {exc}") from exc
    for child in children:
        path = pathlib.Path(child.path)
        relative = path.relative_to(root).as_posix()
        if relative == excluded:
            continue
        if "\n" in relative or "\r" in relative:
            raise SystemExit("runtime path contains a line break")
        info = path.lstat()
        common = {"path": relative, "mode": stat.S_IMODE(info.st_mode), "nlink": info.st_nlink}
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            resolved = path.resolve(strict=True)
            if resolved != resolved_root and resolved_root not in resolved.parents:
                raise SystemExit("runtime symlink escapes private prefix")
            entries.append({**common, "type": "symlink", "target": target})
        elif stat.S_ISDIR(info.st_mode):
            entries.append({**common, "type": "directory"})
            walk(path)
        elif stat.S_ISREG(info.st_mode):
            entries.append({**common, "type": "file", "sha256": stable_digest(path, info)})
        else:
            raise SystemExit("runtime tree contains a special filesystem object")

walk(root)
python_rows = [item for item in entries if item["path"] == "bin/python3.13" and item["type"] == "file"]
if len(python_rows) != 1:
    raise SystemExit("runtime inventory lacks one regular CPython executable")
stdlib = [item for item in entries if item["path"].startswith("lib/python3.13/")]
if not stdlib:
    raise SystemExit("runtime inventory lacks the CPython stdlib")
canonical = lambda value: json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
whole = hashlib.sha256(canonical(entries)).hexdigest()
data = {
    "schema": "genus-a0.3c-private-runtime-inventory-v1",
    "python_executable_sha256": python_rows[0]["sha256"],
    "stdlib_sha256": hashlib.sha256(canonical(stdlib)).hexdigest(),
    "whole_tree_sha256": whole,
    "entries": entries,
}
print(json.dumps(data, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")))
PY
}

verify_runtime_tree_inventory() {
    local root="$1" inventory="$2" tmp
    [ -f "$inventory" ] && [ ! -L "$inventory" ] && [ "$(stat -c %h "$inventory")" -eq 1 ] \
        || fail "Runtime-Inventar ist nicht regulaer/einfach verlinkt" 65
    tmp="$(mktemp "$STATE_ROOT/runtime-inventory.verify.XXXXXX")"
    trap 'rm -f -- "$tmp"' RETURN
    runtime_tree_inventory "$root" > "$tmp"
    cmp -s -- "$tmp" "$inventory" || fail "privater Runtime-Dateibaum driftet" 65
    rm -f -- "$tmp"
    trap - RETURN
}

runtime_inventory_field() {
    local field="$1"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$RUNTIME_INVENTORY" "$field" <<'PY'
import json, pathlib, re, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
required = {"schema", "python_executable_sha256", "stdlib_sha256", "whole_tree_sha256", "entries"}
if set(data) != required or data["schema"] != "genus-a0.3c-private-runtime-inventory-v1":
    raise SystemExit("runtime inventory schema differs")
value = data.get(sys.argv[2])
if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
    raise SystemExit("runtime inventory digest is malformed")
print(value)
PY
}

write_runtime_publication_marker() {
    local inventory_hash="$1"
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$RUNTIME_PUBLICATION" "$RUNTIME_PREFIX" "$RUNTIME_PENDING" "$inventory_hash" <<'PY'
import json, os, pathlib, re, sys
path, runtime, pending, digest = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
if not re.fullmatch(r"[0-9a-f]{64}", digest):
    raise SystemExit("runtime publication digest is malformed")
payload = {"schema":"genus-a0.3c-runtime-publication-v1","runtime_path":runtime,"pending_path":pending,"inventory_sha256":digest}
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(path, flags, 0o600)
try:
    os.write(fd, (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode())
    os.fsync(fd)
finally:
    os.close(fd)
parent = os.open(pathlib.Path(path).parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try: os.fsync(parent)
finally: os.close(parent)
PY
}

validate_runtime_publication_marker() {
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$RUNTIME_PUBLICATION" "$RUNTIME_PREFIX" "$RUNTIME_PENDING" <<'PY'
import json, os, pathlib, re, stat, sys
path = pathlib.Path(sys.argv[1])
info = path.lstat()
if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
    raise SystemExit("runtime publication marker is not root-owned/0600/single-link")
data = json.loads(path.read_text())
expected = {"schema","runtime_path","pending_path","inventory_sha256"}
if set(data) != expected or data["schema"] != "genus-a0.3c-runtime-publication-v1":
    raise SystemExit("runtime publication marker schema differs")
if data["runtime_path"] != sys.argv[2] or data["pending_path"] != sys.argv[3] or not re.fullmatch(r"[0-9a-f]{64}", data["inventory_sha256"]):
    raise SystemExit("runtime publication marker binding differs")
print(data["inventory_sha256"])
PY
}

quarantine_runtime_path() {
    local path="$1" label="$2" quarantine
    quarantine="${path}.failed.$(date -u +%Y%m%dT%H%M%S%N).$$.$RANDOM"
    as_root "$ROOT_TEST_BIN" ! -e "$quarantine" || fail "$label-Quarantaene kollidiert" 70
    as_root "$ROOT_MV_BIN" -T -- "$path" "$quarantine"
    as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
}

recover_runtime_publication() {
    local marker_hash inventory_path actual_hash verify_status
    as_root "$ROOT_INSTALL_BIN" -d -o root -g root -m 0755 "$RUNTIME_PARENT"
    if as_root "$ROOT_TEST_BIN" -e "$RUNTIME_PUBLICATION"; then
        marker_hash="$(validate_runtime_publication_marker)" \
            || fail "Runtime-Publikationsmarker ist ungueltig" 70
        if as_root "$ROOT_TEST_BIN" -e "$RUNTIME_PENDING"; then
            as_root "$ROOT_TEST_BIN" ! -e "$RUNTIME_PREFIX" \
                || fail "Runtime-Publikation hat gleichzeitig Building- und Zielbaum" 70
            inventory_path="$RUNTIME_PENDING/$RUNTIME_INVENTORY_REL"
            set +e
            (
                set -Eeuo pipefail
                verify_runtime_tree_inventory "$RUNTIME_PENDING" "$inventory_path"
                [ "$(sha256_file "$inventory_path")" = "$marker_hash" ]
            )
            verify_status=$?
            set -e
            if [ "$verify_status" -ne 0 ]; then
                quarantine_runtime_path "$RUNTIME_PENDING" "ungueltige Building-Runtime"
                as_root "$ROOT_RM_BIN" -f -- "$RUNTIME_PUBLICATION"
                as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
                return 0
            fi
            durably_sync_tree "$RUNTIME_PENDING"
            as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
            as_root "$ROOT_MV_BIN" -T -- "$RUNTIME_PENDING" "$RUNTIME_PREFIX"
            as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
        fi
        as_root "$ROOT_TEST_BIN" -d "$RUNTIME_PREFIX" \
            || fail "Runtime-Publikationsmarker ohne fortsetzbaren Baum" 70
        set +e
        (
            set -Eeuo pipefail
            verify_runtime_tree_inventory "$RUNTIME_PREFIX" "$RUNTIME_INVENTORY"
            [ "$(sha256_file "$RUNTIME_INVENTORY")" = "$marker_hash" ]
            verify_runtime_prefix
        )
        verify_status=$?
        set -e
        if [ "$verify_status" -ne 0 ]; then
            quarantine_runtime_path "$RUNTIME_PREFIX" "ungueltige publizierte Runtime"
            as_root "$ROOT_RM_BIN" -f -- "$RUNTIME_PUBLICATION"
            as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
            return 0
        fi
        as_root "$ROOT_RM_BIN" -f -- "$RUNTIME_PUBLICATION"
        as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
        return 0
    fi
    if as_root "$ROOT_TEST_BIN" -e "$RUNTIME_PENDING"; then
        quarantine_runtime_path "$RUNTIME_PENDING" "verwaiste Building-Runtime"
    fi
    if as_root "$ROOT_TEST_BIN" -e "$RUNTIME_PREFIX"; then
        # Auch der markerlose Fall heilt sich selbst. Ein hartes fail() beendete hier
        # das ganze Skript, bevor der Quarantaene-Zweig in stage_set greifen konnte --
        # jeder Fehlversuch haette dann eine root-Handaufraeumung gebraucht (live
        # belegt 2026-08-21). Direkt darueber wird beim selben Fehler bereits
        # quarantaeniert; dieser Zweig folgt derselben Regel.
        set +e
        ( set -Eeuo pipefail; verify_runtime_prefix )
        verify_status=$?
        set -e
        if [ "$verify_status" -ne 0 ]; then
            quarantine_runtime_path "$RUNTIME_PREFIX" "unbrauchbare markerlose Runtime"
        fi
    fi
}

runtime_probe() {
    local python="$1" expected_executable="${2:-$1}"
    "$python" - "$RUNTIME_PREFIX" "$expected_executable" "$SQLITE_VERSION" "$SQLITE_SOURCE_ID" <<'PY'
import _sqlite3, hashlib, json, os, pathlib, sqlite3, sys
prefix = pathlib.Path(sys.argv[1]).resolve()
expected_executable = pathlib.Path(sys.argv[2]).resolve()
expected_version, expected_source = sys.argv[3:5]
if sys.version.split()[0] != "3.13.15" or sys.version_info[:3] != (3, 13, 15):
    raise SystemExit("CPython version mismatch")
if pathlib.Path(sys.executable).resolve() != expected_executable:
    raise SystemExit("sys.executable is not the manifest-bound interpreter")
if pathlib.Path(sys._base_executable).resolve() != (prefix / "bin/python3.13").resolve():
    raise SystemExit("venv base executable is not the pinned runtime")
if sqlite3.sqlite_version != expected_version:
    raise SystemExit("SQLite version mismatch")
with sqlite3.connect(":memory:") as db:
    source_id = db.execute("select sqlite_source_id()").fetchone()[0]
    options = sorted(row[0] for row in db.execute("pragma compile_options"))
if source_id != expected_source or "THREADSAFE=1" not in options or "OMIT_WAL" in options:
    raise SystemExit("SQLite source/options mismatch")
mapped = []
for line in pathlib.Path("/proc/self/maps").read_text().splitlines():
    candidate = line.rsplit(None, 1)[-1]
    if "/" in candidate and "libsqlite3.so" in candidate:
        mapped.append(pathlib.Path(candidate).resolve())
mapped = sorted(set(mapped))
if len(mapped) != 1 or prefix not in mapped[0].parents:
    raise SystemExit("private libsqlite3 is not the sole mapped SQLite library")
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
payload = {
    "compile_options_sha256": hashlib.sha256(("\n".join(options) + "\n").encode()).hexdigest(),
    "sqlite_extension_sha256": digest(pathlib.Path(_sqlite3.__file__)),
    "sqlite_library_sha256": digest(mapped[0]),
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
PY
}

verify_runtime_prefix() {
    local python="$RUNTIME_PREFIX/bin/python3.13" extension dynamic actual output status
    [ -x "$python" ] || fail "private Runtime fehlt" 65
    [ ! -L "$RUNTIME_PREFIX" ] || fail "Runtime-Prefix darf kein Symlink sein" 65
    actual="$(realpath -e -- "$RUNTIME_PREFIX")" \
        || fail "Runtime-Prefix ist nicht kanonisch lesbar" 65
    [ "$actual" = "$RUNTIME_PREFIX" ] || fail "Runtime-Prefix ist nicht der fixe reale Pfad" 65
    set +e
    output="$(as_root "$ROOT_FIND_BIN" "$RUNTIME_PREFIX" -xdev ! -user root -print -quit 2>&1)"; status=$?
    set -e
    [ "$status" -eq 0 ] && [ -z "$output" ] \
        || fail "Runtime-Tree ist nicht vollstaendig root-owned/lesbar" 65
    set +e
    # Symlinks tragen unter Linux immer lrwxrwxrwx; ihre Modusbits sind bedeutungslos,
    # der Kernel entscheidet am Ziel, und `chmod -R go-w` fasst sie deshalb nicht an.
    # Ohne diesen Ausschluss meldet der Scan die neun CPython-Symlinks (bin/python3 &
    # Co.) als welt-schreibbar und die Runtime kann nie verifiziert werden (live belegt
    # 2026-08-21). Die Garantie bleibt: Symlink-Eigentum deckt der ! -user root-Scan ab,
    # die Ziele deckt derselbe Scan als reale Dateien ab, und runtime_tree_inventory
    # bindet jedes Symlink-Ziel, sodass ein umgehaengtes Ziel auffliegt.
    output="$(as_root "$ROOT_FIND_BIN" "$RUNTIME_PREFIX" -xdev ! -type l -perm /022 -print -quit 2>&1)"; status=$?
    set -e
    [ "$status" -eq 0 ] && [ -z "$output" ] \
        || fail "Runtime ist gruppen-/welt-schreibbar" 65
    # Gegenprobe zur Schreibbarkeit: Die Dienste laufen unprivilegiert, eine nur
    # fuer root lesbare Runtime ist wertlos (live belegt 2026-08-21: 136
    # Verzeichnisse auf 0700, darunter site-packages/pip).
    output="$(as_root "$ROOT_FIND_BIN" "$RUNTIME_PREFIX" -xdev ! -type l         \( ! -perm -o+r -o \( -type d ! -perm -o+x \) \) -print -quit 2>&1)"; status=$?
    [ "$status" -eq 0 ] && [ -z "$output" ]         || fail "Runtime ist fuer den unprivilegierten Dienstbenutzer nicht lesbar" 65
    [ -f "$RUNTIME_INVENTORY" ] && [ ! -L "$RUNTIME_INVENTORY" ] \
        && [ "$(stat -c %U "$RUNTIME_INVENTORY")" = root ] \
        && [ "$(stat -c %a "$RUNTIME_INVENTORY")" = 644 ] \
        && [ "$(stat -c %h "$RUNTIME_INVENTORY")" -eq 1 ] \
        || fail "Runtime-Inventar ist nicht root-owned/0644/einfach verlinkt" 65
    verify_runtime_tree_inventory "$RUNTIME_PREFIX" "$RUNTIME_INVENTORY"
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$RUNTIME_PREFIX" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for path in root.rglob("*"):
    try:
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if resolved != root and root not in resolved.parents:
                raise SystemExit("runtime symlink escapes private prefix")
        else:
            path.stat()
    except OSError as exc:
        raise SystemExit(f"runtime tree inspection incomplete: {exc}") from exc
PY
    runtime_probe "$python" "$python" >/dev/null
    extension="$($python -c 'import _sqlite3; print(_sqlite3.__file__)')"
    dynamic="$($READELF_BIN -d "$extension")"
    grep -Fq '(RUNPATH)' <<<"$dynamic" || fail "_sqlite3 hat keinen RUNPATH" 65
    grep -Fq "Library runpath: [$RUNTIME_PREFIX/lib]" <<<"$dynamic" \
        || fail "_sqlite3 RUNPATH ist nicht der absolute private lib-Pfad" 65
}

build_runtime() {
    local build stage stage_runtime sqlite_src python_src jobs bootstrap_lock inventory_hash
    recover_runtime_publication
    if as_root "$ROOT_TEST_BIN" -e "$RUNTIME_PREFIX"; then
        return
    fi
    for tool in "$CURL_BIN" "$TAR_BIN" "$MAKE_BIN" "$OPENSSL_BIN" "$READELF_BIN"; do require_command "$tool"; done
    download_source "$PYTHON_URL" "$DOWNLOAD_ROOT/$PYTHON_ARCHIVE" sha256 "$PYTHON_SHA256"
    download_source "$SQLITE_URL" "$DOWNLOAD_ROOT/$SQLITE_ARCHIVE" sha3 "$SQLITE_SHA3_256"
    verify_archive "$DOWNLOAD_ROOT/$PYTHON_ARCHIVE" sha256 "$PYTHON_SHA256"
    verify_archive "$DOWNLOAD_ROOT/$SQLITE_ARCHIVE" sha3 "$SQLITE_SHA3_256"
    build="$(mktemp -d "$STATE_ROOT/build.XXXXXX")"
    trap 'rm -rf -- "$build"' RETURN
    bootstrap_lock="$build/bootstrap.lock"
    bootstrap_build_dependencies "$bootstrap_lock"
    "$TAR_BIN" -xf "$DOWNLOAD_ROOT/$SQLITE_ARCHIVE" -C "$build"
    "$TAR_BIN" -xf "$DOWNLOAD_ROOT/$PYTHON_ARCHIVE" -C "$build"
    sqlite_src="$build/sqlite-autoconf-$SQLITE_NUMBER"
    python_src="$build/Python-$PYTHON_VERSION"
    stage="$build/stage"
    jobs="${GENUS_A03C_BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN)}"
    (
        cd "$sqlite_src"
        # Das globale umask 077 wuerde alles, was Python hier anlegt (pip-
        # Installation, __pycache__), auf 0700 setzen. Nach dem chown auf root
        # koennte der unprivilegierte Dienstbenutzer die Runtime dann nicht mehr
        # lesen -- live belegt 2026-08-21 mit 136 unlesbaren Verzeichnissen.
        # Der Runtime-Baum entsteht deshalb bewusst oeffentlich lesbar; State,
        # Sets und Belege bleiben vom globalen umask geschuetzt.
        umask 022
        CFLAGS='-O2 -fPIC' ./configure --prefix="$RUNTIME_PREFIX" --disable-static --enable-shared
        "$MAKE_BIN" -j"$jobs"
        "$MAKE_BIN" DESTDIR="$stage" install
    )
    (
        cd "$python_src"
        umask 022
        # CPython prueft nach dem Bau jedes Modul auf Importierbarkeit.
        # _sqlite3 traegt bereits den RUNPATH auf den finalen Prefix, der zu
        # diesem Zeitpunkt noch nicht veroeffentlicht ist -- ohne bauzeitlichen
        # Suchpfad scheitert der Import, CPython benennt das Modul in
        # *_failed.so um und der Install bricht ab (live belegt 2026-08-20).
        # Der Suchpfad gilt ausschliesslich hier im Bau; das ausgelieferte
        # Artefakt loest libsqlite3 weiterhin allein ueber seinen RUNPATH auf,
        # was runtime_probe anschliessend erzwingt.
        export LD_LIBRARY_PATH="$stage$RUNTIME_PREFIX/lib"
        CPPFLAGS="-I$stage$RUNTIME_PREFIX/include" \
        LDFLAGS="-L$stage$RUNTIME_PREFIX/lib -Wl,--enable-new-dtags,-rpath,$RUNTIME_PREFIX/lib" \
        PKG_CONFIG_PATH="$stage$RUNTIME_PREFIX/lib/pkgconfig" \
            ./configure --prefix="$RUNTIME_PREFIX" --with-ensurepip=install
        "$MAKE_BIN" -j"$jobs"
        "$MAKE_BIN" DESTDIR="$stage" install
        "$stage$RUNTIME_PREFIX/bin/python3.13" -c 'import _sqlite3' \
            || fail "CPython wurde ohne _sqlite3 gebaut" 70
    )
    install -d -m 0755 "$stage$RUNTIME_PREFIX/share/genus"
    install -m 0644 "$bootstrap_lock" "$stage$RUNTIME_PREFIX/share/genus/BUILD-BOOTSTRAP.lock"
    stage_runtime="$stage$RUNTIME_PREFIX"
    runtime_tree_inventory "$stage_runtime" > "$build/runtime.inventory.tmp"
    chmod 0644 "$build/runtime.inventory.tmp"
    sync -f "$build/runtime.inventory.tmp"
    install -m 0644 "$build/runtime.inventory.tmp" "$stage_runtime/$RUNTIME_INVENTORY_REL"
    sync -f "$stage_runtime/$RUNTIME_INVENTORY_REL"
    fsync_dir "$(dirname "$stage_runtime/$RUNTIME_INVENTORY_REL")"
    verify_runtime_tree_inventory "$stage_runtime" "$stage_runtime/$RUNTIME_INVENTORY_REL"
    inventory_hash="$(sha256_file "$stage_runtime/$RUNTIME_INVENTORY_REL")"
    as_root "$ROOT_INSTALL_BIN" -d -o root -g root -m 0755 "$RUNTIME_PARENT"
    as_root "$ROOT_TEST_BIN" ! -e "$RUNTIME_PENDING" \
        || fail "Building-Runtime blieb trotz Recovery bestehen" 70
    as_root "$ROOT_CP_BIN" -a -- "$stage_runtime" "$RUNTIME_PENDING"
    as_root "$ROOT_CHOWN_BIN" -R root:root "$RUNTIME_PENDING"
    as_root "$ROOT_CHMOD_BIN" -R go-w "$RUNTIME_PENDING"
    verify_runtime_tree_inventory "$RUNTIME_PENDING" "$RUNTIME_PENDING/$RUNTIME_INVENTORY_REL"
    [ "$(sha256_file "$RUNTIME_PENDING/$RUNTIME_INVENTORY_REL")" = "$inventory_hash" ] \
        || fail "Runtime-Inventar driftete beim privilegierten Copy" 70
    durably_sync_tree "$RUNTIME_PENDING"
    as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
    write_runtime_publication_marker "$inventory_hash"
    publication_fault_point after-runtime-marker
    as_root "$ROOT_MV_BIN" -T -- "$RUNTIME_PENDING" "$RUNTIME_PREFIX"
    as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
    publication_fault_point after-runtime-rename
    verify_runtime_prefix
    as_root "$ROOT_RM_BIN" -f -- "$RUNTIME_PUBLICATION"
    as_root "$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"
    publication_fault_point after-runtime-finalize
    rm -rf -- "$build"
    trap - RETURN
}

inventory_for_compare() {
    local python="$1" policy="$2" target="$3" raw="${target}.raw"
    "$python" -m pip freeze --all > "$raw"
    normalize_freeze "$raw" "$target" "$policy"
    rm -f -- "$raw"
}

wheel_inventory() {
    local wheelhouse="$1" target="$2" file
    : > "$target"
    while IFS= read -r -d '' file; do
        printf '%s  %s\n' "$(sha256_file "$file")" "$(basename "$file")" >> "$target"
    done < <(find "$wheelhouse" -maxdepth 1 -type f -name '*.whl' -print0 | LC_ALL=C sort -z)
    [ -s "$target" ] || fail "Wheelhouse ist leer" 65
}

clean_pip() {
    local python="$1" home="$2"
    shift 2
    install -d -m 0700 "$home"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin HOME="$home" LC_ALL=C.UTF-8 \
        PYTHONNOUSERSITE=1 PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 \
        PIP_NO_INPUT=1 PIP_NO_CACHE_DIR=1 \
        "$python" -I -P -m pip "$@"
}

artifact_inventory() {
    local directory="$1" target="$2"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$directory" "$target" <<'PY'
import hashlib, os, pathlib, re, stat, sys
root, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
rows = []
for path in sorted(root.iterdir(), key=lambda item: os.fsencode(item.name)):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SystemExit("artifact store contains a non-regular/single-link object")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!-]*", path.name):
        raise SystemExit("artifact filename is unsafe")
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        while chunk := os.read(fd, 1024 * 1024): digest.update(chunk)
    finally:
        os.close(fd)
    rows.append(f"{digest.hexdigest()}  {path.name}")
if not rows:
    raise SystemExit("artifact store is empty")
target.write_text("\n".join(rows) + "\n")
PY
}

acquire_locked_sources() {
    local lock="$1" destination="$2" binary_lock="$3"
    install -d -m 0700 "$destination"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin HOME="$STATE_ROOT" LC_ALL=C.UTF-8 \
        "$RUNTIME_PREFIX/bin/python3.13" -I -P - \
        "$lock" "$destination" "$binary_lock" "$PYPI_INDEX_URL" <<'PY'
import hashlib, json, os, pathlib, re, ssl, sys, urllib.parse, urllib.request
lock, destination, binary_lock, index = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), sys.argv[4]
if index != "https://pypi.org/simple": raise SystemExit("package index is not the fixed PyPI origin")
requirements = []
for line in lock.read_text().splitlines():
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line)
    if not match: raise SystemExit("lock contains a non-exact requirement")
    requirements.append(match.groups())
if len({re.sub(r"[-_.]+", "-", name).lower() for name, _ in requirements}) != len(requirements):
    raise SystemExit("lock contains duplicate normalized projects")

def sdist_identity(filename):
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".zip"):
        if filename.endswith(suffix):
            stem = filename[:-len(suffix)]
            for position in range(1, len(stem)):
                if stem[position] == "-": yield stem[:position], stem[position + 1:]

# Wheel-First: ein bereits veroeffentlichtes Wheel wird bevorzugt, sobald es zur
# Zielplattform passt; die sdist bleibt der Rueckfallweg. Rust-Extensions wie
# tokenizers, py_rust_stemmers und hf-xet sind in der netzlosen Build-Sandbox
# grundsaetzlich nicht baubar (kein rustc, kein crates.io) -- ihre manylinux-
# Wheels sind exakt die Artefakte, die der Pi heute schon ausfuehrt. Die
# Herkunftsbindung bleibt unveraendert: fixer Index, fixe Datei-Origin und der
# index-advertisierte SHA-256 gelten fuer Wheel und sdist gleichermassen.
MACHINE = os.uname().machine
PYTHON_MINOR = sys.version_info[1]
try:
    _libc = os.confstr("CS_GNU_LIBC_VERSION") or ""
except (OSError, ValueError):
    _libc = ""
_libc_match = re.fullmatch(r"glibc (\d+)\.(\d+)", _libc.strip())
GLIBC = (int(_libc_match.group(1)), int(_libc_match.group(2))) if _libc_match else None

def wheel_identity(filename):
    if not filename.endswith(".whl"): return None
    parts = filename[:-4].split("-")
    if len(parts) < 5: return None
    return parts[0], parts[1], parts[-3].split("."), parts[-2].split("."), parts[-1].split(".")

def platform_floor(tag):
    if tag == "any": return (0, 0)
    if tag.startswith("musllinux") or not tag.endswith("_" + MACHINE): return None
    if tag == "manylinux2014_" + MACHINE: tag = "manylinux_2_17_" + MACHINE
    match = re.fullmatch(r"manylinux_(\d+)_(\d+)_" + re.escape(MACHINE), tag)
    if not match: return None
    floor = (int(match.group(1)), int(match.group(2)))
    return floor if GLIBC is not None and floor <= GLIBC else None

def interpreter_ok(python_tag, abi_tag):
    if abi_tag == "abi3":
        match = re.fullmatch(r"cp3(\d+)", python_tag)
        return match is not None and int(match.group(1)) <= PYTHON_MINOR
    if abi_tag == "cp3%d" % PYTHON_MINOR: return python_tag == abi_tag
    if abi_tag == "none":
        match = re.fullmatch(r"(?:py|cp)3(\d*)", python_tag)
        return match is not None and (not match.group(1) or int(match.group(1)) <= PYTHON_MINOR)
    return False

def wheel_rank(identity):
    _, _, python_tags, abi_tags, platform_tags = identity
    floors = [floor for floor in map(platform_floor, platform_tags) if floor is not None]
    if not floors: return None
    if not any(interpreter_ok(python_tag, abi_tag) for python_tag in python_tags for abi_tag in abi_tags):
        return None
    return (0 if "any" in platform_tags else 1, 1 if "cp3%d" % PYTHON_MINOR in abi_tags else 0, max(floors))

missing = []
context = ssl.create_default_context()
for name, version in requirements:
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    url = f"{index}/{urllib.parse.quote(normalized, safe='')}/"
    request = urllib.request.Request(url, headers={"Accept":"application/vnd.pypi.simple.v1+json","Accept-Encoding":"identity","User-Agent":"GENUS-A0.3c-hermetic-acquirer/1"})
    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        if response.geturl() != url or urllib.parse.urlsplit(response.geturl()).scheme != "https":
            raise SystemExit("simple-index redirected away from its fixed project URL")
        data = json.load(response)
    candidates = []
    wheels = []
    for item in data.get("files", []):
        filename = item.get("filename")
        digest = item.get("hashes", {}).get("sha256")
        if not isinstance(filename, str) or not re.fullmatch(r"[0-9a-f]{64}", digest or "") or item.get("yanked", False): continue
        identity = wheel_identity(filename)
        if identity is not None:
            if re.sub(r"[-_.]+", "-", identity[0]).lower() == normalized and identity[1] == version:
                rank = wheel_rank(identity)
                if rank is not None: wheels.append((rank, filename, item.get("url"), digest))
            continue
        for project, found_version in sdist_identity(filename):
            if re.sub(r"[-_.]+", "-", project).lower() == normalized and found_version == version:
                candidates.append((filename, item.get("url"), digest)); break
    if wheels:
        wheels.sort(key=lambda entry: (entry[0], entry[1]))
        candidates = [wheels[-1][1:]]
    elif not candidates:
        missing.append(f"{name}=={version}"); continue
    elif len(candidates) != 1: raise SystemExit(f"project {name} has an ambiguous sdist set")
    filename, artifact_url, expected = candidates[0]
    parsed = urllib.parse.urlsplit(artifact_url)
    if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
        raise SystemExit("artifact URL left the fixed PyPI file origin")
    target = destination / filename
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    digest = hashlib.sha256()
    try:
        artifact_request = urllib.request.Request(artifact_url, headers={"Accept-Encoding":"identity","User-Agent":"GENUS-A0.3c-hermetic-acquirer/1"})
        with urllib.request.urlopen(artifact_request, timeout=120, context=context) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != "files.pythonhosted.org": raise SystemExit("artifact redirected away from fixed file origin")
            while chunk := response.read(1024 * 1024):
                digest.update(chunk); os.write(fd, chunk)
        if digest.hexdigest() != expected: raise SystemExit("PyPI-advertised artifact digest differs")
        os.fsync(fd)
    finally:
        os.close(fd)
parent = os.open(destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try: os.fsync(parent)
finally: os.close(parent)
binary_lock.write_text("\n".join(missing) + ("\n" if missing else ""))
PY
    if [ -s "$binary_lock" ]; then
        clean_pip "$RUNTIME_PREFIX/bin/python3.13" "${destination}.pip-home" download \
            --index-url "$PYPI_INDEX_URL" --only-binary=:all: --no-deps \
            --dest "$destination" -r "$binary_lock"
    fi
}

build_backend_requirements() {
    local sources="$1" target="$2"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$sources" "$target" "$PIP_VERSION" "$SETUPTOOLS_VERSION" <<'PY'
import pathlib, tarfile, tomllib, zipfile, sys
root, output = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
requirements = {f"pip=={sys.argv[3]}", f"setuptools=={sys.argv[4]}", "wheel"}
for archive in root.iterdir():
    payload = None
    try:
        if archive.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            with tarfile.open(archive, "r:*") as package:
                members = [member for member in package.getmembers() if member.isfile() and pathlib.PurePosixPath(member.name).name == "pyproject.toml" and len(pathlib.PurePosixPath(member.name).parts) == 2]
                if len(members) > 1: raise SystemExit("sdist has ambiguous root pyproject.toml")
                if members:
                    if members[0].size > 1024 * 1024: raise SystemExit("pyproject.toml is unexpectedly large")
                    payload = package.extractfile(members[0]).read()
        elif archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as package:
                members = [name for name in package.namelist() if pathlib.PurePosixPath(name).name == "pyproject.toml" and len(pathlib.PurePosixPath(name).parts) == 2]
                if len(members) > 1: raise SystemExit("sdist has ambiguous root pyproject.toml")
                if members:
                    info = package.getinfo(members[0])
                    if info.file_size > 1024 * 1024: raise SystemExit("pyproject.toml is unexpectedly large")
                    payload = package.read(members[0])
        else:
            continue
    except (tarfile.TarError, zipfile.BadZipFile) as exc:
        raise SystemExit(f"cannot inspect sdist safely: {archive.name}: {exc}") from exc
    if payload is None:
        requirements.add("setuptools>=40.8.0")
        continue
    build = tomllib.loads(payload.decode("utf-8")).get("build-system", {})
    values = build.get("requires", ["setuptools>=40.8.0"])
    if not isinstance(values, list) or not values or any(not isinstance(item, str) or "\n" in item or "\r" in item or "@" in item or "://" in item or "\\" in item or item.startswith(("-", ".", "/")) for item in values):
        raise SystemExit("build-system.requires is unsafe")
    requirements.update(values)
output.write_text("\n".join(sorted(requirements, key=str.casefold)) + "\n")
PY
}

seal_artifact_store() {
    local directory="$1" inventory="$2" verify
    chmod 0400 "$directory"/*
    chmod 0500 "$directory"
    chmod 0400 "$inventory"
    sync -f "$inventory"
    fsync_dir "$(dirname "$inventory")"
    verify="$(mktemp "$STATE_ROOT/artifacts.verify.XXXXXX")"
    artifact_inventory "$directory" "$verify"
    cmp -s -- "$verify" "$inventory" || fail "Artefaktstore driftete vor Versiegelung" 70
    rm -f -- "$verify"
    durably_sync_tree "$directory"
}

verify_artifact_store() {
    local directory="$1" inventory="$2" verify
    [ "$(stat -c %a "$directory")" = 500 ] \
        || fail "Artefaktstore ist vor Ausfuehrung schreibbar" 70
    [ -z "$(find "$directory" -maxdepth 1 -type f -perm /222 -print -quit)" ] \
        || fail "Artefakt ist vor Ausfuehrung schreibbar" 70
    verify="$(mktemp "$STATE_ROOT/artifacts.verify.XXXXXX")"
    artifact_inventory "$directory" "$verify"
    cmp -s -- "$verify" "$inventory" || fail "Artefaktstore driftete nach Operator-Freigabe" 70
    rm -f -- "$verify"
}

root_artifact_inventory() {
    local directory="$1" target="$2"
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$directory" "$target" <<'PY'
import hashlib, os, pathlib, re, stat, sys
root, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); rows=[]
for path in sorted(root.iterdir(), key=lambda item: os.fsencode(item.name)):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!-]*",path.name):
        raise SystemExit("sandbox artifact is unsafe")
    fields=("st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns")
    digest=hashlib.sha256(); fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        opened=os.fstat(fd)
        if any(getattr(opened,key)!=getattr(info,key) for key in fields): raise SystemExit("sandbox artifact changed during open")
        while chunk:=os.read(fd,1024*1024): digest.update(chunk)
        final=os.fstat(fd)
        if any(getattr(final,key)!=getattr(opened,key) for key in fields): raise SystemExit("sandbox artifact changed during read")
    finally: os.close(fd)
    rows.append(f"{digest.hexdigest()}  {path.name}")
if not rows: raise SystemExit("sandbox artifact store is empty")
fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,("\n".join(rows)+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
PY
}

create_build_scratch() {
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$STATE_ROOT" "$(id -u)" <<'PY'
import json, os, pathlib, secrets, sys
parent=pathlib.Path("/var/tmp"); state=sys.argv[1]; uid=int(sys.argv[2])
for _ in range(128):
    path=parent/f"genus-a03c-build.{secrets.token_hex(12)}"
    try: os.mkdir(path,0o700)
    except FileExistsError: continue
    marker=path/".genus-a03c-build-owner"
    payload={"schema":"genus-a0.3c-build-scratch-v1","state_root":state,"operator_uid":uid}
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    try: os.write(fd,(json.dumps(payload,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
    finally: os.close(fd)
    directory=os.open(path,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
    try: os.fsync(directory)
    finally: os.close(directory)
    root=os.open(parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
    try: os.fsync(root)
    finally: os.close(root)
    print(path); break
else: raise SystemExit("cannot allocate unique build scratch")
PY
}

# Der RETURN-Trap in build_runtime raeumt nur den Erfolgsfall auf: bei errexit
# oder exit feuert er nicht. Ein abgebrochener Bau liess so 851 MB im State-Root
# liegen (live belegt 2026-08-20). Unter der Operator-Sperre kann kein zweiter
# Lauf aktiv sein -- vorgefundene Baureste sind deshalb immer Altlasten.
recover_stale_state_builds() {
    local path
    for path in "$STATE_ROOT"/build.*; do
        [ -d "$path" ] || continue
        [ ! -L "$path" ] || fail "Baurest ist ein Symlink" 70
        log "entferne Baurest $(basename -- "$path")"
        rm -rf -- "$path"
    done
}

recover_stale_build_scratch() {
    local output status path
    set +e
    output="$(as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$STATE_ROOT" "$(id -u)" <<'PY'
import json, os, pathlib, re, stat, sys
parent=pathlib.Path("/var/tmp"); state=sys.argv[1]; uid=int(sys.argv[2]); candidates=[]
for path in parent.iterdir():
    if not re.fullmatch(r"genus-a03c-build\.[0-9a-f]{24}",path.name): continue
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid!=0: raise SystemExit("build scratch path is unsafe")
    marker=path/".genus-a03c-build-owner"
    marker_info=marker.lstat()
    if not stat.S_ISREG(marker_info.st_mode) or marker_info.st_uid!=0 or stat.S_IMODE(marker_info.st_mode)!=0o600 or marker_info.st_nlink!=1: raise SystemExit("build scratch marker is unsafe")
    data=json.loads(marker.read_text())
    if data!={"schema":"genus-a0.3c-build-scratch-v1","state_root":state,"operator_uid":uid}: continue
    candidates.append(path)
for process in pathlib.Path("/proc").iterdir():
    if not process.name.isdigit(): continue
    targets=[]
    try:
        targets.append(pathlib.Path(os.readlink(process/"cwd")))
        targets.extend(pathlib.Path(os.readlink(fd)) for fd in (process/"fd").iterdir())
    except (FileNotFoundError,ProcessLookupError): continue
    except (PermissionError,OSError) as exc: raise SystemExit(f"build scratch process inspection incomplete: {exc}") from exc
    for candidate in candidates:
        if any(target==candidate or candidate in target.parents for target in targets): raise SystemExit("stale build scratch is still in use")
for candidate in candidates: print(candidate)
PY
)"
    status=$?
    set -e
    [ "$status" -eq 0 ] || fail "stale Build-Scratch konnte nicht sicher inventarisiert werden" 70
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        [[ "$path" =~ ^/var/tmp/genus-a03c-build\.[0-9a-f]{24}$ ]] \
            || fail "stale Build-Scratch-Ausgabe ist ungueltig" 70
        as_root "$ROOT_RM_BIN" -rf -- "$path"
        as_root "$ROOT_SYNC_BIN" -f /var/tmp
    done <<< "$output"
}

sandbox_run() {
    local scratch="$1"
    shift
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$ROOT_SYSTEMD_RUN_BIN" \
        --quiet --wait --pipe --collect --property=Type=exec \
        --property=User=nobody --property=Group=nogroup --property=UMask=0077 \
        --property=ProtectHome=yes --property=ProtectSystem=strict \
        --property=PrivateNetwork=yes --property=PrivateDevices=yes --property=PrivateTmp=yes \
        --property=NoNewPrivileges=yes --property=CapabilityBoundingSet= \
        --property=RestrictAddressFamilies=AF_UNIX --property=ProtectProc=invisible \
        --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes \
        --property=ProtectControlGroups=yes --property=LockPersonality=yes \
        --property=TasksMax=512 --property=RuntimeMaxSec=4h \
        --property=MemoryMax=7G --property=LimitFSIZE=8G \
        --property="ReadOnlyPaths=$scratch/input $RUNTIME_PREFIX" \
        --property="ReadWritePaths=$scratch/work $scratch/output" \
        --property="InaccessiblePaths=$REPO_DIR $STATE_ROOT $DB_PATH" \
        --property="WorkingDirectory=$scratch/work" \
        --setenv=PATH=/usr/bin:/bin --setenv="HOME=$scratch/work/home" --setenv=LC_ALL=C.UTF-8 \
        --setenv=PYTHONNOUSERSITE=1 --setenv=PIP_CONFIG_FILE=/dev/null \
        --setenv=PIP_DISABLE_PIP_VERSION_CHECK=1 --setenv=PIP_NO_INPUT=1 \
        --setenv=PIP_NO_CACHE_DIR=1 -- "$@"
}

sandbox_canary() {
    local scratch="$1"
    sandbox_run "$scratch" "$RUNTIME_PREFIX/bin/python3.13" -I -P -c \
        'import os,pathlib,sys; forbidden=[pathlib.Path(p) for p in sys.argv[2:5]]; assert os.getuid()!=int(sys.argv[1]) and pathlib.Path.cwd()==pathlib.Path(sys.argv[5]) and os.environ.get("PATH")=="/usr/bin:/bin"; [(lambda p: (_ for _ in ()).throw(SystemExit("forbidden product path visible")) if p.exists() else None)(p) for p in forbidden]; targets=[]; [(targets.append(os.readlink(fd))) for fd in pathlib.Path("/proc/self/fd").iterdir() if fd.name not in {"0","1","2"}]; assert not any(any(str(p) in t for p in forbidden) for t in targets); assert not any(any(str(p) in value for p in forbidden) for value in os.environ.values()); interfaces={p.name for p in pathlib.Path("/sys/class/net").iterdir()}; assert interfaces <= {"lo"}; pathlib.Path(sys.argv[6]).write_text("isolated\n")' \
        "$(id -u)" "$REPO_DIR" "$STATE_ROOT" "$DB_PATH" "$scratch/work" "$scratch/output/.canary"
    as_root "$ROOT_TEST_BIN" -f "$scratch/output/.canary" \
        || fail "Build-Sandbox konnte designated output nicht schreiben" 70
    as_root "$ROOT_RM_BIN" -f -- "$scratch/output/.canary"
}

prepare_wheelhouse_inputs() {
    local lock="$1" wheelhouse="$2" builder="$3" sources="$4" backends="$5" prefix="$6"
    local binary_lock="${sources}.binary.lock" backend_requirements="${backends}.requirements"
    acquire_locked_sources "$lock" "$sources" "$binary_lock"
    artifact_inventory "$sources" "${prefix}-sources.sha256"
    build_backend_requirements "$sources" "$backend_requirements"
    install -d -m 0700 "$backends"
    clean_pip "$RUNTIME_PREFIX/bin/python3.13" "${backends}.pip-home" download \
        --index-url "$PYPI_INDEX_URL" --only-binary=:all: --dest "$backends" \
        -r "$backend_requirements"
    artifact_inventory "$backends" "${prefix}-backends.sha256"
    seal_artifact_store "$sources" "${prefix}-sources.sha256"
    seal_artifact_store "$backends" "${prefix}-backends.sha256"
}

build_wheelhouse() (
    local lock="$1" wheelhouse="$2" builder="$3" sources="$4" backends="$5" prefix="$6"
    local scratch nobody_uid nobody_gid copied_inventory verify_inventory
    verify_artifact_store "$sources" "${prefix}-sources.sha256"
    verify_artifact_store "$backends" "${prefix}-backends.sha256"
    nobody_uid="$(getent passwd nobody | cut -d: -f3)"
    nobody_gid="$(getent group nogroup | cut -d: -f3)"
    [[ "$nobody_uid" =~ ^[0-9]+$ ]] && [[ "$nobody_gid" =~ ^[0-9]+$ ]] \
        || fail "dedizierte Build-Identitaet nobody:nogroup fehlt" 69
    [ "$nobody_uid" -ne "$(id -u)" ] || fail "Build-Identitaet ist nicht vom Operator getrennt" 70
    scratch="$(create_build_scratch)"
    [[ "$scratch" =~ ^/var/tmp/genus-a03c-build\.[0-9a-f]{24}$ ]] \
        || fail "Build-Scratch liegt nicht unter dem fixen /var/tmp-Root" 70
    cleanup_build_scratch() {
        local status=$?
        trap - EXIT
        set +e
        if [[ "$scratch" =~ ^/var/tmp/genus-a03c-build\.[0-9a-f]{24}$ ]]; then
            as_root "$ROOT_RM_BIN" -rf -- "$scratch"
            as_root "$ROOT_SYNC_BIN" -f /var/tmp
        fi
        exit "$status"
    }
    trap cleanup_build_scratch EXIT
    as_root "$ROOT_CHMOD_BIN" 0711 "$scratch"
    as_root "$ROOT_INSTALL_BIN" -d -o root -g root -m 0555 "$scratch/input"
    as_root "$ROOT_CP_BIN" -a -- "$sources" "$scratch/input/sources"
    as_root "$ROOT_CP_BIN" -a -- "$backends" "$scratch/input/backends"
    as_root "$ROOT_INSTALL_BIN" -o root -g root -m 0444 "$lock" "$scratch/input/requirements.lock"
    as_root "$ROOT_CHOWN_BIN" -R root:root "$scratch/input"
    as_root "$ROOT_FIND_BIN" "$scratch/input" -type d -exec "$ROOT_CHMOD_BIN" 0555 {} +
    as_root "$ROOT_FIND_BIN" "$scratch/input" -type f -exec "$ROOT_CHMOD_BIN" 0444 {} +
    root_artifact_inventory "$scratch/input/sources" "$scratch/sources.sha256"
    root_artifact_inventory "$scratch/input/backends" "$scratch/backends.sha256"
    as_root "$ROOT_CMP_BIN" -s -- "$scratch/sources.sha256" "${prefix}-sources.sha256" \
        || fail "Sandbox-Source-Copy driftete" 70
    as_root "$ROOT_CMP_BIN" -s -- "$scratch/backends.sha256" "${prefix}-backends.sha256" \
        || fail "Sandbox-Backend-Copy driftete" 70
    as_root "$ROOT_INSTALL_BIN" -d -o nobody -g nogroup -m 0700 "$scratch/work" "$scratch/work/home" "$scratch/output"
    sandbox_canary "$scratch"
    sandbox_run "$scratch" "$RUNTIME_PREFIX/bin/python3.13" -I -P -m venv "$scratch/work/builder"
    sandbox_run "$scratch" "$scratch/work/builder/bin/python" -I -P -m pip install \
        --disable-pip-version-check --no-input --no-cache-dir --no-index \
        --find-links "$scratch/input/backends" "pip==$PIP_VERSION" "setuptools==$SETUPTOOLS_VERSION" wheel
    sandbox_run "$scratch" "$scratch/work/builder/bin/python" -I -P -m pip wheel \
        --disable-pip-version-check --no-input --no-cache-dir --no-index \
        --find-links "$scratch/input/sources" --find-links "$scratch/input/backends" \
        --no-deps --wheel-dir "$scratch/output" -r "$scratch/input/requirements.lock"
    root_artifact_inventory "$scratch/output" "$scratch/output.sha256"
    as_root "$ROOT_CHOWN_BIN" -R root:root "$scratch/output"
    as_root "$ROOT_FIND_BIN" "$scratch/output" -type f -exec "$ROOT_CHMOD_BIN" 0444 {} +
    durably_sync_tree "$scratch/output"
    install -d -m 0700 "$wheelhouse"
    as_root "$ROOT_CP_BIN" -a -- "$scratch/output/." "$wheelhouse/"
    as_root "$ROOT_CHOWN_BIN" -R "$(id -u):$(id -g)" "$wheelhouse"
    chmod 0400 "$wheelhouse"/*; chmod 0500 "$wheelhouse"
    verify_inventory="$(mktemp "$STATE_ROOT/wheel-output.verify.XXXXXX")"
    artifact_inventory "$wheelhouse" "$verify_inventory"
    as_root "$ROOT_CMP_BIN" -s -- "$scratch/output.sha256" "$verify_inventory" \
        || fail "Wheel-Output driftete beim Rueckkopieren aus Sandbox" 70
    rm -f -- "$verify_inventory"
    as_root "$ROOT_RM_BIN" -rf -- "$scratch"
    as_root "$ROOT_SYNC_BIN" -f /var/tmp
    scratch=""
    trap - EXIT
)

install_offline_lock() {
    local python="$1" lock="$2" wheelhouse="$3"
    clean_pip "$python" "${python}.pip-home" install --no-index --no-deps \
        --find-links "$wheelhouse" -r "$lock"
}

tree_inventory() {
    local set="$1" target="$2"
    "$set/core/bin/python" - "$set" "$target" <<'PY'
import hashlib, os, pathlib, sys
root, output = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2])
excluded = {"manifest.json", "tree.inventory"}
rows = []
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root).as_posix()
    if relative in excluded:
        continue
    info = path.lstat()
    if path.is_symlink():
        rows.append(f"L {relative} {os.readlink(path)}")
    elif path.is_file():
        rows.append(f"F {relative} {hashlib.sha256(path.read_bytes()).hexdigest()}")
    elif path.is_dir():
        rows.append(f"D {relative}")
    else:
        raise SystemExit("unexpected filesystem object in runtime set")
output.write_text("\n".join(rows) + "\n")
PY
}

seal_set_modes() {
    local set="$1" file
    find "$set" -type d -exec chmod 0500 {} +
    while IFS= read -r -d '' file; do
        if [ -x "$file" ]; then chmod 0500 "$file"; else chmod 0400 "$file"; fi
    done < <(find "$set" -type f -print0)
}

write_manifest() {
    local set="$1" manifest="$2" commit="$3" core_hash="$4" embed_hash="$5" probe="$6"
    local core_wheels="$7" embed_wheels="$8" core_sources="$9" embed_sources="${10}"
    local core_backends="${11}" embed_backends="${12}" tree_hash="${13}" repo_tree="${14}"
    local bootstrap_hash runtime_inventory_hash runtime_python_hash runtime_stdlib_hash runtime_tree_hash
    bootstrap_hash="$(sha256_file "$RUNTIME_PREFIX/share/genus/BUILD-BOOTSTRAP.lock")"
    runtime_inventory_hash="$(sha256_file "$RUNTIME_INVENTORY")"
    runtime_python_hash="$(runtime_inventory_field python_executable_sha256)"
    runtime_stdlib_hash="$(runtime_inventory_field stdlib_sha256)"
    runtime_tree_hash="$(runtime_inventory_field whole_tree_sha256)"
    CORE_HASH="$core_hash" EMBED_HASH="$embed_hash" PROBE="$probe" \
    CORE_WHEELS="$core_wheels" EMBED_WHEELS="$embed_wheels" TREE_HASH="$tree_hash" \
    CORE_SOURCES="$core_sources" EMBED_SOURCES="$embed_sources" \
    CORE_BACKENDS="$core_backends" EMBED_BACKENDS="$embed_backends" \
    REPO_TREE="$repo_tree" BOOTSTRAP_HASH="$bootstrap_hash" \
    RUNTIME_INVENTORY_HASH="$runtime_inventory_hash" RUNTIME_PYTHON_HASH="$runtime_python_hash" \
    RUNTIME_STDLIB_HASH="$runtime_stdlib_hash" RUNTIME_TREE_HASH="$runtime_tree_hash" \
    "$set/core/bin/python" - "$set/manifest.json.tmp" "$manifest" "$commit" <<'PY'
import json, os, pathlib, sys
probe = json.loads(os.environ["PROBE"])
data = {
    "schema": "genus-a0.3c-runtime-set-v1",
    "manifest_id": sys.argv[2],
    "repo_commit": sys.argv[3],
    "python": {
        "version": "3.13.15",
        "archive_sha256": "1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76",
        "runtime_inventory_sha256": os.environ["RUNTIME_INVENTORY_HASH"],
        "executable_sha256": os.environ["RUNTIME_PYTHON_HASH"],
        "stdlib_sha256": os.environ["RUNTIME_STDLIB_HASH"],
        "whole_tree_sha256": os.environ["RUNTIME_TREE_HASH"],
    },
    "sqlite": {
        "version": "3.53.4",
        "archive_sha3_256": "454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338",
        "source_id": "2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc",
        **probe,
    },
    "requirements": {"core_sha256": os.environ["CORE_HASH"], "embed_sha256": os.environ["EMBED_HASH"]},
    "wheel_inventories": {"core_sha256": os.environ["CORE_WHEELS"], "embed_sha256": os.environ["EMBED_WHEELS"]},
    "source_inventories": {"core_sha256": os.environ["CORE_SOURCES"], "embed_sha256": os.environ["EMBED_SOURCES"]},
    "build_backend_inventories": {"core_sha256": os.environ["CORE_BACKENDS"], "embed_sha256": os.environ["EMBED_BACKENDS"]},
    "tree_inventory_sha256": os.environ["TREE_HASH"],
    "repo_tree": os.environ["REPO_TREE"],
    "bootstrap_inventory_sha256": os.environ["BOOTSTRAP_HASH"],
}
path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
PY
    mv -- "$set/manifest.json.tmp" "$set/manifest.json"
    chmod 0600 "$set/manifest.json"
}

smoke_set() {
    local set="$1"
    "$set/core/bin/python" -m pip check
    "$set/embed/bin/python" -m pip check
    "$set/core/bin/python" -c 'import genus, llama_cpp, sqlite3; assert sqlite3.sqlite_version == "3.53.4"'
    GENUS_EMBED_MODEL="$MODEL" "$set/embed/bin/python" - <<'PY'
import os
from fastembed import TextEmbedding
model = TextEmbedding(model_name=os.environ["GENUS_EMBED_MODEL"])
vectors = list(model.embed(["bereit"]))
assert len(vectors) == 1 and len(vectors[0]) > 0
PY
}

verify_set() {
    local manifest="$1" set manifest_file tmp probe canonical_sets canonical_set
    safe_manifest_id "$manifest"
    set="$(set_path "$manifest")"
    [ ! -L "$SETS_ROOT" ] && [ ! -L "$set" ] && [ ! -L "$set/core" ] && [ ! -L "$set/embed" ] \
        || fail "Set-/Rollenpfad darf kein Symlink sein" 65
    canonical_sets="$(realpath -e -- "$SETS_ROOT")"; canonical_set="$(realpath -e -- "$set")"
    [ "$canonical_sets" = "$SETS_ROOT" ] && [ "$canonical_set" = "$SETS_ROOT/$manifest" ] \
        || fail "Set ist nicht kanonisch strikt unter SETS_ROOT" 65
    [ "$(dirname "$(realpath -e -- "$set/core")")" = "$canonical_set" ] \
        && [ "$(dirname "$(realpath -e -- "$set/embed")")" = "$canonical_set" ] \
        || fail "Core-/Embed-Rolle entkommt dem kanonischen Set" 65
    manifest_file="$set/manifest.json"
    [ -f "$manifest_file" ] && [ -x "$set/core/bin/python" ] && [ -x "$set/embed/bin/python" ] \
        || fail "Set ist unvollstaendig" 65
    [ "$(stat -c %U "$set")" = "$GENUS_USER" ] || fail "Set hat falschen Owner" 65
    [ -z "$(find "$set" -xdev ! -user "$GENUS_USER" -print -quit)" ] || fail "Set enthaelt fremden Owner" 65
    [ -z "$(find "$set" -xdev -type f -perm /222 -print -quit)" ] || fail "Set-Datei ist nach Stage schreibbar" 65
    [ -z "$(find "$set" -xdev -type d -perm /222 -print -quit)" ] || fail "Set-Verzeichnis ist nach Stage schreibbar" 65
    verify_runtime_prefix
    probe="$(runtime_probe "$set/core/bin/python" "$set/core/bin/python")"
    runtime_probe "$set/embed/bin/python" "$set/embed/bin/python" >/dev/null
    "$set/core/bin/python" - "$manifest_file" "$manifest" "$(repo_commit)" "$probe" \
        "$("$GIT_BIN" -C "$REPO_DIR" rev-parse 'HEAD^{tree}')" \
        "$(sha256_file "$RUNTIME_PREFIX/share/genus/BUILD-BOOTSTRAP.lock")" \
        "$(sha256_file "$RUNTIME_INVENTORY")" \
        "$(runtime_inventory_field python_executable_sha256)" \
        "$(runtime_inventory_field stdlib_sha256)" \
        "$(runtime_inventory_field whole_tree_sha256)" <<'PY'
import hashlib, json, pathlib, sys
path, expected_id, commit, probe = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
repo_tree, bootstrap_hash, runtime_inventory_hash, runtime_python_hash, runtime_stdlib_hash, runtime_tree_hash = sys.argv[5:11]
data = json.loads(path.read_text())
if data["schema"] != "genus-a0.3c-runtime-set-v1" or data["manifest_id"] != expected_id:
    raise SystemExit("manifest identity mismatch")
if data.get("python") != {
    "version":"3.13.15",
    "archive_sha256":"1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76",
    "runtime_inventory_sha256":runtime_inventory_hash,
    "executable_sha256":runtime_python_hash,
    "stdlib_sha256":runtime_stdlib_hash,
    "whole_tree_sha256":runtime_tree_hash,
}:
    raise SystemExit("python pin differs")
if any(data.get("sqlite", {}).get(key) != value for key, value in {
    "version":"3.53.4",
    "archive_sha3_256":"454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338",
    "source_id":"2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc",
}.items()):
    raise SystemExit("sqlite pin differs")
if data["repo_commit"] != commit or any(data["sqlite"].get(k) != v for k, v in probe.items()):
    raise SystemExit("manifest runtime/commit mismatch")
if data.get("repo_tree") != repo_tree or data.get("bootstrap_inventory_sha256") != bootstrap_hash:
    raise SystemExit("manifest source/bootstrap binding differs")
for name in ("core", "embed"):
    payload = (path.parent / f"requirements-{name}.lock").read_bytes()
    if hashlib.sha256(payload).hexdigest() != data["requirements"][f"{name}_sha256"]:
        raise SystemExit("requirements hash mismatch")
    wheels = (path.parent / f"wheels-{name}.sha256").read_bytes()
    if hashlib.sha256(wheels).hexdigest() != data["wheel_inventories"][f"{name}_sha256"]:
        raise SystemExit("wheel inventory hash mismatch")
    sources = (path.parent / f"sources-{name}.sha256").read_bytes()
    if hashlib.sha256(sources).hexdigest() != data["source_inventories"][f"{name}_sha256"]:
        raise SystemExit("source inventory hash mismatch")
    backends = (path.parent / f"backends-{name}.sha256").read_bytes()
    if hashlib.sha256(backends).hexdigest() != data["build_backend_inventories"][f"{name}_sha256"]:
        raise SystemExit("build-backend inventory hash mismatch")
tree = (path.parent / "tree.inventory").read_bytes()
if hashlib.sha256(tree).hexdigest() != data["tree_inventory_sha256"]:
    raise SystemExit("tree inventory hash mismatch")
probe_fields = {key: data["sqlite"][key] for key in ("compile_options_sha256", "sqlite_extension_sha256", "sqlite_library_sha256")}
probe_hash = hashlib.sha256(json.dumps(probe_fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
seed = (
    f"commit={commit}\n"
    f"tree={repo_tree}\n"
    f"python={data['python']['archive_sha256']}\n"
    f"sqlite={data['sqlite']['archive_sha3_256']}\n"
    f"core={data['requirements']['core_sha256']}\n"
    f"embed={data['requirements']['embed_sha256']}\n"
    f"core_wheels={data['wheel_inventories']['core_sha256']}\n"
    f"embed_wheels={data['wheel_inventories']['embed_sha256']}\n"
    f"core_sources={data['source_inventories']['core_sha256']}\n"
    f"embed_sources={data['source_inventories']['embed_sha256']}\n"
    f"core_backends={data['build_backend_inventories']['core_sha256']}\n"
    f"embed_backends={data['build_backend_inventories']['embed_sha256']}\n"
    f"runtime_inventory={runtime_inventory_hash}\n"
    f"runtime_python={runtime_python_hash}\n"
    f"runtime_stdlib={runtime_stdlib_hash}\n"
    f"runtime_tree={runtime_tree_hash}\n"
    f"bootstrap={bootstrap_hash}\n"
    f"probe={probe_hash}\n"
)
if hashlib.sha256(seed.encode()).hexdigest() != expected_id:
    raise SystemExit("manifest id is not reproducible from bound inputs")
PY
    tmp="$(mktemp -d "$STATE_ROOT/verify.XXXXXX")"
    inventory_for_compare "$set/core/bin/python" one "$tmp/core.lock"
    inventory_for_compare "$set/embed/bin/python" none "$tmp/embed.lock"
    cmp -s "$tmp/core.lock" "$set/requirements-core.lock" || fail "Core-Inventar driftet" 65
    cmp -s "$tmp/embed.lock" "$set/requirements-embed.lock" || fail "Embed-Inventar driftet" 65
    (cd "$set/wheelhouse-core" && sha256sum -c ../wheels-core.sha256 >/dev/null) \
        || fail "Core-Wheelhouse driftet" 65
    (cd "$set/wheelhouse-embed" && sha256sum -c ../wheels-embed.sha256 >/dev/null) \
        || fail "Embed-Wheelhouse driftet" 65
    (cd "$set/sources-core" && sha256sum -c ../sources-core.sha256 >/dev/null) \
        || fail "Core-Quellartefakte driften" 65
    (cd "$set/sources-embed" && sha256sum -c ../sources-embed.sha256 >/dev/null) \
        || fail "Embed-Quellartefakte driften" 65
    (cd "$set/backends-core" && sha256sum -c ../backends-core.sha256 >/dev/null) \
        || fail "Core-Build-Backends driften" 65
    (cd "$set/backends-embed" && sha256sum -c ../backends-embed.sha256 >/dev/null) \
        || fail "Embed-Build-Backends driften" 65
    tree_inventory "$set" "$tmp/tree.inventory"
    cmp -s "$tmp/tree.inventory" "$set/tree.inventory" || fail "Set-Dateibaum driftet" 65
    "$set/core/bin/python" - "$set" "$RUNTIME_PREFIX" <<'PY'
import pathlib, sys
root, runtime = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve()
for link in root.rglob("*"):
    if not link.is_symlink():
        continue
    resolved = link.resolve(strict=True)
    if resolved != runtime and root not in resolved.parents and runtime not in resolved.parents:
        raise SystemExit("set symlink escapes both set and pinned runtime")
PY
    rm -rf -- "$tmp"
    smoke_set "$set"
    printf '%s\n' "$manifest"
}

verify_legacy_set() {
    local manifest="$1" set core_target embed_target tmp core_hash embed_hash tree_hash runtime_hash seed
    [[ "$manifest" =~ ^legacy-[a-f0-9]{64}$ ]] || fail "ungueltige Legacy-ID" 65
    set="$SETS_ROOT/$manifest"
    [ -L "$set/core" ] && [ -L "$set/embed" ] || fail "Legacy-Set ist unvollstaendig" 65
    core_target="${CORE_POINTER}.a03c-${manifest}"
    embed_target="${EMBED_POINTER}.a03c-${manifest}"
    [ "$(readlink "$set/core")" = "$core_target" ] \
        && [ "$(readlink "$set/embed")" = "$embed_target" ] \
        || fail "Legacy-Set zeigt nicht auf das gebundene Venv-Paar" 65
    [ -x "$set/core/bin/python" ] && [ -x "$set/core/bin/genus" ] && [ -x "$set/embed/bin/python" ] \
        || fail "Legacy-Venv-Paar ist nicht lauffaehig" 65
    [ -z "$(find -L "$set/core" "$set/embed" -xdev -perm /222 -print -quit)" ] \
        || fail "Legacy-Venv-Paar ist nicht unveraenderlich" 65
    "$set/core/bin/python" -m pip check
    "$set/embed/bin/python" -m pip check
    tmp="$(mktemp -d "$STATE_ROOT/legacy-verify.XXXXXX")"
    "$set/core/bin/python" -m pip freeze --all > "$tmp/core.raw"
    "$set/embed/bin/python" -m pip freeze --all > "$tmp/embed.raw"
    normalize_legacy_freeze "$tmp/core.raw" "$tmp/core.lock" one
    normalize_legacy_freeze "$tmp/embed.raw" "$tmp/embed.lock" none
    cmp -s "$tmp/core.lock" "$set/requirements-core.lock" || fail "Legacy-Core-Lock driftet" 65
    cmp -s "$tmp/embed.lock" "$set/requirements-embed.lock" || fail "Legacy-Embed-Lock driftet" 65
    legacy_tree_inventory "$set/core" "$set/embed" "$tmp/tree.inventory"
    legacy_runtime_inventory "$set/core/bin/python" "$tmp/runtime.json"
    cmp -s "$tmp/tree.inventory" "$set/tree.inventory" || fail "Legacy-Dateibaum driftet" 65
    cmp -s "$tmp/runtime.json" "$set/runtime.json" || fail "Legacy-Runtime driftet" 65
    core_hash="$(sha256_file "$tmp/core.lock")"; embed_hash="$(sha256_file "$tmp/embed.lock")"
    tree_hash="$(sha256_file "$tmp/tree.inventory")"; runtime_hash="$(sha256_file "$tmp/runtime.json")"
    seed="core=$core_hash\nembed=$embed_hash\ntree=$tree_hash\nruntime=$runtime_hash\n"
    [ "legacy-$(printf '%b' "$seed" | sha256sum | awk '{print $1}')" = "$manifest" ] \
        || fail "Legacy-Manifest-ID ist nicht reproduzierbar" 65
    "$set/core/bin/python" - "$set/manifest.json" "$manifest" "$core_hash" "$embed_hash" "$tree_hash" "$runtime_hash" <<'PY'
import json, pathlib, sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
expected={"schema":"genus-a0.3c-legacy-set-v1","manifest_id":sys.argv[2],"requirements":{"core_sha256":sys.argv[3],"embed_sha256":sys.argv[4]},"tree_inventory_sha256":sys.argv[5],"runtime_inventory_sha256":sys.argv[6]}
if data != expected: raise SystemExit("legacy manifest binding differs")
PY
    rm -rf -- "$tmp"
    printf '%s\n' "$manifest"
}

verify_target() {
    case "$1" in
        legacy-*) verify_legacy_set "$1" ;;
        *) verify_set "$1" ;;
    esac
}

write_set_publication_marker() {
    local manifest="$1" marker="$SETS_ROOT/.building-$1"
    safe_manifest_id "$manifest"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$marker" "$manifest" "$SETS_ROOT/$manifest" <<'PY'
import json, os, pathlib, sys
path = pathlib.Path(sys.argv[1])
payload = {"schema":"genus-a0.3c-set-publication-v1","manifest_id":sys.argv[2],"set_path":sys.argv[3]}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
try:
    os.write(fd, (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode())
    os.fsync(fd)
finally:
    os.close(fd)
parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try: os.fsync(parent)
finally: os.close(parent)
PY
}

validate_set_publication_marker() {
    local manifest="$1" marker="$SETS_ROOT/.building-$1"
    safe_manifest_id "$manifest"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$marker" "$manifest" "$SETS_ROOT/$manifest" "$(id -u)" <<'PY'
import json, pathlib, stat, sys
path = pathlib.Path(sys.argv[1]); info = path.lstat()
if not stat.S_ISREG(info.st_mode) or info.st_uid != int(sys.argv[4]) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
    raise SystemExit("set publication marker is not user-owned/0600/single-link")
data = json.loads(path.read_text())
expected = {"schema":"genus-a0.3c-set-publication-v1","manifest_id":sys.argv[2],"set_path":sys.argv[3]}
if data != expected: raise SystemExit("set publication marker binding differs")
PY
}

set_is_referenced() {
    local manifest="$1" link target
    for link in "$ACTIVE_LINK" "$PREVIOUS_LINK" "$STAGED_LINK"; do
        [ -L "$link" ] || continue
        target="$(readlink "$link")"
        [ "$target" != "sets/$manifest" ] || return 0
    done
    return 1
}

quarantine_set() {
    local manifest="$1" set="$SETS_ROOT/$1" quarantine
    set_is_referenced "$manifest" \
        && fail "ungueltiges Set ist noch durch einen Selector referenziert" 70
    quarantine="$SETS_ROOT/.failed-$manifest-$(date -u +%Y%m%dT%H%M%S%N)-$$-$RANDOM"
    [ ! -e "$quarantine" ] || fail "Set-Quarantaene kollidiert" 70
    mv -T -- "$set" "$quarantine"
    fsync_dir "$SETS_ROOT"
}

recover_set_publication() {
    local manifest="$1" set="$SETS_ROOT/$1" marker="$SETS_ROOT/.building-$1" status
    safe_manifest_id "$manifest"
    if [ -e "$marker" ] || [ -L "$marker" ]; then
        validate_set_publication_marker "$manifest" \
            || fail "Set-Publikationsmarker ist ungueltig" 70
        if [ ! -e "$set" ]; then
            return 10
        fi
        set +e
        ( set -Eeuo pipefail; verify_set "$manifest" >/dev/null )
        status=$?
        set -e
        if [ "$status" -eq 0 ]; then
            durably_sync_tree "$set"
            fsync_dir "$SETS_ROOT"
            rm -f -- "$marker"
            fsync_dir "$SETS_ROOT"
            return 0
        fi
        quarantine_set "$manifest"
        rm -f -- "$marker"
        fsync_dir "$SETS_ROOT"
        return 10
    fi
    if [ -e "$set" ] || [ -L "$set" ]; then
        set +e
        ( set -Eeuo pipefail; verify_set "$manifest" >/dev/null )
        status=$?
        set -e
        [ "$status" -ne 0 ] || return 0
        quarantine_set "$manifest"
    fi
    return 10
}

stage_set() (
    local expected_supply="${1:-}" supply_seed supply_seal
    local work commit repo_tree core_hash embed_hash seed manifest set building probe probe_hash
    local core_wheels embed_wheels core_sources embed_sources core_backends embed_backends
    local runtime_inventory_hash runtime_python_hash runtime_stdlib_hash runtime_tree_hash
    local tree_hash bootstrap_hash quarantine recovery_status
    exec 3>&1 1>&2
    init_user_roots
    acquire_operator_lock
    require_command "$FUSER_BIN"
    recover_pending_activation
    # Reste eines per SIGKILL/Stromausfall abgebrochenen Sandbox-Baus gehoeren dem
    # root-Benutzer; der EXIT-Trap des Sandbox-Baus hat sie dann nie erreicht.
    recover_stale_build_scratch
    recover_stale_state_builds
    assert_expected_commit "$(repo_commit)"
    # Auch bei bereits vorhandenem Prefix kann ein Publikationsmarker offen sein
    # (Abbruch zwischen Rename und Markerentfernung); Recovery laeuft deshalb in
    # beiden Zweigen und nicht nur im Neubau.
    recover_runtime_publication
    # Quarantaene statt Reparatur: Eine vorgefundene Runtime, die die Verifikation
    # nicht besteht, wird beiseitegelegt und neu gebaut, statt den Lauf blockiert
    # zurueckzulassen (sonst braeuchte jeder Fehlversuch eine root-Handaufraeumung).
    if [ -e "$RUNTIME_PREFIX" ] && ( verify_runtime_prefix ); then
        :
    else
        if [ -e "$RUNTIME_PREFIX" ]; then
            quarantine_runtime_path "$RUNTIME_PREFIX" "vorgefundene Runtime besteht die Verifikation nicht"
        fi
        build_runtime
    fi
    work="$(mktemp -d "$STATE_ROOT/stage.XXXXXX")"
    trap 'rm -rf -- "$work"' EXIT
    capture_locks "$work"
    commit="$(repo_commit)"
    repo_tree="$("$GIT_BIN" -C "$REPO_DIR" rev-parse 'HEAD^{tree}')"
    core_hash="$(sha256_file "$work/core.lock")"
    embed_hash="$(sha256_file "$work/embed.lock")"
    prepare_wheelhouse_inputs "$work/core.lock" "$work/wheelhouse-core" "$work/builder-core" \
        "$work/sources-core" "$work/backends-core" "$work/core"
    prepare_wheelhouse_inputs "$work/embed.lock" "$work/wheelhouse-embed" "$work/builder-embed" \
        "$work/sources-embed" "$work/backends-embed" "$work/embed"
    supply_seed="index=$PYPI_INDEX_URL\ncore_lock=$(sha256_file "$work/core.lock")\nembed_lock=$(sha256_file "$work/embed.lock")\ncore_sources=$(sha256_file "$work/core-sources.sha256")\nembed_sources=$(sha256_file "$work/embed-sources.sha256")\ncore_backends=$(sha256_file "$work/core-backends.sha256")\nembed_backends=$(sha256_file "$work/embed-backends.sha256")\n"
    supply_seal="$(printf '%b' "$supply_seed" | sha256sum | awk '{print $1}')"
    printf '[A0.3c] SUPPLY_SEAL=%s\n' "$supply_seal" >&2
    if [ -z "$expected_supply" ]; then
        fail "Supply wurde ohne Fremdcode-Ausfuehrung versiegelt; stage mit exakt diesem EXPECTED_SUPPLY_SEAL erneut autorisieren" 78
    fi
    [[ "$expected_supply" =~ ^[a-f0-9]{64}$ ]] \
        || fail "EXPECTED_SUPPLY_SEAL muss SHA-256 sein" 64
    [ "$expected_supply" = "$supply_seal" ] \
        || fail "Operator-Supply-Freigabe stimmt nicht mit der frischen versiegelten Akquise ueberein" 65
    verify_artifact_store "$work/sources-core" "$work/core-sources.sha256"
    verify_artifact_store "$work/sources-embed" "$work/embed-sources.sha256"
    verify_artifact_store "$work/backends-core" "$work/core-backends.sha256"
    verify_artifact_store "$work/backends-embed" "$work/embed-backends.sha256"
    publication_fault_point after-supply-authorization
    build_wheelhouse "$work/core.lock" "$work/wheelhouse-core" "$work/builder-core" \
        "$work/sources-core" "$work/backends-core" "$work/core"
    build_wheelhouse "$work/embed.lock" "$work/wheelhouse-embed" "$work/builder-embed" \
        "$work/sources-embed" "$work/backends-embed" "$work/embed"
    assert_expected_commit "$commit"
    wheel_inventory "$work/wheelhouse-core" "$work/wheels-core.sha256"
    wheel_inventory "$work/wheelhouse-embed" "$work/wheels-embed.sha256"
    core_wheels="$(sha256_file "$work/wheels-core.sha256")"
    embed_wheels="$(sha256_file "$work/wheels-embed.sha256")"
    core_sources="$(sha256_file "$work/core-sources.sha256")"
    embed_sources="$(sha256_file "$work/embed-sources.sha256")"
    core_backends="$(sha256_file "$work/core-backends.sha256")"
    embed_backends="$(sha256_file "$work/embed-backends.sha256")"
    bootstrap_hash="$(sha256_file "$RUNTIME_PREFIX/share/genus/BUILD-BOOTSTRAP.lock")"
    runtime_inventory_hash="$(sha256_file "$RUNTIME_INVENTORY")"
    runtime_python_hash="$(runtime_inventory_field python_executable_sha256)"
    runtime_stdlib_hash="$(runtime_inventory_field stdlib_sha256)"
    runtime_tree_hash="$(runtime_inventory_field whole_tree_sha256)"
    probe="$(runtime_probe "$RUNTIME_PREFIX/bin/python3.13" "$RUNTIME_PREFIX/bin/python3.13")"
    probe_hash="$(printf '%s' "$probe" | sha256sum | awk '{print $1}')"
    seed="commit=$commit\ntree=$repo_tree\npython=$PYTHON_SHA256\nsqlite=$SQLITE_SHA3_256\ncore=$core_hash\nembed=$embed_hash\ncore_wheels=$core_wheels\nembed_wheels=$embed_wheels\ncore_sources=$core_sources\nembed_sources=$embed_sources\ncore_backends=$core_backends\nembed_backends=$embed_backends\nruntime_inventory=$runtime_inventory_hash\nruntime_python=$runtime_python_hash\nruntime_stdlib=$runtime_stdlib_hash\nruntime_tree=$runtime_tree_hash\nbootstrap=$bootstrap_hash\nprobe=$probe_hash\n"
    manifest="$(printf '%b' "$seed" | sha256sum | awk '{print $1}')"
    set="$(set_path "$manifest")"
    building="$SETS_ROOT/.building-$manifest"
    set +e
    ( set -Eeuo pipefail; recover_set_publication "$manifest" )
    recovery_status=$?
    set -e
    case "$recovery_status" in
    0) ;;
    10)
        if [ ! -e "$building" ]; then
            write_set_publication_marker "$manifest"
        else
            validate_set_publication_marker "$manifest"
        fi
        publication_fault_point after-set-marker
        install -d -m 0700 "$set"
        cp -a -- "$work/wheelhouse-core" "$set/wheelhouse-core"
        cp -a -- "$work/wheelhouse-embed" "$set/wheelhouse-embed"
        cp -a -- "$work/sources-core" "$set/sources-core"
        cp -a -- "$work/sources-embed" "$set/sources-embed"
        cp -a -- "$work/backends-core" "$set/backends-core"
        cp -a -- "$work/backends-embed" "$set/backends-embed"
        install -m 0600 "$work/wheels-core.sha256" "$set/wheels-core.sha256"
        install -m 0600 "$work/wheels-embed.sha256" "$set/wheels-embed.sha256"
        install -m 0600 "$work/core-sources.sha256" "$set/sources-core.sha256"
        install -m 0600 "$work/embed-sources.sha256" "$set/sources-embed.sha256"
        install -m 0600 "$work/core-backends.sha256" "$set/backends-core.sha256"
        install -m 0600 "$work/embed-backends.sha256" "$set/backends-embed.sha256"
        "$RUNTIME_PREFIX/bin/python3.13" -m venv "$set/core"
        "$RUNTIME_PREFIX/bin/python3.13" -m venv "$set/embed"
        install_offline_lock "$set/core/bin/python" "$work/core.lock" "$set/wheelhouse-core"
        install_offline_lock "$set/embed/bin/python" "$work/embed.lock" "$set/wheelhouse-embed"
        assert_expected_commit "$commit"
        clean_pip "$set/core/bin/python" "$work/editable-pip-home" install \
            --no-index --no-build-isolation --no-deps -e "$REPO_DIR"
        assert_expected_commit "$commit"
        publication_fault_point after-set-populate
        install -m 0600 "$work/core.lock" "$set/requirements-core.lock"
        install -m 0600 "$work/embed.lock" "$set/requirements-embed.lock"
        probe="$(runtime_probe "$set/core/bin/python" "$set/core/bin/python")"
        tree_inventory "$set" "$set/tree.inventory"
        tree_hash="$(sha256_file "$set/tree.inventory")"
        write_manifest "$set" "$manifest" "$commit" "$core_hash" "$embed_hash" "$probe" \
            "$core_wheels" "$embed_wheels" "$core_sources" "$embed_sources" \
            "$core_backends" "$embed_backends" "$tree_hash" "$repo_tree"
        seal_set_modes "$set"
        durably_sync_tree "$set"
        fsync_dir "$SETS_ROOT"
        publication_fault_point after-set-seal
        verify_set "$manifest" >/dev/null
        publication_fault_point after-set-verify
        rm -f -- "$building"
        fsync_dir "$SETS_ROOT"
        publication_fault_point after-set-finalize
        ;;
    *) fail "Set-Publikationsrecovery scheiterte" "$recovery_status" ;;
    esac
    verify_set "$manifest" >/dev/null
    atomic_link "sets/$manifest" "$STAGED_LINK"
    rm -rf -- "$work"
    trap - EXIT
    printf '%s\n' "$manifest" >&3
)

resolve_manifest() {
    local requested="${1:-active}" target manifest
    case "$requested" in
        active) target="$(readlink "$ACTIVE_LINK" 2>/dev/null || true)" ;;
        staged) target="$(readlink "$STAGED_LINK" 2>/dev/null || true)" ;;
        *) printf '%s\n' "$requested"; return ;;
    esac
    [ -n "$target" ] || fail "$requested ist nicht gesetzt" 65
    manifest="${target##*/}"
    safe_manifest_id "$manifest"
    [ "$target" = "sets/$manifest" ] || fail "$requested-Selector hat kein exaktes Set-Ziel" 65
    printf '%s\n' "$manifest"
}

pointer_dir_valid() {
    local pointer="$1" role="$2" name expected_role
    [ -d "$pointer" ] && [ ! -L "$pointer" ] \
        && [ "$(realpath -e -- "$pointer" 2>/dev/null)" = "$pointer" ] \
        && [ "$(stat -c %u "$pointer" 2>/dev/null)" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$pointer" 2>/dev/null)" = 700 ] \
        || return 1
    [ -f "$pointer/.a03c-pointer-unit" ] && [ ! -L "$pointer/.a03c-pointer-unit" ] \
        && [ "$(stat -c %u "$pointer/.a03c-pointer-unit" 2>/dev/null)" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$pointer/.a03c-pointer-unit" 2>/dev/null)" = 600 ] \
        && [ "$(stat -c %h "$pointer/.a03c-pointer-unit" 2>/dev/null)" -eq 1 ] \
        && [ "$(cat "$pointer/.a03c-pointer-unit")" = genus-a0.3c-pointer-v1 ] \
        || return 1
    [ -L "$pointer/current" ] \
        && [ "$(readlink "$pointer/current")" = "$STATE_ROOT/active/$role" ] \
        || return 1
    expected_role="$(readlink -f "$STATE_ROOT/active/$role" 2>/dev/null)" \
        || return 1
    [ "$(readlink -f "$pointer/current" 2>/dev/null)" = "$expected_role" ] || return 1
    for name in bin lib include pyvenv.cfg lib64; do
        [ -L "$pointer/$name" ] && [ "$(readlink "$pointer/$name")" = "current/$name" ] \
            || return 1
    done
}

create_pointer_dir() {
    local pointer="$1" role="$2"
    install -d -m 0700 "$pointer"
    fsync_dir "$(dirname "$pointer")"
    printf '%s\n' 'genus-a0.3c-pointer-v1' > "$pointer/.a03c-pointer-unit"
    chmod 0600 "$pointer/.a03c-pointer-unit"
    sync -f "$pointer/.a03c-pointer-unit"
    ln -s -- "$STATE_ROOT/active/$role" "$pointer/current"
    for name in bin lib include pyvenv.cfg lib64; do ln -s -- "current/$name" "$pointer/$name"; done
    fsync_dir "$pointer"
}

durably_sync_tree() {
    local root="$1"
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$root" <<'PY'
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1])
root_info = root.lstat()
if not stat.S_ISDIR(root_info.st_mode) or root.is_symlink():
    raise SystemExit("durable tree root is not a real directory")
directories = []
for directory, names, files in os.walk(root, topdown=True, followlinks=False):
    base = pathlib.Path(directory)
    directories.append(base)
    for name in names + files:
        path = base / name
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            continue
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise SystemExit("durable tree contains a special filesystem object")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
for directory in reversed(directories):
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
PY
}

MIGRATION_PHASE=0
MIGRATION_CORE_BACKUP=""
MIGRATION_EMBED_BACKUP=""
MIGRATION_LEGACY_SET=""
MIGRATION_CAPTURE=""

rollback_incomplete_migration() {
    local result=0
    set +e
    [ "$MIGRATION_PHASE" -gt 0 ] || return 0
    if [ "$MIGRATION_PHASE" -ge 3 ]; then
        rm -rf -- "$CORE_POINTER" || result=70
        rm -rf -- "$EMBED_POINTER" || result=70
        fsync_dir "$(dirname "$CORE_POINTER")" || result=70
        fsync_dir "$(dirname "$EMBED_POINTER")" || result=70
    fi
    if [ "$MIGRATION_PHASE" -ge 2 ] && [ -d "$MIGRATION_EMBED_BACKUP" ] && [ ! -e "$EMBED_POINTER" ]; then
        mv -T -- "$MIGRATION_EMBED_BACKUP" "$EMBED_POINTER" || result=70
        fsync_dir "$(dirname "$EMBED_POINTER")" || result=70
        [ -d "$EMBED_POINTER" ] && [ ! -e "$MIGRATION_EMBED_BACKUP" ] || result=70
    fi
    if [ "$MIGRATION_PHASE" -ge 1 ] && [ -d "$MIGRATION_CORE_BACKUP" ] && [ ! -e "$CORE_POINTER" ]; then
        mv -T -- "$MIGRATION_CORE_BACKUP" "$CORE_POINTER" || result=70
        fsync_dir "$(dirname "$CORE_POINTER")" || result=70
        [ -d "$CORE_POINTER" ] && [ ! -e "$MIGRATION_CORE_BACKUP" ] || result=70
    fi
    [ "$result" -eq 0 ] || return "$result"
    if [ -n "$MIGRATION_LEGACY_SET" ]; then
        chmod -R u+w "$MIGRATION_LEGACY_SET" 2>/dev/null || true
        rm -rf -- "$MIGRATION_LEGACY_SET" || return 70
        fsync_dir "$SETS_ROOT" || return 70
    fi
    rm -f -- "$STATE_ROOT/migration.pending" || return 70
    fsync_dir "$STATE_ROOT" || return 70
    [ -z "$MIGRATION_CAPTURE" ] || rm -rf -- "$MIGRATION_CAPTURE"
    MIGRATION_PHASE=0
    return 0
}

recover_incomplete_migration() {
    local journal="$STATE_ROOT/migration.pending" legacy core_backup embed_backup
    [ -f "$journal" ] || return 0
    IFS= read -r legacy < "$journal"
    [[ "$legacy" =~ ^legacy-[a-f0-9]{64}$ ]] || fail "Migration-Journal ist ungueltig" 70
    core_backup="${CORE_POINTER}.a03c-${legacy}"
    embed_backup="${EMBED_POINTER}.a03c-${legacy}"
    if pointer_dir_valid "$CORE_POINTER" core && pointer_dir_valid "$EMBED_POINTER" embed \
        && [ "$(readlink "$ACTIVE_LINK" 2>/dev/null || true)" = "sets/$legacy" ] \
        && [ "$(readlink "$PREVIOUS_LINK" 2>/dev/null || true)" = "sets/$legacy" ]; then
        verify_legacy_set "$legacy" >/dev/null
        pointer_dir_valid "$CORE_POINTER" core && pointer_dir_valid "$EMBED_POINTER" embed \
            && [ "$(selector_manifest)" = "$legacy" ] \
            && [ "$(selector_manifest "$PREVIOUS_LINK")" = "$legacy" ] \
            || fail "abgeschlossene Legacy-Migration driftet vor Journalabschluss" 70
        rm -f -- "$journal"
        fsync_dir "$STATE_ROOT"
        return 0
    fi
    if [ -f "$CORE_POINTER/.a03c-pointer-unit" ]; then
        rm -rf -- "$CORE_POINTER"; fsync_dir "$(dirname "$CORE_POINTER")"
    fi
    if [ -f "$EMBED_POINTER/.a03c-pointer-unit" ]; then
        rm -rf -- "$EMBED_POINTER"; fsync_dir "$(dirname "$EMBED_POINTER")"
    fi
    if [ "$(readlink "$ACTIVE_LINK" 2>/dev/null || true)" = "sets/$legacy" ]; then
        rm -f -- "$ACTIVE_LINK"
    fi
    if [ "$(readlink "$PREVIOUS_LINK" 2>/dev/null || true)" = "sets/$legacy" ]; then
        rm -f -- "$PREVIOUS_LINK"
    fi
    fsync_dir "$STATE_ROOT"
    if [ ! -e "$CORE_POINTER" ] && [ -d "$core_backup" ]; then
        mv -T -- "$core_backup" "$CORE_POINTER"
        fsync_dir "$(dirname "$CORE_POINTER")"
    fi
    if [ ! -e "$EMBED_POINTER" ] && [ -d "$embed_backup" ]; then
        mv -T -- "$embed_backup" "$EMBED_POINTER"
        fsync_dir "$(dirname "$EMBED_POINTER")"
    fi
    [ -d "$CORE_POINTER" ] && [ -d "$EMBED_POINTER" ] \
        && [ ! -e "$core_backup" ] && [ ! -e "$embed_backup" ] \
        || fail "unvollstaendige Legacy-Migration kann nicht automatisch restauriert werden" 70
    chmod -R u+w "$SETS_ROOT/$legacy" 2>/dev/null || true
    rm -rf -- "$SETS_ROOT/$legacy"
    fsync_dir "$SETS_ROOT"
    rm -f -- "$journal"
    fsync_dir "$STATE_ROOT"
}

legacy_tree_inventory() {
    local core="$1" embed="$2" target="$3"
    "$core/bin/python" - "$core" "$embed" "$target" <<'PY'
import hashlib, os, pathlib, sys
roots = {"core": pathlib.Path(sys.argv[1]), "embed": pathlib.Path(sys.argv[2])}
rows = []
for role, root in roots.items():
    for directory, names, files in os.walk(root, followlinks=False):
        base = pathlib.Path(directory)
        names.sort(); files.sort()
        for name in names + files:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                rows.append(f"L {role}/{relative} {os.readlink(path)}")
            elif path.is_file():
                rows.append(f"F {role}/{relative} {hashlib.sha256(path.read_bytes()).hexdigest()}")
            elif path.is_dir():
                rows.append(f"D {role}/{relative}")
            else:
                raise SystemExit("unexpected legacy filesystem object")
pathlib.Path(sys.argv[3]).write_text("\n".join(sorted(rows)) + "\n")
PY
}

legacy_runtime_inventory() {
    local python="$1" target="$2"
    "$python" - "$target" <<'PY'
import _sqlite3, hashlib, json, pathlib, sqlite3, sys
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
with sqlite3.connect(":memory:") as db:
    source = db.execute("select sqlite_source_id()").fetchone()[0]
mapped = sorted({line.rsplit(None, 1)[-1] for line in pathlib.Path("/proc/self/maps").read_text().splitlines() if "libsqlite3.so" in line})
data = {
    "schema":"genus-a0.3c-legacy-runtime-v1",
    "python_version":sys.version.split()[0],
    "python_binary_sha256":digest(sys._base_executable),
    "sqlite_version":sqlite3.sqlite_version,
    "sqlite_source_id":source,
    "sqlite_extension_sha256":digest(_sqlite3.__file__),
    "sqlite_library_sha256":[digest(path) for path in mapped],
}
pathlib.Path(sys.argv[1]).write_text(json.dumps(data, sort_keys=True, separators=(",", ":"))+"\n")
PY
}

prepare_legacy_pointer_unit() {
    local capture legacy_seed legacy core_lock embed_lock tree runtime
    if pointer_dir_valid "$CORE_POINTER" core && pointer_dir_valid "$EMBED_POINTER" embed; then return; fi
    [ -d "$CORE_POINTER" ] && [ ! -L "$CORE_POINTER" ] || fail "Core-Legacy-Venv ist kein echtes Verzeichnis" 65
    [ -d "$EMBED_POINTER" ] && [ ! -L "$EMBED_POINTER" ] || fail "Embed-Legacy-Venv ist kein echtes Verzeichnis" 65
    capture="$(mktemp -d "$STATE_ROOT/legacy-capture.XXXXXX")"
    MIGRATION_CAPTURE="$capture"
    "$CORE_POINTER/bin/python" -m pip freeze --all > "$capture/core.raw"
    "$EMBED_POINTER/bin/python" -m pip freeze --all > "$capture/embed.raw"
    normalize_legacy_freeze "$capture/core.raw" "$capture/core.lock" one
    normalize_legacy_freeze "$capture/embed.raw" "$capture/embed.lock" none
    rm -f -- "$capture/core.raw" "$capture/embed.raw"
    legacy_tree_inventory "$CORE_POINTER" "$EMBED_POINTER" "$capture/tree.inventory"
    legacy_runtime_inventory "$CORE_POINTER/bin/python" "$capture/runtime.json"
    core_lock="$(sha256_file "$capture/core.lock")"; embed_lock="$(sha256_file "$capture/embed.lock")"
    tree="$(sha256_file "$capture/tree.inventory")"; runtime="$(sha256_file "$capture/runtime.json")"
    legacy_seed="core=$core_lock\nembed=$embed_lock\ntree=$tree\nruntime=$runtime\n"
    legacy="legacy-$(printf '%b' "$legacy_seed" | sha256sum | awk '{print $1}')"
    MIGRATION_CORE_BACKUP="${CORE_POINTER}.a03c-${legacy}"
    MIGRATION_EMBED_BACKUP="${EMBED_POINTER}.a03c-${legacy}"
    MIGRATION_LEGACY_SET="$SETS_ROOT/$legacy"
    [ ! -e "$MIGRATION_CORE_BACKUP" ] && [ ! -e "$MIGRATION_EMBED_BACKUP" ] \
        || fail "Legacy-Backupziel existiert bereits" 70
    printf '%s\n' "$legacy" > "$STATE_ROOT/migration.pending"
    chmod 0600 "$STATE_ROOT/migration.pending"
    sync -f "$STATE_ROOT/migration.pending"; sync -f "$STATE_ROOT"
    mv -T -- "$CORE_POINTER" "$MIGRATION_CORE_BACKUP"; MIGRATION_PHASE=1
    sync -f "$(dirname "$CORE_POINTER")"
    mv -T -- "$EMBED_POINTER" "$MIGRATION_EMBED_BACKUP"; MIGRATION_PHASE=2
    sync -f "$(dirname "$EMBED_POINTER")"
    install -d -m 0700 "$MIGRATION_LEGACY_SET"
    ln -s -- "$MIGRATION_CORE_BACKUP" "$MIGRATION_LEGACY_SET/core"
    ln -s -- "$MIGRATION_EMBED_BACKUP" "$MIGRATION_LEGACY_SET/embed"
    install -m 0600 "$capture/core.lock" "$MIGRATION_LEGACY_SET/requirements-core.lock"
    install -m 0600 "$capture/embed.lock" "$MIGRATION_LEGACY_SET/requirements-embed.lock"
    install -m 0600 "$capture/tree.inventory" "$MIGRATION_LEGACY_SET/tree.inventory"
    install -m 0600 "$capture/runtime.json" "$MIGRATION_LEGACY_SET/runtime.json"
    CORE_LOCK="$core_lock" EMBED_LOCK="$embed_lock" TREE_HASH="$tree" RUNTIME_HASH="$runtime" \
        "$MIGRATION_CORE_BACKUP/bin/python" - "$MIGRATION_LEGACY_SET/manifest.json" "$legacy" <<'PY'
import json, os, pathlib, sys
data={"schema":"genus-a0.3c-legacy-set-v1","manifest_id":sys.argv[2],"requirements":{"core_sha256":os.environ["CORE_LOCK"],"embed_sha256":os.environ["EMBED_LOCK"]},"tree_inventory_sha256":os.environ["TREE_HASH"],"runtime_inventory_sha256":os.environ["RUNTIME_HASH"]}
pathlib.Path(sys.argv[1]).write_text(json.dumps(data, sort_keys=True, separators=(",", ":"))+"\n")
PY
    seal_set_modes "$MIGRATION_CORE_BACKUP"
    seal_set_modes "$MIGRATION_EMBED_BACKUP"
    seal_set_modes "$MIGRATION_LEGACY_SET"
    durably_sync_tree "$MIGRATION_CORE_BACKUP"
    durably_sync_tree "$MIGRATION_EMBED_BACKUP"
    durably_sync_tree "$MIGRATION_LEGACY_SET"
    fsync_dir "$(dirname "$MIGRATION_CORE_BACKUP")"
    fsync_dir "$(dirname "$MIGRATION_EMBED_BACKUP")"
    fsync_dir "$SETS_ROOT"
    verify_legacy_set "$legacy" >/dev/null
    MIGRATION_PHASE=3
    create_pointer_dir "$CORE_POINTER" core
    create_pointer_dir "$EMBED_POINTER" embed
    atomic_link "sets/$legacy" "$ACTIVE_LINK"
    atomic_link "sets/$legacy" "$PREVIOUS_LINK"
    rm -f -- "$STATE_ROOT/migration.pending"
    sync -f "$STATE_ROOT"
    rm -rf -- "$capture"
    MIGRATION_CAPTURE=""
    MIGRATION_PHASE=0
}

selector_manifest() {
    local link="${1:-$ACTIVE_LINK}" target manifest
    target="$(readlink "$link" 2>/dev/null || true)"
    if [ -z "$target" ]; then
        printf '\n'
        return
    fi
    manifest="${target##*/}"
    safe_manifest_id "$manifest"
    [ "$target" = "sets/$manifest" ] || fail "Selector hat kein exaktes gebundenes Set-Ziel" 70
    printf '%s\n' "$manifest"
}

manifest_file_hash() {
    local manifest="$1" path
    if [ -z "$manifest" ]; then printf '\n'; return; fi
    safe_manifest_id "$manifest"
    path="$(set_path "$manifest")/manifest.json"
    [ -f "$path" ] && [ ! -L "$path" ] && [ "$(stat -c %h "$path")" -eq 1 ] \
        || fail "gebundenes Set-Manifest ist nicht regulaer/einfach verlinkt" 70
    sha256_file "$path"
}

assert_not_previously_paused() {
    local status
    set +e
    GENUS_DB_PATH="$DB_PATH" "$CORE_POINTER/bin/genus" paused >/dev/null 2>&1
    status=$?
    set -e
    case "$status" in
        0) fail "GENUS war bereits pausiert; Runtimewechsel blockiert statt fremden Pausezustand zu uebernehmen" 70 ;;
        1) return 0 ;;
        *) fail "vorheriger Pausezustand ist nicht eindeutig lesbar" 70 ;;
    esac
}

capture_activation_crontab() {
    local original disabled status
    require_command "$CRONTAB_BIN"
    [ ! -e "$ACTIVATION_CRON_SNAPSHOT" ] && [ ! -e "$ACTIVATION_CRON_DISABLED" ] \
        || fail "verwaiste Activation-Crontab-Artefakte vorhanden" 70
    original="$(mktemp "$STATE_ROOT/crontab.original.XXXXXX")"
    disabled="$(mktemp "$STATE_ROOT/crontab.disabled.XXXXXX")"
    set +e
    "$CRONTAB_BIN" -l > "$original" 2>/dev/null; status=$?
    set -e
    [ "$status" -eq 0 ] || { rm -f -- "$original" "$disabled"; fail "User-Crontab nicht exakt lesbar" 70; }
    "$CORE_POINTER/bin/python" - "$original" "$disabled" "$CRON_BEGIN" "$CRON_END" <<'PY'
import pathlib, sys
source, target = map(pathlib.Path, sys.argv[1:3])
begin, end = sys.argv[3:5]
lines = source.read_bytes().splitlines(keepends=True)
begin_rows = [i for i, row in enumerate(lines) if row.rstrip(b"\r\n") == begin.encode()]
end_rows = [i for i, row in enumerate(lines) if row.rstrip(b"\r\n") == end.encode()]
if len(begin_rows) != 1 or len(end_rows) != 1 or begin_rows[0] >= end_rows[0]:
    raise SystemExit("GENUS cron block is not unique and well formed")
target.write_bytes(b"".join(lines[:begin_rows[0]] + lines[end_rows[0] + 1:]))
PY
    chmod 0600 "$original" "$disabled"
    [ -s "$original" ] || { rm -f -- "$original" "$disabled"; fail "Crontab-Snapshot ist leer" 70; }
    mv -- "$original" "$ACTIVATION_CRON_SNAPSHOT"
    mv -- "$disabled" "$ACTIVATION_CRON_DISABLED"
    sync -f "$ACTIVATION_CRON_SNAPSHOT"; sync -f "$ACTIVATION_CRON_DISABLED"; fsync_dir "$STATE_ROOT"
}

verify_live_crontab() {
    local expected="$1" actual status
    actual="$(mktemp "$STATE_ROOT/crontab.verify.XXXXXX")" || return 70
    set +e
    "$CRONTAB_BIN" -l > "$actual" 2>/dev/null; status=$?
    set -e
    if [ "$status" -ne 0 ] || ! cmp -s -- "$actual" "$expected"; then
        rm -f -- "$actual"
        return 70
    fi
    rm -f -- "$actual"
}

disable_genus_cron_block() {
    if verify_live_crontab "$ACTIVATION_CRON_DISABLED"; then return 0; fi
    verify_live_crontab "$ACTIVATION_CRON_SNAPSHOT" \
        || fail "Crontab driftet vor GENUS-Block-Deaktivierung" 70
    "$CRONTAB_BIN" "$ACTIVATION_CRON_DISABLED"
    verify_live_crontab "$ACTIVATION_CRON_DISABLED" \
        || fail "GENUS-Cronblock blieb nach Deaktivierung aktiv" 70
}

restore_genus_cron_block() {
    if verify_live_crontab "$ACTIVATION_CRON_SNAPSHOT"; then return 0; fi
    verify_live_crontab "$ACTIVATION_CRON_DISABLED" \
        || { printf '[A0.3c] FEHLER: Crontab driftet; exakte Restaurierung verweigert\n' >&2; return 70; }
    "$CRONTAB_BIN" "$ACTIVATION_CRON_SNAPSHOT" || return 70
    verify_live_crontab "$ACTIVATION_CRON_SNAPSHOT"
}

write_boot_guard_payload() {
    local output="$1" generator_status
    harden_privileged_boundary
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$output" "$ACTIVATION_JOURNAL" "$AUTOSTART_APPROVAL" "$ACTIVE_LINK" \
        "$SETS_ROOT" "$REPO_DIR" "$GIT_BIN" "$(id -u)" "$(id -g)" "$STATE_ROOT" \
        "$CORE_POINTER" "$EMBED_POINTER" <<'PY'
import pathlib, sys
config = {
    "journal": sys.argv[2], "approval": sys.argv[3], "active": sys.argv[4],
    "sets": sys.argv[5], "repo": sys.argv[6], "git": sys.argv[7], "uid": int(sys.argv[8]),
    "gid": int(sys.argv[9]), "state": sys.argv[10], "core_pointer": sys.argv[11],
    "embed_pointer": sys.argv[12],
}
program = r'''#!/usr/bin/python3 -I
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys

CONFIG = __CONFIG__
PENDING_KEYS = {"schema","phase","candidate_commit","mode","target_manifest","target_manifest_sha256",
 "readiness_path","readiness_sha256","active_manifest","active_manifest_sha256",
 "prior_active_manifest","prior_previous_manifest","prior_active_services","cron_original_sha256",
 "cron_disabled_sha256","activation_receipt_path","activation_receipt_sha256"}

def regular_bytes(name, mode):
    path = pathlib.Path(name)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_uid != CONFIG["uid"] or stat.S_IMODE(before.st_mode) != mode or before.st_nlink != 1:
        raise RuntimeError("unsafe evidence file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        after = os.fstat(fd)
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError("evidence file changed during open")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk: break
            chunks.append(chunk)
        payload = b"".join(chunks)
        final = os.fstat(fd)
        fields = ("st_dev","st_ino","st_uid","st_mode","st_nlink","st_size","st_mtime_ns")
        if any(getattr(final, field) != getattr(before, field) for field in fields) or len(payload) != before.st_size:
            raise RuntimeError("evidence file changed during read")
        return payload
    finally:
        os.close(fd)

def safe_dir(path, mode):
    path = pathlib.Path(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != CONFIG["uid"] or stat.S_IMODE(info.st_mode) != mode or info.st_nlink < 2:
        raise RuntimeError("unsafe runtime directory")
    if path.resolve(strict=True) != path:
        raise RuntimeError("runtime directory is not canonical")
    return path

def set_roles(manifest):
    sets = safe_dir(CONFIG["sets"], 0o700)
    root = safe_dir(sets / manifest, 0o500)
    roles = {}
    for role, pointer in (("core", CONFIG["core_pointer"]), ("embed", CONFIG["embed_pointer"])):
        path = root / role
        if manifest.startswith("legacy-"):
            expected = f"{pointer}.a03c-{manifest}"
            if not stat.S_ISLNK(path.lstat().st_mode) or os.readlink(path) != expected:
                raise RuntimeError("legacy role link differs")
            resolved = pathlib.Path(expected)
            safe_dir(resolved, 0o500)
        else:
            resolved = safe_dir(path, 0o500)
            if resolved.parent != root:
                raise RuntimeError("runtime role escapes set")
        roles[role] = resolved.resolve(strict=True)
    return root, roles

def pointer_unit(pointer_name, role, expected_role):
    pointer = safe_dir(pointer_name, 0o700)
    marker = pointer / ".a03c-pointer-unit"
    if regular_bytes(marker, 0o600) != b"genus-a0.3c-pointer-v1\n":
        raise RuntimeError("pointer marker differs")
    current = pointer / "current"
    if not stat.S_ISLNK(current.lstat().st_mode) or os.readlink(current) != f"{CONFIG['state']}/active/{role}":
        raise RuntimeError("pointer current link differs")
    if current.resolve(strict=True) != expected_role:
        raise RuntimeError("pointer current resolves to wrong role")
    for name in ("bin","lib","include","pyvenv.cfg","lib64"):
        link = pointer / name
        if not stat.S_ISLNK(link.lstat().st_mode) or os.readlink(link) != f"current/{name}":
            raise RuntimeError("stable pointer member differs")
        resolved = link.resolve(strict=True)
        if resolved != expected_role and expected_role not in resolved.parents:
            raise RuntimeError("stable pointer member escapes role")

def manifest_bytes(manifest):
    if not re.fullmatch(r"(?:legacy-)?[a-f0-9]{64}", manifest):
        raise RuntimeError("invalid manifest id")
    root, _ = set_roles(manifest)
    path = root / "manifest.json"
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != CONFIG["uid"] or stat.S_IMODE(info.st_mode) not in {0o400, 0o600} or info.st_nlink != 1:
        raise RuntimeError("unsafe set manifest")
    return regular_bytes(path, stat.S_IMODE(info.st_mode))

def digest(payload): return hashlib.sha256(payload).hexdigest()

def drop_to_runtime_user():
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(CONFIG["gid"])
        os.setuid(CONFIG["uid"])
    if os.geteuid() != CONFIG["uid"] or os.getegid() != CONFIG["gid"]:
        raise RuntimeError("boot guard could not enter the bound runtime identity")

def main():
    drop_to_runtime_user()
    approval = json.loads(regular_bytes(CONFIG["approval"], 0o600))
    if set(approval) != {"schema","repo_commit","active_manifest","active_manifest_sha256","readiness_path","readiness_sha256","reason"}:
        raise RuntimeError("authorization schema differs")
    if approval["schema"] != "genus-a0.3c-runtime-start-authorization-v2" or approval["reason"] not in {"activate","rollback","recovery"}:
        raise RuntimeError("authorization identity differs")
    if not re.fullmatch(r"[a-f0-9]{40}", approval["repo_commit"]):
        raise RuntimeError("authorization commit malformed")
    commit = subprocess.run([CONFIG["git"], "-c", f"safe.directory={CONFIG['repo']}", "-C", CONFIG["repo"],
        "rev-parse", "--verify", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
    if commit != approval["repo_commit"]:
        raise RuntimeError("repo commit differs")
    dirty = subprocess.run([CONFIG["git"], "-c", f"safe.directory={CONFIG['repo']}", "-C", CONFIG["repo"],
        "status", "--porcelain=v1", "--untracked-files=all"], check=True, text=True, capture_output=True).stdout
    if dirty:
        raise RuntimeError("repo worktree is not exactly clean")
    active_path = pathlib.Path(CONFIG["active"])
    if not stat.S_ISLNK(active_path.lstat().st_mode):
        raise RuntimeError("ACTIVE is not a selector link")
    raw_active = os.readlink(active_path)
    if raw_active != f"sets/{approval['active_manifest']}":
        raise RuntimeError("ACTIVE selector differs")
    active_payload = manifest_bytes(approval["active_manifest"])
    if digest(active_payload) != approval["active_manifest_sha256"]:
        raise RuntimeError("ACTIVE manifest hash differs")
    _, active_roles = set_roles(approval["active_manifest"])
    pointer_unit(CONFIG["core_pointer"], "core", active_roles["core"])
    pointer_unit(CONFIG["embed_pointer"], "embed", active_roles["embed"])
    readiness = approval["readiness_path"]
    if readiness:
        if digest(regular_bytes(readiness, 0o600)) != approval["readiness_sha256"]:
            raise RuntimeError("readiness hash differs")
    elif approval["reason"] == "activate" or approval["readiness_sha256"]:
        raise RuntimeError("activate lacks readiness evidence")
    journal_path = pathlib.Path(CONFIG["journal"])
    try:
        journal_path.lstat()
    except FileNotFoundError:
        return
    journal = json.loads(regular_bytes(journal_path, 0o600))
    if set(journal) != PENDING_KEYS or journal["schema"] != "genus-a0.3c-runtime-activation-pending-v1":
        raise RuntimeError("pending schema differs")
    if journal["candidate_commit"] != approval["repo_commit"] or journal["active_manifest"] != approval["active_manifest"]:
        raise RuntimeError("pending authorization differs")
    target_payload = manifest_bytes(journal["target_manifest"])
    if digest(target_payload) != journal["target_manifest_sha256"]:
        raise RuntimeError("target manifest hash differs")
    if journal["active_manifest"] not in {journal["target_manifest"], journal["prior_active_manifest"]}:
        raise RuntimeError("ACTIVE is outside the journal transition")
    if approval["reason"] == "activate" and (journal["active_manifest"] != journal["target_manifest"] or journal["readiness_path"] != approval["readiness_path"] or journal["readiness_sha256"] != approval["readiness_sha256"]):
        raise RuntimeError("pending activate readiness differs")
    if journal["phase"] not in {"guarded","target-verified","resumed","postflight","receipt-written"}:
        raise RuntimeError("journal phase does not allow an autostart")

try:
    main()
except Exception:
    sys.exit(1)
'''
path = pathlib.Path(sys.argv[1])
path.write_text(program.replace("__CONFIG__", repr(config)))
PY
    generator_status=$?
    [ "$generator_status" -eq 0 ] || return "$generator_status"
    chmod 0600 "$output"
}

systemd_guard_payload() {
    local unit="${1:-}"
    printf '[Unit]\nConditionPathExists=%s\n' "$AUTOSTART_APPROVAL"
    if [[ "$unit" != *.timer ]]; then
        printf '[Service]\nExecCondition=%s\n' "$BOOT_GUARD_PATH"
    fi
}

install_systemd_autostart_guard() {
    local unit directory path expected boot_expected
    boot_expected="$(mktemp "$STATE_ROOT/boot-guard.XXXXXX")"
    write_boot_guard_payload "$boot_expected"
    if as_root "$ROOT_TEST_BIN" -e "$BOOT_GUARD_PATH" || as_root "$ROOT_TEST_BIN" -L "$BOOT_GUARD_PATH"; then
        as_root "$ROOT_TEST_BIN" -f "$BOOT_GUARD_PATH" && ! as_root "$ROOT_TEST_BIN" -L "$BOOT_GUARD_PATH" \
            && [ "$(as_root "$ROOT_STAT_BIN" -c %u "$BOOT_GUARD_PATH")" -eq 0 ] \
            && [ "$(as_root "$ROOT_STAT_BIN" -c %a "$BOOT_GUARD_PATH")" = 755 ] \
            && [ "$(as_root "$ROOT_STAT_BIN" -c %h "$BOOT_GUARD_PATH")" -eq 1 ] \
            && as_root "$ROOT_CMP_BIN" -s -- "$boot_expected" "$BOOT_GUARD_PATH" \
            || { rm -f -- "$boot_expected"; fail "fremder/ungueltiger root Boot-Guard" 70; }
    else
        as_root "$ROOT_INSTALL_BIN" -d -o root -g root -m 0755 "$(dirname "$BOOT_GUARD_PATH")"
        as_root "$ROOT_INSTALL_BIN" -o root -g root -m 0755 "$boot_expected" "$BOOT_GUARD_PATH"
        as_root "$ROOT_SYNC_BIN" -f "$BOOT_GUARD_PATH"
        as_root "$ROOT_SYNC_BIN" -f "$(dirname "$BOOT_GUARD_PATH")"
    fi
    rm -f -- "$boot_expected"
    expected="$(mktemp "$STATE_ROOT/systemd-guard.XXXXXX")"
    for unit in "${AUTOSTART_UNITS[@]}"; do
        systemd_guard_payload "$unit" > "$expected"; chmod 0600 "$expected"
        directory="$SYSTEMD_GUARD_ROOT/$unit.d"
        path="$directory/90-genus-a0-3c-pending.conf"
        if as_root "$ROOT_TEST_BIN" -e "$path" || as_root "$ROOT_TEST_BIN" -L "$path"; then
            as_root "$ROOT_TEST_BIN" -f "$path" && ! as_root "$ROOT_TEST_BIN" -L "$path" \
                && [ "$(as_root "$ROOT_STAT_BIN" -c %u "$path")" -eq 0 ] \
                && [ "$(as_root "$ROOT_STAT_BIN" -c %a "$path")" = 644 ] \
                && [ "$(as_root "$ROOT_STAT_BIN" -c %h "$path")" -eq 1 ] \
                && as_root "$ROOT_CMP_BIN" -s -- "$expected" "$path" \
                || { rm -f -- "$expected"; fail "fremder/ungueltiger systemd Activation-Guard" 70; }
            continue
        fi
        as_root "$ROOT_INSTALL_BIN" -d -o root -g root -m 0755 "$directory"
        as_root "$ROOT_INSTALL_BIN" -o root -g root -m 0644 "$expected" "$path"
        as_root "$ROOT_SYNC_BIN" -f "$path"
        as_root "$ROOT_SYNC_BIN" -f "$directory"
    done
    rm -f -- "$expected"
    systemctl_root daemon-reload
}

systemd_autostart_guard_present() {
    local unit path expected boot_expected
    boot_expected="$(mktemp "$STATE_ROOT/boot-guard-check.XXXXXX")"
    write_boot_guard_payload "$boot_expected"
    if ! as_root "$ROOT_TEST_BIN" -f "$BOOT_GUARD_PATH" || as_root "$ROOT_TEST_BIN" -L "$BOOT_GUARD_PATH" \
        || [ "$(as_root "$ROOT_STAT_BIN" -c %u "$BOOT_GUARD_PATH" 2>/dev/null || printf 1)" -ne 0 ] \
        || [ "$(as_root "$ROOT_STAT_BIN" -c %a "$BOOT_GUARD_PATH" 2>/dev/null || true)" != 755 ] \
        || [ "$(as_root "$ROOT_STAT_BIN" -c %h "$BOOT_GUARD_PATH" 2>/dev/null || printf 0)" -ne 1 ] \
        || ! as_root "$ROOT_CMP_BIN" -s -- "$boot_expected" "$BOOT_GUARD_PATH"; then
        rm -f -- "$boot_expected"
        return 1
    fi
    rm -f -- "$boot_expected"
    expected="$(mktemp "$STATE_ROOT/systemd-guard-check.XXXXXX")"
    for unit in "${AUTOSTART_UNITS[@]}"; do
        systemd_guard_payload "$unit" > "$expected"
        path="$SYSTEMD_GUARD_ROOT/$unit.d/90-genus-a0-3c-pending.conf"
        if ! as_root "$ROOT_TEST_BIN" -f "$path" || as_root "$ROOT_TEST_BIN" -L "$path" \
            || [ "$(as_root "$ROOT_STAT_BIN" -c %u "$path" 2>/dev/null || printf 1)" -ne 0 ] \
            || [ "$(as_root "$ROOT_STAT_BIN" -c %a "$path" 2>/dev/null || true)" != 644 ] \
            || [ "$(as_root "$ROOT_STAT_BIN" -c %h "$path" 2>/dev/null || printf 0)" -ne 1 ] \
            || ! as_root "$ROOT_CMP_BIN" -s -- "$expected" "$path"; then
            rm -f -- "$expected"
            return 1
        fi
    done
    rm -f -- "$expected"
}

remove_systemd_autostart_guard() {
    local unit directory path result=0
    systemd_autostart_guard_present
    for unit in "${AUTOSTART_UNITS[@]}"; do
        directory="$SYSTEMD_GUARD_ROOT/$unit.d"
        path="$directory/90-genus-a0-3c-pending.conf"
        as_root "$ROOT_RM_BIN" -f -- "$path" || result=70
        as_root "$ROOT_RMDIR_BIN" --ignore-fail-on-non-empty "$directory" 2>/dev/null || true
    done
    [ "$result" -eq 0 ] || return "$result"
    as_root "$ROOT_RM_BIN" -f -- "$BOOT_GUARD_PATH" || return 70
    as_root "$ROOT_SYNC_BIN" -f "$(dirname "$BOOT_GUARD_PATH")"
    systemctl_root daemon-reload
}

journal_python() {
    if [ -x "$CORE_POINTER/bin/python" ]; then printf '%s\n' "$CORE_POINTER/bin/python"
    elif [ -x "$RUNTIME_PREFIX/bin/python3.13" ]; then printf '%s\n' "$RUNTIME_PREFIX/bin/python3.13"
    else fail "kein Interpreter fuer Activation-Journal verfuegbar" 70
    fi
}

create_activation_journal() {
    local expected="$1" target="$2" mode="$3" readiness="$4" readiness_hash active active_hash previous
    local target_hash services_csv python
    [ ! -e "$ACTIVATION_JOURNAL" ] || fail "Activation-Journal existiert bereits" 70
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"
    previous="$(selector_manifest "$PREVIOUS_LINK")"
    target_hash="$(manifest_file_hash "$target")"
    readiness_hash=""; [ -z "$readiness" ] || readiness_hash="$(sha256_file "$readiness")"
    [ "${#active_services[@]}" -gt 0 ] || fail "kein aktives GENUS-Service-Inventar fuer Recovery" 70
    services_csv="$(IFS=,; printf '%s' "${active_services[*]}")"
    python="$(journal_python)"
    EXPECTED="$expected" TARGET="$target" TARGET_HASH="$target_hash" MODE="$mode" \
    READINESS="$readiness" READINESS_HASH="$readiness_hash" ACTIVE="$active" ACTIVE_HASH="$active_hash" \
    PREVIOUS="$previous" SERVICES_CSV="$services_csv" \
    CRON_ORIGINAL_HASH="$(sha256_file "$ACTIVATION_CRON_SNAPSHOT")" \
    CRON_DISABLED_HASH="$(sha256_file "$ACTIVATION_CRON_DISABLED")" \
        "$python" - "$ACTIVATION_JOURNAL" <<'PY'
import json, os, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = {
    "schema":"genus-a0.3c-runtime-activation-pending-v1", "phase":"prepared",
    "candidate_commit":os.environ["EXPECTED"], "mode":os.environ["MODE"],
    "target_manifest":os.environ["TARGET"], "target_manifest_sha256":os.environ["TARGET_HASH"],
    "readiness_path":os.environ["READINESS"], "readiness_sha256":os.environ["READINESS_HASH"],
    "active_manifest":os.environ["ACTIVE"], "active_manifest_sha256":os.environ["ACTIVE_HASH"],
    "prior_active_manifest":os.environ["ACTIVE"], "prior_previous_manifest":os.environ["PREVIOUS"],
    "prior_active_services":[item for item in os.environ["SERVICES_CSV"].split(",") if item],
    "cron_original_sha256":os.environ["CRON_ORIGINAL_HASH"],
    "cron_disabled_sha256":os.environ["CRON_DISABLED_HASH"],
    "activation_receipt_path":"", "activation_receipt_sha256":"",
}
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
fd = os.open(path, flags, 0o600)
try:
    payload = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
    os.write(fd, payload); os.fsync(fd)
finally: os.close(fd)
directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try: os.fsync(directory)
finally: os.close(directory)
PY
}

validate_activation_journal() {
    local allow_active_mismatch="${1:-0}" python active active_hash
    [ -f "$ACTIVATION_JOURNAL" ] && [ ! -L "$ACTIVATION_JOURNAL" ] \
        && [ "$(stat -c %u "$ACTIVATION_JOURNAL")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$ACTIVATION_JOURNAL")" = 600 ] \
        && [ "$(stat -c %h "$ACTIVATION_JOURNAL")" -eq 1 ] \
        || fail "Activation-Journal ist nicht regulaer/user-owned/0600/einfach verlinkt" 70
    [ -f "$ACTIVATION_CRON_SNAPSHOT" ] && [ ! -L "$ACTIVATION_CRON_SNAPSHOT" ] \
        && [ "$(stat -c %u "$ACTIVATION_CRON_SNAPSHOT")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$ACTIVATION_CRON_SNAPSHOT")" = 600 ] \
        && [ "$(stat -c %h "$ACTIVATION_CRON_SNAPSHOT")" -eq 1 ] \
        || fail "Activation-Crontab-Snapshot ist ungueltig" 70
    [ -f "$ACTIVATION_CRON_DISABLED" ] && [ ! -L "$ACTIVATION_CRON_DISABLED" ] \
        && [ "$(stat -c %u "$ACTIVATION_CRON_DISABLED")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$ACTIVATION_CRON_DISABLED")" = 600 ] \
        && [ "$(stat -c %h "$ACTIVATION_CRON_DISABLED")" -eq 1 ] \
        || fail "deaktivierter Activation-Crontab ist ungueltig" 70
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"
    python="$(journal_python)"
    COMMIT="$(repo_commit)" ACTIVE="$active" ACTIVE_HASH="$active_hash" \
    ALLOW_ACTIVE_MISMATCH="$allow_active_mismatch" \
    TARGET_ROOT="$SETS_ROOT" CRON_ORIGINAL_HASH="$(sha256_file "$ACTIVATION_CRON_SNAPSHOT")" \
    CRON_DISABLED_HASH="$(sha256_file "$ACTIVATION_CRON_DISABLED")" \
        "$python" - "$ACTIVATION_JOURNAL" <<'PY'
import hashlib, json, os, pathlib, sys
path = pathlib.Path(sys.argv[1]); data = json.loads(path.read_text())
required = {"schema","phase","candidate_commit","mode","target_manifest","target_manifest_sha256",
 "readiness_path","readiness_sha256","active_manifest","active_manifest_sha256",
 "prior_active_manifest","prior_previous_manifest","prior_active_services","cron_original_sha256",
 "cron_disabled_sha256","activation_receipt_path","activation_receipt_sha256"}
if set(data) != required or data["schema"] != "genus-a0.3c-runtime-activation-pending-v1":
    raise SystemExit("activation journal schema differs")
if data["candidate_commit"] != os.environ["COMMIT"]:
    raise SystemExit("activation journal commit differs")
if os.environ["ALLOW_ACTIVE_MISMATCH"] != "1" and (data["active_manifest"] != os.environ["ACTIVE"] or data["active_manifest_sha256"] != os.environ["ACTIVE_HASH"]):
    raise SystemExit("activation journal ACTIVE binding differs")
target = pathlib.Path(os.environ["TARGET_ROOT"]) / data["target_manifest"] / "manifest.json"
if target.is_symlink() or not target.is_file() or target.stat().st_nlink != 1:
    raise SystemExit("target manifest is not a regular single-link file")
if hashlib.sha256(target.read_bytes()).hexdigest() != data["target_manifest_sha256"]:
    raise SystemExit("target manifest hash differs")
readiness = data["readiness_path"]
if readiness:
    ready = pathlib.Path(readiness)
    if ready.is_symlink() or not ready.is_file() or ready.stat().st_nlink != 1:
        raise SystemExit("readiness manifest is not regular")
    if hashlib.sha256(ready.read_bytes()).hexdigest() != data["readiness_sha256"]:
        raise SystemExit("readiness manifest hash differs")
elif data["readiness_sha256"]:
    raise SystemExit("empty readiness path has a hash")
if data["cron_original_sha256"] != os.environ["CRON_ORIGINAL_HASH"] or data["cron_disabled_sha256"] != os.environ["CRON_DISABLED_HASH"]:
    raise SystemExit("crontab snapshot hash differs")
allowed_services={"genus-network-watchdog.timer","genus-network-watchdog.service","genus-learner.service","genus-telegram-bot.service","genus-telegram-bot-fallback.service"}
if not data["prior_active_services"] or len(data["prior_active_services"]) != len(set(data["prior_active_services"])) or any(item not in allowed_services for item in data["prior_active_services"]):
    raise SystemExit("service inventory differs")
allowed = {"prepared","guarded","paused","stopped","legacy-ready","swapped","target-verified","resumed","postflight","receipt-written"}
if data["phase"] not in allowed or data["mode"] not in {"activate","rollback"}:
    raise SystemExit("activation journal state differs")
PY
}

rebind_activation_journal() {
    local phase="$1" expected_active="$2" python active active_hash tmp
    validate_activation_journal 1
    active="$(selector_manifest)"
    [ "$active" = "$expected_active" ] || fail "ACTIVE weicht vom erwarteten Journal-Uebergang ab" 70
    active_hash="$(manifest_file_hash "$active")"; python="$(journal_python)"
    tmp="$ACTIVATION_JOURNAL.tmp.$$.$RANDOM"
    PHASE="$phase" ACTIVE="$active" ACTIVE_HASH="$active_hash" \
        "$python" - "$ACTIVATION_JOURNAL" "$tmp" <<'PY'
import json, os, pathlib, sys
source, target = map(pathlib.Path, sys.argv[1:3]); data = json.loads(source.read_text())
allowed = {data["target_manifest"], data["prior_active_manifest"]}
if data["prior_active_manifest"] == "" and os.environ["ACTIVE"].startswith("legacy-"):
    data["prior_active_manifest"] = os.environ["ACTIVE"]
    if not data["prior_previous_manifest"]:
        data["prior_previous_manifest"] = os.environ["ACTIVE"]
    allowed.add(os.environ["ACTIVE"])
if os.environ["ACTIVE"] not in allowed:
    raise SystemExit("ACTIVE is not an allowed activation transition")
data["phase"] = os.environ["PHASE"]
data["active_manifest"] = os.environ["ACTIVE"]
data["active_manifest_sha256"] = os.environ["ACTIVE_HASH"]
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
fd = os.open(target, flags, 0o600)
try:
    os.write(fd, (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()); os.fsync(fd)
finally: os.close(fd)
os.replace(target, source)
directory = os.open(source.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    validate_activation_journal
}

update_activation_journal() {
    local phase="$1" receipt="${2:-}" python active active_hash tmp
    validate_activation_journal
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"
    python="$(journal_python)"; tmp="$ACTIVATION_JOURNAL.tmp.$$.$RANDOM"
    PHASE="$phase" ACTIVE="$active" ACTIVE_HASH="$active_hash" RECEIPT="$receipt" \
    RECEIPT_HASH="$([ -z "$receipt" ] || sha256_file "$receipt")" \
        "$python" - "$ACTIVATION_JOURNAL" "$tmp" <<'PY'
import json, os, pathlib, sys
source, target = map(pathlib.Path, sys.argv[1:3]); data = json.loads(source.read_text())
data["phase"] = os.environ["PHASE"]; data["active_manifest"] = os.environ["ACTIVE"]
data["active_manifest_sha256"] = os.environ["ACTIVE_HASH"]
if os.environ["RECEIPT"]:
    data["activation_receipt_path"] = os.environ["RECEIPT"]
    data["activation_receipt_sha256"] = os.environ["RECEIPT_HASH"]
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
fd = os.open(target, flags, 0o600)
try:
    os.write(fd, (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()); os.fsync(fd)
finally: os.close(fd)
os.replace(target, source)
directory = os.open(source.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try: os.fsync(directory)
finally: os.close(directory)
PY
}

remove_autostart_approval() {
    rm -f -- "$AUTOSTART_APPROVAL"
    fsync_dir "$STATE_ROOT"
}

write_autostart_approval() {
    local python active active_hash
    validate_activation_journal
    systemd_autostart_guard_present
    [ ! -e "$AUTOSTART_APPROVAL" ] || fail "Autostart-Approval existiert bereits" 70
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"; python="$(journal_python)"
    ACTIVE="$active" ACTIVE_HASH="$active_hash" COMMIT="$(repo_commit)" \
        "$python" - "$ACTIVATION_JOURNAL" "$AUTOSTART_APPROVAL" <<'PY'
import json, os, pathlib, sys
journal = json.loads(pathlib.Path(sys.argv[1]).read_text()); path = pathlib.Path(sys.argv[2])
if journal["active_manifest"] != os.environ["ACTIVE"] or journal["active_manifest_sha256"] != os.environ["ACTIVE_HASH"]:
    raise SystemExit("journal ACTIVE is not directly verified")
if journal["active_manifest"] == journal["target_manifest"]:
    reason = journal["mode"]
else:
    if journal["active_manifest"] != journal["prior_active_manifest"]:
        raise SystemExit("restored ACTIVE is not journal-bound")
    reason = "recovery"
readiness_path = journal["readiness_path"] if reason == "activate" else ""
readiness_hash = journal["readiness_sha256"] if reason == "activate" else ""
data={"schema":"genus-a0.3c-runtime-start-authorization-v2","repo_commit":os.environ["COMMIT"],
      "active_manifest":os.environ["ACTIVE"],"active_manifest_sha256":os.environ["ACTIVE_HASH"],
      "readiness_path":readiness_path,"readiness_sha256":readiness_hash,"reason":reason}
flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
if hasattr(os,"O_NOFOLLOW"): flags|=os.O_NOFOLLOW
fd=os.open(path,flags,0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    validate_autostart_approval
}

validate_autostart_approval() {
    local python active active_hash has_journal=0
    [ -f "$AUTOSTART_APPROVAL" ] && [ ! -L "$AUTOSTART_APPROVAL" ] \
        && [ "$(stat -c %u "$AUTOSTART_APPROVAL")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$AUTOSTART_APPROVAL")" = 600 ] \
        && [ "$(stat -c %h "$AUTOSTART_APPROVAL")" -eq 1 ] \
        || fail "Autostart-Approval ist nicht regulaer/user-owned/0600/einfach verlinkt" 70
    if [ -e "$ACTIVATION_JOURNAL" ] || [ -L "$ACTIVATION_JOURNAL" ]; then
        validate_activation_journal
        has_journal=1
    fi
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"; python="$(journal_python)"
    ACTIVE="$active" ACTIVE_HASH="$active_hash" COMMIT="$(repo_commit)" HAS_JOURNAL="$has_journal" \
        "$python" - "$ACTIVATION_JOURNAL" "$AUTOSTART_APPROVAL" <<'PY'
import hashlib, json, os, pathlib, sys
journal_path, approval_path = map(pathlib.Path, sys.argv[1:3])
approval=json.loads(approval_path.read_text())
if set(approval) != {"schema","repo_commit","active_manifest","active_manifest_sha256","readiness_path","readiness_sha256","reason"}:
    raise SystemExit("start authorization schema differs")
if approval["schema"] != "genus-a0.3c-runtime-start-authorization-v2" or approval["repo_commit"] != os.environ["COMMIT"]:
    raise SystemExit("start authorization commit differs")
if approval["active_manifest"] != os.environ["ACTIVE"] or approval["active_manifest_sha256"] != os.environ["ACTIVE_HASH"]:
    raise SystemExit("start authorization ACTIVE binding differs")
if approval["reason"] not in {"activate","rollback","recovery"}:
    raise SystemExit("start authorization reason differs")
if approval["readiness_path"]:
    ready=pathlib.Path(approval["readiness_path"])
    if ready.is_symlink() or not ready.is_file() or ready.stat().st_nlink != 1:
        raise SystemExit("authorization readiness is not regular")
    if hashlib.sha256(ready.read_bytes()).hexdigest() != approval["readiness_sha256"]:
        raise SystemExit("authorization readiness hash differs")
elif approval["readiness_sha256"] or approval["reason"] == "activate":
    raise SystemExit("activate authorization lacks readiness")
if os.environ["HAS_JOURNAL"] == "1":
    journal=json.loads(journal_path.read_text())
    if journal["candidate_commit"] != approval["repo_commit"] or journal["active_manifest"] != approval["active_manifest"]:
        raise SystemExit("pending journal and authorization differ")
    if approval["reason"] == "activate" and (journal["target_manifest"] != approval["active_manifest"] or journal["readiness_path"] != approval["readiness_path"] or journal["readiness_sha256"] != approval["readiness_sha256"]):
        raise SystemExit("activate authorization is not readiness-bound to pending journal")
PY
}

validate_stale_autostart_approval() {
    local old_commit="$1" active active_hash
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$AUTOSTART_APPROVAL" "$old_commit" "$active" "$active_hash" "$SETS_ROOT/$active/manifest.json" <<'PY'
import hashlib, json, pathlib, sys
approval_path, old, active, active_hash, manifest_path = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], pathlib.Path(sys.argv[5])
approval=json.loads(approval_path.read_text())
keys={"schema","repo_commit","active_manifest","active_manifest_sha256","readiness_path","readiness_sha256","reason"}
if set(approval)!=keys or approval["schema"]!="genus-a0.3c-runtime-start-authorization-v2" or approval["repo_commit"]!=old or approval["active_manifest"]!=active or approval["active_manifest_sha256"]!=active_hash: raise SystemExit("stale approval binding differs")
if approval["reason"] not in {"activate","rollback","recovery"}: raise SystemExit("stale approval reason differs")
if approval["readiness_path"]:
    ready=pathlib.Path(approval["readiness_path"])
    if ready.is_symlink() or not ready.is_file() or ready.stat().st_nlink!=1 or hashlib.sha256(ready.read_bytes()).hexdigest()!=approval["readiness_sha256"]: raise SystemExit("stale approval readiness differs")
elif approval["readiness_sha256"] or approval["reason"]=="activate": raise SystemExit("stale activate approval lacks readiness")
manifest=json.loads(manifest_path.read_text())
if not active.startswith("legacy-") and (manifest.get("schema")!="genus-a0.3c-runtime-set-v1" or manifest.get("manifest_id")!=active or manifest.get("repo_commit")!=old): raise SystemExit("stale active manifest is not old-commit-bound")
PY
}

validate_operator_reauthorization() {
    local receipt old new active active_hash guard_hash approval_hash stale_path stale_hash
    local old_tree new_tree diff_file diff_hash path
    [ -f "$OPERATOR_REAUTH_TOKEN" ] && [ ! -L "$OPERATOR_REAUTH_TOKEN" ] \
        && [ "$(stat -c %u "$OPERATOR_REAUTH_TOKEN")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$OPERATOR_REAUTH_TOKEN")" = 600 ] \
        && [ "$(stat -c %h "$OPERATOR_REAUTH_TOKEN")" -eq 1 ] \
        || fail "Operator-Reauthorization-Token ist nicht regulaer/privat" 70
    systemd_autostart_guard_present
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"
    receipt="$("$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$OPERATOR_REAUTH_TOKEN" <<'PY'
import json,pathlib,sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
print(data.get("receipt_path",""))
PY
)"
    [ -f "$receipt" ] && [ ! -L "$receipt" ] \
        && [ "$(stat -c %u "$receipt")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$receipt")" = 600 ] && [ "$(stat -c %h "$receipt")" -eq 1 ] \
        || fail "Operator-Reauthorization-Receipt ist nicht regulaer/privat" 70
    stale_path="$("$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import json,pathlib,sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text()).get("stale_approval_path",""))
PY
)"
    case "$(realpath -e -- "$stale_path" 2>/dev/null || true)" in "$RECEIPT_ROOT"/*) ;; *) fail "stale Approval-Evidence entkommt Receipt-Root" 70 ;; esac
    [ -f "$stale_path" ] && [ ! -L "$stale_path" ] && [ "$(stat -c %h "$stale_path")" -eq 1 ] \
        || fail "stale Approval-Evidence ist nicht regulaer" 70
    guard_hash="$(sha256_file "$BOOT_GUARD_PATH")"; approval_hash="$(sha256_file "$AUTOSTART_APPROVAL")"
    stale_hash="$(sha256_file "$stale_path")"
    [ "$approval_hash" = "$stale_hash" ] || fail "live stale Approval driftete von Reauthorization-Evidence" 70
    TOKEN_HASH="$(sha256_file "$receipt")" ACTIVE="$active" ACTIVE_HASH="$active_hash" \
    GUARD_HASH="$guard_hash" GUARD_PATH="$BOOT_GUARD_PATH" APPROVAL_HASH="$approval_hash" \
    STALE_PATH="$stale_path" STALE_HASH="$stale_hash" COMMIT="$(repo_commit)" \
        "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$OPERATOR_REAUTH_TOKEN" "$receipt" "$AUTOSTART_APPROVAL" <<'PY'
import hashlib,json,os,pathlib,re,sys
token=json.loads(pathlib.Path(sys.argv[1]).read_text()); receipt=json.loads(pathlib.Path(sys.argv[2]).read_text())
token_keys={"schema","receipt_path","receipt_sha256","old_commit","new_commit","active_manifest","active_manifest_sha256","guard_sha256","intended_command"}
receipt_keys={"schema","old_commit","new_commit","old_tree","new_tree","active_manifest","active_manifest_sha256","stale_approval_path","stale_approval_sha256","guard_path","guard_sha256","allowed_diff_sha256","intended_command","boot_approval_updated","paths_logged","payloads_logged"}
if set(token)!=token_keys or token["schema"]!="genus-a0.3c-operator-reauthorization-token-v1" or set(receipt)!=receipt_keys or receipt["schema"]!="genus-a0.3c-operator-reauthorization-v1": raise SystemExit("reauthorization schema differs")
if token["receipt_path"]!=sys.argv[2] or token["receipt_sha256"]!=os.environ["TOKEN_HASH"] or token["new_commit"]!=os.environ["COMMIT"] or token["active_manifest"]!=os.environ["ACTIVE"] or token["active_manifest_sha256"]!=os.environ["ACTIVE_HASH"] or token["guard_sha256"]!=os.environ["GUARD_HASH"] or token["intended_command"]!="stage-and-activate": raise SystemExit("reauthorization token binding differs")
for key in ("old_commit","new_commit","active_manifest","active_manifest_sha256","guard_sha256","intended_command"):
    if receipt[key]!=token[key]: raise SystemExit("reauthorization receipt/token crossbinding differs")
if receipt["stale_approval_path"]!=os.environ["STALE_PATH"] or receipt["stale_approval_sha256"]!=os.environ["STALE_HASH"] or receipt["stale_approval_sha256"]!=os.environ["APPROVAL_HASH"] or receipt["guard_path"]!=os.environ["GUARD_PATH"]: raise SystemExit("reauthorization stale evidence differs")
if receipt["boot_approval_updated"] is not False or receipt["paths_logged"] is not True or receipt["payloads_logged"] is not False: raise SystemExit("reauthorization safety booleans differ")
if not re.fullmatch(r"[0-9a-f]{40}",receipt["old_commit"]) or not re.fullmatch(r"[0-9a-f]{40}",receipt["new_commit"]): raise SystemExit("reauthorization commit malformed")
if any(not re.fullmatch(r"[0-9a-f]{64}",receipt[key]) for key in ("old_tree","new_tree","active_manifest_sha256","stale_approval_sha256","guard_sha256","allowed_diff_sha256")): raise SystemExit("reauthorization digest malformed")
PY
    old="$("$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import json,pathlib,sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["old_commit"])
PY
)"
    new="$(repo_commit)"
    assert_expected_commit "$new"
    "$GIT_BIN" -C "$REPO_DIR" merge-base --is-ancestor "$old" "$new" \
        || fail "reauthorisierter Commit ist kein Fast-Forward" 65
    old_tree="$("$GIT_BIN" -C "$REPO_DIR" rev-parse "$old^{tree}")"
    new_tree="$("$GIT_BIN" -C "$REPO_DIR" rev-parse "$new^{tree}")"
    diff_file="$(mktemp "$STATE_ROOT/reauthorize-verify.diff.XXXXXX")"
    "$GIT_BIN" -C "$REPO_DIR" diff --name-only -z "$old" "$new" > "$diff_file"
    while IFS= read -r -d '' path; do
        case "$path" in
            deploy/pi_a0_3c_runtime.sh|deploy/README.md|docs/*|tests/*|experiments/*|.github/*|README*|CONTRIBUTING.md) ;;
            *) fail "reauthorisierter Diff enthaelt nun einen nicht freigegebenen Pfad" 70 ;;
        esac
    done < "$diff_file"
    diff_hash="$(sha256_file "$diff_file")"; rm -f -- "$diff_file"
    OLD_TREE="$old_tree" NEW_TREE="$new_tree" DIFF_HASH="$diff_hash" \
        "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import json,os,pathlib,sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
if data["old_tree"]!=os.environ["OLD_TREE"] or data["new_tree"]!=os.environ["NEW_TREE"] or data["allowed_diff_sha256"]!=os.environ["DIFF_HASH"]: raise SystemExit("reauthorization git-object/diff binding differs")
PY
    validate_stale_autostart_approval "$old"
    OPERATOR_REAUTH_RECEIPT="$receipt"
}

consume_operator_reauthorization() {
    [ ! -e "$OPERATOR_REAUTH_TOKEN" ] && return 0
    rm -f -- "$OPERATOR_REAUTH_TOKEN"
    fsync_dir "$STATE_ROOT"
    OPERATOR_REAUTH_RECEIPT=""
}

clear_activation_state() {
    # The crontab snapshots remain as durable recovery evidence until the next
    # locked invocation observes the established no-journal state and removes
    # them.  Thus a finalization error can always disable the exact GENUS block.
    rm -f -- "$ACTIVATION_JOURNAL"
    fsync_dir "$STATE_ROOT"
}

active_services=()
old_pids=()
old_restarts=()
old_invocations=()
old_active_enters=()
stopped_services=()
SERVICES_RESTARTED=0
remember_services() {
    local service pid restarts active invocation entered
    active_services=(); old_pids=(); old_restarts=(); old_invocations=(); old_active_enters=(); stopped_services=()
    for service in "${SERVICES[@]}"; do
        active="$($SYSTEMCTL_BIN show "$service" -p ActiveState --value 2>/dev/null || true)"
        if [ "$active" = active ]; then
            [ "$service" != genus-telegram-bot-fallback.service ] \
                || fail "aktive transiente Telegram-Fallback-Unit ist nicht verlustfrei restartbar" 70
            active_services+=("$service")
            invocation="$($SYSTEMCTL_BIN show "$service" -p InvocationID --value 2>/dev/null || true)"
            entered="$($SYSTEMCTL_BIN show "$service" -p ActiveEnterTimestampMonotonic --value 2>/dev/null || true)"
            if [[ "$service" = *.timer ]]; then
                pid=0; restarts=0
                [[ "$entered" =~ ^[0-9]+$ ]] || fail "Timerstatus unlesbar: $service" 70
            else
                pid="$($SYSTEMCTL_BIN show "$service" -p MainPID --value)"
                restarts="$($SYSTEMCTL_BIN show "$service" -p NRestarts --value)"
                [[ "$pid" =~ ^[0-9]+$ ]] && [[ "$restarts" =~ ^[0-9]+$ ]] \
                    || fail "Dienststatus unlesbar: $service" 70
            fi
            old_pids+=("$pid")
            old_restarts+=("$restarts")
            old_invocations+=("$invocation")
            old_active_enters+=("$entered")
        fi
    done
}

stop_services() {
    local service load_state result=0 step
    for service in "${AUTOSTART_UNITS[@]}"; do
        load_state="$($SYSTEMCTL_BIN show "$service" -p LoadState --value 2>/dev/null || true)"
        if [ "$load_state" != not-found ]; then
            if systemctl_root stop "$service"; then
                if [[ " ${active_services[*]} " == *" $service "* ]]; then stopped_services+=("$service"); fi
            else
                step=$?
                [ "$result" -ne 0 ] || result="$step"
            fi
        fi
    done
    return "$result"
}

start_previous_services() {
    local index service pid restarts active invocation entered
    SERVICES_RESTARTED=1
    for index in "${!active_services[@]}"; do
        service="${active_services[$index]}"
        [[ " ${stopped_services[*]} " == *" $service "* ]] || continue
        if ! systemctl_root start "$service"; then
            printf '[A0.3c] FEHLER: Dienststart fehlgeschlagen: %s\n' "$service" >&2
            return 70
        fi
        active="$($SYSTEMCTL_BIN show "$service" -p ActiveState --value 2>/dev/null || true)"
        if [ "$active" != active ]; then
            printf '[A0.3c] FEHLER: Dienst blieb inaktiv: %s\n' "$service" >&2
            return 70
        fi
        invocation="$($SYSTEMCTL_BIN show "$service" -p InvocationID --value 2>/dev/null || true)"
        entered="$($SYSTEMCTL_BIN show "$service" -p ActiveEnterTimestampMonotonic --value 2>/dev/null || true)"
        if [[ "$service" = *.timer ]]; then
            pid=0; restarts=0
            if ! [[ "$entered" =~ ^[0-9]+$ ]] || [ "$entered" = "${old_active_enters[$index]}" ]; then
                printf '[A0.3c] FEHLER: Timer-Aktivierung wurde nicht ersetzt: %s\n' "$service" >&2
                return 70
            fi
            continue
        fi
        pid="$($SYSTEMCTL_BIN show "$service" -p MainPID --value)"
        restarts="$($SYSTEMCTL_BIN show "$service" -p NRestarts --value)"
        if ! [[ "$pid" =~ ^[0-9]+$ ]] || ! [[ "$restarts" =~ ^[0-9]+$ ]]; then
            printf '[A0.3c] FEHLER: Dienststatus unlesbar: %s\n' "$service" >&2
            return 70
        fi
        if [ "$restarts" != "${old_restarts[$index]}" ]; then
            printf '[A0.3c] FEHLER: unerwarteter NRestarts-Drift: %s\n' "$service" >&2
            return 70
        fi
        if [ "${old_pids[$index]}" != 0 ] && [ "$pid" != 0 ]; then
            if [ "$pid" = "${old_pids[$index]}" ]; then
                printf '[A0.3c] FEHLER: Dienst-PID wurde nicht ersetzt: %s\n' "$service" >&2
                return 70
            fi
        fi
    done
    return 0
}

prove_no_db_handles() {
    local output status path
    local paths=()
    for path in "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"; do [ ! -e "$path" ] || paths+=("$path"); done
    [ "${#paths[@]}" -gt 0 ] || fail "Produkt-DB-Dateien fehlen" 65
    # psmisc' fuser kennt kein "--": es faellt in den Unbekannt-Zweig, gibt seine
    # Usage aus und liefert Status 1 -- exakt die Signatur, die hier "keine
    # Handles" bedeuten soll. Die Pfade sind per Konstruktion absolut, koennen
    # also nie als Option gelesen werden; die Absolutheit wird trotzdem geprueft.
    for path in "${paths[@]}"; do
        [[ "$path" = /* ]] || fail "Produkt-DB-Pfad ist nicht absolut" 78
    done
    set +e
    output="$(as_root "$FUSER_BIN" "${paths[@]}" 2>&1)"; status=$?
    set -e
    [ "$status" -eq 1 ] && [ -z "$output" ] || fail "offene Produkt-DB-Handles verhindern den Pointerwechsel" 70
}

prove_no_old_runtime_processes() {
    local active_core active_embed
    active_core="$(readlink -f "$CORE_POINTER/current" 2>/dev/null || printf '%s' "$CORE_POINTER")"
    active_embed="$(readlink -f "$EMBED_POINTER/current" 2>/dev/null || printf '%s' "$EMBED_POINTER")"
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$CORE_POINTER" "$EMBED_POINTER" "$active_core" "$active_embed" "$$" <<'PY'
import os, pathlib, sys
needles = tuple(os.fsencode(path) for path in sys.argv[1:5])
own = {int(sys.argv[5]), os.getpid(), os.getppid()}
found = 0
inspection_errors = 0
for entry in pathlib.Path("/proc").iterdir():
    if not entry.name.isdigit() or int(entry.name) in own:
        continue
    try:
        command = (entry / "cmdline").read_bytes()
    except (FileNotFoundError, ProcessLookupError):
        continue
    except (PermissionError, OSError):
        inspection_errors += 1
        continue
    if not command:
        continue
    try:
        maps = (entry / "maps").read_bytes()
        exe = os.fsencode(os.readlink(entry / "exe"))
    except (FileNotFoundError, ProcessLookupError):
        continue
    except (PermissionError, OSError):
        inspection_errors += 1
        continue
    file_targets = []
    try:
        descriptors = list((entry / "fd").iterdir())
    except (FileNotFoundError, ProcessLookupError):
        continue
    except (PermissionError, OSError):
        inspection_errors += 1
        continue
    for descriptor in descriptors:
        try:
            file_targets.append(os.fsencode(os.readlink(descriptor)))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (PermissionError, OSError):
            inspection_errors += 1
    if any(needle in command or needle in maps or exe.startswith(needle) or any(target.startswith(needle) for target in file_targets) for needle in needles):
        found += 1
if inspection_errors:
    raise SystemExit("process inspection was incomplete")
if found:
    raise SystemExit("old runtime process handles remain")
PY
}

backup_tree_inventory() {
    local root="$1" output="$2"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$root" "$output" <<'PY'
import hashlib, json, os, pathlib, stat, sys
root, output = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); entries=[]
if root.is_symlink() or not root.is_dir(): raise SystemExit("anchor root is not a real directory")
for path in sorted(root.rglob("*"), key=lambda item: os.fsencode(item.relative_to(root).as_posix())):
    rel=path.relative_to(root).as_posix(); info=path.lstat()
    if "\n" in rel or "\r" in rel or stat.S_ISLNK(info.st_mode): raise SystemExit("anchor path is unsafe")
    if stat.S_ISDIR(info.st_mode): entries.append({"path":rel,"type":"directory","mode":stat.S_IMODE(info.st_mode)}); continue
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise SystemExit("anchor object is not a regular single-link file")
    digest=hashlib.sha256(); fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        while chunk:=os.read(fd,1024*1024): digest.update(chunk)
    finally: os.close(fd)
    entries.append({"path":rel,"type":"file","mode":stat.S_IMODE(info.st_mode),"sha256":digest.hexdigest()})
data={"schema":"genus-a0.3c-backup-anchor-inventory-v1","entries":entries}
path=output; fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
PY
}

validate_backup_receipt() {
    local receipt="$1"
    [ -f "$receipt" ] && [ ! -L "$receipt" ] \
        && [ "$(stat -c %u "$receipt")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$receipt")" = 600 ] && [ "$(stat -c %h "$receipt")" -eq 1 ] \
        || fail "Backup-Receipt ist nicht regulaer/user-owned/0600/einfach verlinkt" 70
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$receipt" "$(repo_commit)" "$BACKUP_DIR/a03c-activation-snapshots" "$DB_PATH" \
        "$(dirname "$DB_PATH")" "$RECEIPT_ROOT" <<'PY'
import hashlib, json, os, pathlib, re, stat, sys
receipt, commit, snapshots, database, config_root, receipt_root = map(pathlib.Path, sys.argv[1:7])
commit=str(commit)
def regular(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise SystemExit("backup evidence is not a regular single-link file")
    return info
def digest(path):
    info=regular(path); fields=("st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns")
    value=hashlib.sha256(); fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        opened=os.fstat(fd)
        if any(getattr(opened,key)!=getattr(info,key) for key in fields): raise SystemExit("backup evidence changed during open")
        while chunk:=os.read(fd,1024*1024): value.update(chunk)
        final=os.fstat(fd)
        if any(getattr(final,key)!=getattr(opened,key) for key in fields): raise SystemExit("backup evidence changed during read")
    finally: os.close(fd)
    return value.hexdigest()
def contained(path, root):
    resolved=path.resolve(strict=True); expected=root.resolve(strict=True)
    if expected not in resolved.parents: raise SystemExit("backup evidence escapes its fixed root")
    return resolved
if contained(receipt,receipt_root).parent != receipt_root.resolve(strict=True): raise SystemExit("backup receipt is nested unexpectedly")
data=json.loads(receipt.read_text())
keys={"schema","repo_commit","snapshot_root","database_source_path","ledger_path","ledger_sha256","config_inventory_path","config_inventory_sha256","anchor_root","anchor_inventory_path","anchor_inventory_sha256","paths_logged","payloads_logged"}
if set(data)!=keys or data["schema"]!="genus-a0.3c-backup-v2" or data["repo_commit"]!=commit:
    raise SystemExit("backup receipt schema/commit differs")
if data["database_source_path"]!=str(database) or data["paths_logged"] is not True or data["payloads_logged"] is not False:
    raise SystemExit("backup receipt safety booleans/source differ")
snapshot=pathlib.Path(data["snapshot_root"]); contained(snapshot,snapshots)
if snapshot.parent.resolve()!=snapshots.resolve() or not snapshot.name.startswith("snapshot-") or snapshot.is_symlink() or not snapshot.is_dir() or stat.S_IMODE(snapshot.stat().st_mode)!=0o500: raise SystemExit("snapshot generation differs")
ledger=pathlib.Path(data["ledger_path"]); inventory=pathlib.Path(data["config_inventory_path"])
anchors=pathlib.Path(data["anchor_root"]); anchor_inventory=pathlib.Path(data["anchor_inventory_path"])
if ledger!=snapshot/"ledger.sqlite3" or inventory!=snapshot/"config-inventory.json" or anchors!=snapshot/"anchors" or anchor_inventory!=snapshot/"anchor-inventory.json": raise SystemExit("snapshot evidence paths differ")
for path in (ledger,inventory,anchor_inventory): contained(path,snapshot)
if digest(ledger)!=data["ledger_sha256"] or digest(inventory)!=data["config_inventory_sha256"] or digest(anchor_inventory)!=data["anchor_inventory_sha256"]: raise SystemExit("snapshot evidence digest differs")
config=json.loads(inventory.read_text()); allowed={"core_id","status_publish.enabled","chat_word_learning.enabled","remote_deuter.enabled","coder.enabled","github_models_token","telegram_bot_token","telegram_bot.env"}
if set(config)!={"schema","files","paths_logged","payloads_logged"} or config["schema"]!="genus-a0.3c-backup-config-inventory-v1" or config["paths_logged"] is not True or config["payloads_logged"] is not False or not config["files"]: raise SystemExit("config inventory schema differs")
names=[]
for item in config["files"]:
    if set(item)!={"name","source_path","snapshot_path","sha256"} or item["name"] not in allowed or not re.fullmatch(r"[0-9a-f]{64}",item["sha256"]): raise SystemExit("config inventory entry differs")
    names.append(item["name"]); source=config_root/item["name"]; copied=snapshot/"config"/item["name"]
    if item["source_path"]!=str(source) or item["snapshot_path"]!=str(copied) or digest(copied)!=item["sha256"]: raise SystemExit("config snapshot binding differs")
if len(names)!=len(set(names)): raise SystemExit("duplicate config inventory name")
config_dir=snapshot/"config"
if config_dir.is_symlink() or not config_dir.is_dir() or stat.S_IMODE(config_dir.stat().st_mode)!=0o500: raise SystemExit("config snapshot directory differs")
actual_config=list(config_dir.iterdir())
if {path.name for path in actual_config}!=set(names) or any(path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode)!=0o400 for path in actual_config): raise SystemExit("config snapshot inventory is incomplete")
anchor_data=json.loads(anchor_inventory.read_text())
if set(anchor_data)!={"schema","entries"} or anchor_data["schema"]!="genus-a0.3c-backup-anchor-inventory-v1": raise SystemExit("anchor inventory schema differs")
seen=[]
for item in anchor_data["entries"]:
    if set(item) not in ({"path","type","mode"},{"path","type","mode","sha256"}) or not isinstance(item["path"],str) or not isinstance(item["mode"],int) or isinstance(item["mode"],bool) or item["path"].startswith(("/","../")) or "\n" in item["path"]: raise SystemExit("anchor inventory entry differs")
    path=anchors/item["path"]; contained(path,anchors); seen.append(item["path"])
    if stat.S_IMODE(path.lstat().st_mode)!=item["mode"]: raise SystemExit("anchor mode differs")
    if item["type"]=="directory":
        if set(item)!={"path","type","mode"} or path.is_symlink() or not path.is_dir(): raise SystemExit("anchor directory differs")
    elif item["type"]=="file":
        if set(item)!={"path","type","mode","sha256"} or digest(path)!=item["sha256"]: raise SystemExit("anchor file differs")
    else: raise SystemExit("anchor type differs")
if seen!=sorted(seen,key=os.fsencode) or len(seen)!=len(set(seen)): raise SystemExit("anchor inventory ordering differs")
actual_anchors=sorted((path.relative_to(anchors).as_posix() for path in anchors.rglob("*")),key=os.fsencode)
if anchors.is_symlink() or not anchors.is_dir() or stat.S_IMODE(anchors.stat().st_mode)!=0o500 or actual_anchors!=seen: raise SystemExit("anchor inventory is incomplete")
PY
}

prove_no_backup_in_progress() {
    local backup_real
    backup_real="$(realpath -e -- "$BACKUP_SCRIPT")" \
        || fail "Backup-Skript ist nicht kanonisch lesbar" 65
    as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$backup_real" "$$" <<'PY'
import os, pathlib, sys
needle, own = os.fsencode(sys.argv[1]), int(sys.argv[2])
errors = 0
for entry in pathlib.Path("/proc").iterdir():
    if not entry.name.isdigit() or int(entry.name) == own: continue
    try: argv = (entry / "cmdline").read_bytes().split(b"\0")
    except (FileNotFoundError, ProcessLookupError): continue
    except (PermissionError, OSError): errors += 1; continue
    if needle in argv: raise SystemExit("cron/operator backup process is still running")
if errors: raise SystemExit("backup process inspection was incomplete")
PY
}

fresh_backup_receipt() {
    local snapshots generation partial final ledger_partial ledger config_dir inventory receipt
    local name source before after copied target ledger_hash inventory_hash
    local anchor_source anchor_copy anchor_inventory anchor_pre anchor_inventory_hash
    local -a config_args=()
    [ -f "$DB_PATH" ] && [ ! -L "$DB_PATH" ] || fail "Produkt-DB ist nicht regulaer" 65
    install -d -m 0700 "$BACKUP_DIR"
    [ "$(stat -c %d "$DB_PATH")" != "$(stat -c %d "$BACKUP_DIR")" ] \
        || fail "Activation-Snapshot liegt nicht auf einem anderen Geraet" 65
    snapshots="$BACKUP_DIR/a03c-activation-snapshots"
    install -d -m 0700 "$snapshots"
    generation="$(date -u +%Y%m%dT%H%M%S%N)-$$-$RANDOM"
    partial="$snapshots/.partial-$generation"
    final="$snapshots/snapshot-$generation"
    [ ! -e "$partial" ] && [ ! -e "$final" ] || fail "Backup-Generation kollidiert" 70
    mkdir -m 0700 -- "$partial"
    config_dir="$partial/config"
    mkdir -m 0700 -- "$config_dir"
    ledger_partial="$partial/ledger.sqlite3.partial"
    ledger="$partial/ledger.sqlite3"
    "$CORE_POINTER/bin/python" -I -P - "$DB_PATH" "$ledger_partial" <<'PY'
import os, sqlite3, sys
source = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute("pragma integrity_check").fetchone()[0] != "ok": raise SystemExit("snapshot integrity differs")
finally:
    target.close(); source.close()
fd = os.open(sys.argv[2], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try: os.fsync(fd)
finally: os.close(fd)
PY
    GENUS_DB_PATH="$ledger_partial" "$CORE_POINTER/bin/genus" integrity check >/dev/null
    GENUS_DB_PATH="$ledger_partial" "$CORE_POINTER/bin/genus" ledger verify >/dev/null
    mv -T -- "$ledger_partial" "$ledger"
    sync -f "$ledger"
    for name in core_id status_publish.enabled chat_word_learning.enabled remote_deuter.enabled coder.enabled github_models_token telegram_bot_token telegram_bot.env; do
        source="$(dirname "$DB_PATH")/$name"
        [ ! -e "$source" ] && continue
        [ -f "$source" ] && [ ! -L "$source" ] && [ "$(stat -c %h "$source")" -eq 1 ] \
            || fail "Konfigurationsquelle ist nicht regulaer/einfach verlinkt" 65
        before="$(sha256_file "$source")"
        target="$config_dir/$name"
        install -m 0600 "$source" "$target"
        sync -f "$target"
        after="$(sha256_file "$source")"; copied="$(sha256_file "$target")"
        [ "$before" = "$after" ] && [ "$after" = "$copied" ] \
            || fail "Konfigurationsquelle aenderte sich waehrend der Sicherung" 70
        config_args+=("$name" "$source" "$final/config/$name" "$copied")
    done
    [ "${#config_args[@]}" -gt 0 ] || fail "keine Konfiguration fuer Activation-Snapshot gefunden" 65
    anchor_source="$GENUS_HOME/.genus/anchors"
    anchor_copy="$partial/anchors"
    mkdir -m 0700 -- "$anchor_copy"
    anchor_pre="$STATE_ROOT/anchor-pre.$(date -u +%Y%m%dT%H%M%S%N).$$.$RANDOM.json"
    anchor_inventory="$partial/anchor-inventory.json"
    if [ -e "$anchor_source" ] || [ -L "$anchor_source" ]; then
        [ -d "$anchor_source" ] && [ ! -L "$anchor_source" ] \
            || fail "Anchor-Quelle ist kein reales Verzeichnis" 65
        [ ! -e "$anchor_pre" ] || fail "Anchor-Preinventory kollidiert" 70
        backup_tree_inventory "$anchor_source" "$anchor_pre"
        cp -a -- "$anchor_source/." "$anchor_copy/"
        find "$anchor_copy" -type d -exec chmod 0500 {} +
        find "$anchor_copy" -type f -exec chmod 0400 {} +
        backup_tree_inventory "$anchor_copy" "$anchor_inventory"
        "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
            "$anchor_pre" "$anchor_inventory" <<'PY'
import json, pathlib, sys
def content(path):
    data=json.loads(pathlib.Path(path).read_text())
    return [{key:value for key,value in item.items() if key!="mode"} for item in data["entries"]]
if content(sys.argv[1])!=content(sys.argv[2]): raise SystemExit("anchor source changed during backup")
PY
        rm -f -- "$anchor_pre"
    else
        backup_tree_inventory "$anchor_copy" "$anchor_inventory"
    fi
    inventory="$partial/config-inventory.json"
    "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
        "$inventory" "${config_args[@]}" <<'PY'
import json, os, pathlib, sys
if (len(sys.argv) - 2) % 4: raise SystemExit("config inventory arguments differ")
entries=[]
for offset in range(2, len(sys.argv), 4):
    name, source, snapshot, digest = sys.argv[offset:offset+4]
    entries.append({"name":name,"source_path":source,"snapshot_path":snapshot,"sha256":digest})
data={"schema":"genus-a0.3c-backup-config-inventory-v1","files":entries,"paths_logged":True,"payloads_logged":False}
path=pathlib.Path(sys.argv[1]); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
PY
    find "$partial" -type d -exec chmod 0500 {} +
    find "$partial" -type f -exec chmod 0400 {} +
    durably_sync_tree "$partial"
    fsync_dir "$snapshots"
    mv -T -- "$partial" "$final"
    fsync_dir "$snapshots"
    fsync_dir "$BACKUP_DIR"
    publication_fault_point after-backup-publication
    ledger="$final/ledger.sqlite3"; inventory="$final/config-inventory.json"
    anchor_copy="$final/anchors"; anchor_inventory="$final/anchor-inventory.json"
    ledger_hash="$(sha256_file "$ledger")"; inventory_hash="$(sha256_file "$inventory")"
    anchor_inventory_hash="$(sha256_file "$anchor_inventory")"
    receipt="$(receipt_target backup)"
    COMMIT="$(repo_commit)" SNAPSHOT="$final" DB_SOURCE="$DB_PATH" LEDGER="$ledger" \
    LEDGER_HASH="$ledger_hash" INVENTORY="$inventory" INVENTORY_HASH="$inventory_hash" \
    ANCHOR_ROOT="$anchor_copy" ANCHOR_INVENTORY="$anchor_inventory" ANCHOR_INVENTORY_HASH="$anchor_inventory_hash" \
        "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import json, os, pathlib, sys
data={"schema":"genus-a0.3c-backup-v2","repo_commit":os.environ["COMMIT"],
      "snapshot_root":os.environ["SNAPSHOT"],"database_source_path":os.environ["DB_SOURCE"],
      "ledger_path":os.environ["LEDGER"],"ledger_sha256":os.environ["LEDGER_HASH"],
      "config_inventory_path":os.environ["INVENTORY"],"config_inventory_sha256":os.environ["INVENTORY_HASH"],
      "anchor_root":os.environ["ANCHOR_ROOT"],"anchor_inventory_path":os.environ["ANCHOR_INVENTORY"],
      "anchor_inventory_sha256":os.environ["ANCHOR_INVENTORY_HASH"],
      "paths_logged":True,"payloads_logged":False}
path=pathlib.Path(sys.argv[1]); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    validate_backup_receipt "$receipt"
    printf '%s\n' "$receipt"
}

verify_readiness_manifest() {
    local set_manifest="$1" expected="$2" readiness="$3" set root resolved receipt
    [[ "$set_manifest" =~ ^[a-f0-9]{64}$ ]] || fail "Legacy-Set kann nicht neu aktiviert werden" 65
    [ -f "$readiness" ] && [ ! -L "$readiness" ] || fail "Readiness-Manifest fehlt oder ist ein Link" 65
    [ "$(stat -c %U "$readiness")" = "$GENUS_USER" ] && [ "$(stat -c %a "$readiness")" = 600 ] \
        || fail "Readiness-Manifest muss user-owned 0600 sein" 65
    root="$GENUS_HOME/.genus/a0.3c/readiness"
    resolved="$(realpath -e -- "$readiness")"
    case "$resolved" in "$root"/*) ;; *) fail "Readiness-Manifest liegt nicht im privaten Evidence-Root" 65 ;; esac
    [ -z "$(find "$root" -type d -perm /077 -print -quit)" ] \
        || fail "Readiness-Evidence-Verzeichnis ist nicht privat" 65
    set="$(set_path "$set_manifest")"
    receipt="$(receipt_target manifest-verify)"
    [ ! -e "$receipt" ] || fail "Verification-Receipt-Ziel existiert" 65
    (
        cd "$REPO_DIR"
        "$set/core/bin/python" -m experiments.a0_3c manifest-verify \
            --manifest "$resolved" --receipt "$receipt" --code-root "$REPO_DIR" \
            --expected-invocation "$set/core/bin/python"
    ) >/dev/null
    [ -f "$receipt" ] && [ "$(stat -c %a "$receipt")" = 600 ] \
        || fail "Readiness-Verifikation lieferte keinen privaten Receipt" 65
    sync -f "$receipt"; fsync_dir "$RECEIPT_ROOT"
    "$set/core/bin/python" - "$receipt" "$expected" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
if data.get("schema") != "genus-a0-3c-manifest-verification-v1":
    raise SystemExit("readiness verification schema differs")
if data.get("outcome") != "verified" or data.get("candidate_commit") != sys.argv[2]:
    raise SystemExit("readiness verification did not bind expected commit")
if data.get("expected_invocation_attested") is not True:
    raise SystemExit("candidate invocation was not attested")
PY
    printf '%s\n' "$receipt"
}

attest_active_pointer_unit() {
    local manifest="$1" set receipt
    set="$(set_path "$manifest")"
    [ "$(readlink -f "$CORE_POINTER/current")" = "$(readlink -f "$set/core")" ] \
        && [ "$(readlink -f "$EMBED_POINTER/current")" = "$(readlink -f "$set/embed")" ] \
        || fail "aktive Core-/Embed-Pointer bilden nicht dasselbe Set" 70
    "$CORE_POINTER/bin/python" - "$CORE_POINTER/bin/python" "$RUNTIME_PREFIX/bin/python3.13" <<'PY'
import pathlib, sys
if sys.version.split()[0] != "3.13.15" or sys.version_info[:3] != (3, 13, 15):
    raise SystemExit("stable core invocation uses wrong CPython")
if pathlib.Path(sys.executable).absolute() != pathlib.Path(sys.argv[1]).absolute():
    raise SystemExit("stable core invocation path is not sys.executable")
if pathlib.Path(sys._base_executable).resolve() != pathlib.Path(sys.argv[2]).resolve():
    raise SystemExit("stable core invocation does not use pinned base runtime")
PY
    "$EMBED_POINTER/bin/python" - "$EMBED_POINTER/bin/python" "$RUNTIME_PREFIX/bin/python3.13" <<'PY'
import pathlib, sqlite3, sys
from fastembed import TextEmbedding  # noqa: F401
if sys.version.split()[0] != "3.13.15" or sys.version_info[:3] != (3, 13, 15):
    raise SystemExit("stable embed invocation uses wrong CPython")
if pathlib.Path(sys.executable).absolute() != pathlib.Path(sys.argv[1]).absolute():
    raise SystemExit("stable embed invocation path is not sys.executable")
if pathlib.Path(sys._base_executable).resolve() != pathlib.Path(sys.argv[2]).resolve():
    raise SystemExit("stable embed invocation does not use pinned base runtime")
if sqlite3.sqlite_version != "3.53.4":
    raise SystemExit("stable embed invocation uses wrong SQLite")
PY
    receipt="$(receipt_target active-identity)"
    (
        cd "$REPO_DIR"
        "$CORE_POINTER/bin/python" -m experiments.a0_3c identity \
            --receipt "$receipt" --expected-invocation "$CORE_POINTER/bin/python"
    ) >/dev/null
    [ -f "$receipt" ] && [ "$(stat -c %a "$receipt")" = 600 ] \
        || fail "aktive Invocation-Attestation fehlt" 70
    sync -f "$receipt"; fsync_dir "$RECEIPT_ROOT"
    printf '%s\n' "$receipt"
}

attest_restarted_services() {
    local deadline=$((SECONDS + 30)) consecutive=0 index service pid restarts sample_ok active
    local invocation entered bot_attested learner_attested names_csv pids_csv restarts_csv target
    local invocations_csv enters_csv types_csv
    local -a names=() pids=() restarts_seen=() invocations=() enters=() types=()
    while [ "$SECONDS" -lt "$deadline" ]; do
        sample_ok=1
        bot_attested=0
        learner_attested=0
        names=(); pids=(); restarts_seen=(); invocations=(); enters=(); types=()
        for index in "${!active_services[@]}"; do
            service="${active_services[$index]}"
            active="$($SYSTEMCTL_BIN show "$service" -p ActiveState --value 2>/dev/null || true)"
            [ "$active" = active ] || { sample_ok=0; break; }
            invocation="$($SYSTEMCTL_BIN show "$service" -p InvocationID --value 2>/dev/null || true)"
            entered="$($SYSTEMCTL_BIN show "$service" -p ActiveEnterTimestampMonotonic --value 2>/dev/null || true)"
            if [[ "$service" = *.timer ]]; then
                pid=0; restarts=0
                if ! [[ "$entered" =~ ^[0-9]+$ ]] || [ "$entered" = "${old_active_enters[$index]}" ]; then
                    sample_ok=0
                    break
                fi
                types+=(timer)
            else
                pid="$($SYSTEMCTL_BIN show "$service" -p MainPID --value 2>/dev/null || true)"
                restarts="$($SYSTEMCTL_BIN show "$service" -p NRestarts --value 2>/dev/null || true)"
                if ! [[ "$pid" =~ ^[0-9]+$ ]] || ! [[ "$restarts" =~ ^[0-9]+$ ]] \
                    || [ "$restarts" != "${old_restarts[$index]}" ]; then
                    sample_ok=0
                    break
                fi
                types+=(service)
            fi
            if [ "$restarts" != "${old_restarts[$index]}" ]; then
                sample_ok=0
                break
            fi
            if [ "${old_pids[$index]}" != 0 ] && [ "$pid" != 0 ] \
                && [ "$pid" = "${old_pids[$index]}" ]; then
                sample_ok=0
                break
            fi
            case "$service" in
                genus-telegram-bot.service)
                    if ! as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
                        "$pid" "$RUNTIME_PREFIX" "$CORE_POINTER/bin/python" <<'PY' >/dev/null 2>&1
import os, pathlib, sys
pid, prefix, stable = sys.argv[1:4]
command = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
maps = pathlib.Path(f"/proc/{pid}/maps").read_bytes()
if os.fsencode(stable) not in command or os.fsencode(prefix + "/") not in maps:
    raise SystemExit("bot process does not use the selected private runtime")
PY
                    then sample_ok=0; break; fi
                    bot_attested=1
                    ;;
                genus-learner.service)
                    if ! as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - \
                        "$pid" "$REPO_DIR/deploy/pi_learn.sh" <<'PY' >/dev/null 2>&1
import os, pathlib, sys
command = pathlib.Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes().split(b"\0")
if os.fsencode(sys.argv[2]) not in command:
    raise SystemExit("learner process is not the pinned repository script")
PY
                    then sample_ok=0; break; fi
                    learner_attested=1
                    ;;
            esac
            names+=("$service"); pids+=("$pid"); restarts_seen+=("$restarts")
            invocations+=("${invocation:--}"); enters+=("$entered")
        done
        if [ "$sample_ok" -eq 1 ]; then
            consecutive=$((consecutive + 1))
            [ "$consecutive" -ge 3 ] && break
        else
            consecutive=0
        fi
        sleep 1
    done
    [ "$consecutive" -ge 3 ] || { printf '[A0.3c] FEHLER: Dienst-Postflight blieb unvollstaendig\n' >&2; return 70; }
    if [[ " ${active_services[*]} " == *" genus-telegram-bot.service "* ]] && [ "$bot_attested" -ne 1 ]; then
        printf '[A0.3c] FEHLER: Bot-Runtime wurde nicht attestiert\n' >&2
        return 70
    fi
    if [[ " ${active_services[*]} " == *" genus-learner.service "* ]] && [ "$learner_attested" -ne 1 ]; then
        printf '[A0.3c] FEHLER: Learner-Aufrufpfad wurde nicht attestiert\n' >&2
        return 70
    fi
    names_csv="$(IFS=,; printf '%s' "${names[*]}")"
    pids_csv="$(IFS=,; printf '%s' "${pids[*]}")"
    restarts_csv="$(IFS=,; printf '%s' "${restarts_seen[*]}")"
    invocations_csv="$(IFS=,; printf '%s' "${invocations[*]}")"
    enters_csv="$(IFS=,; printf '%s' "${enters[*]}")"
    types_csv="$(IFS=,; printf '%s' "${types[*]}")"
    target="$(receipt_target service-postflight)"
    [ ! -e "$target" ] || { printf '[A0.3c] FEHLER: Postflight-Receipt existiert bereits\n' >&2; return 70; }
    NAMES="$names_csv" PIDS="$pids_csv" RESTARTS="$restarts_csv" \
    INVOCATIONS="$invocations_csv" ACTIVE_ENTERS="$enters_csv" UNIT_TYPES="$types_csv" \
    BOT_ATTESTED="$bot_attested" LEARNER_ATTESTED="$learner_attested" \
        "$CORE_POINTER/bin/python" - "$target" <<'PY'
import hashlib, json, os, pathlib, sys
names = os.environ["NAMES"].split(",") if os.environ["NAMES"] else []
pids = [int(item) for item in os.environ["PIDS"].split(",") if item]
restarts = [int(item) for item in os.environ["RESTARTS"].split(",") if item]
invocations = os.environ["INVOCATIONS"].split(",") if os.environ["INVOCATIONS"] else []
enters = [int(item) for item in os.environ["ACTIVE_ENTERS"].split(",") if item]
unit_types = os.environ["UNIT_TYPES"].split(",") if os.environ["UNIT_TYPES"] else []
if not (len(names) == len(pids) == len(restarts) == len(invocations) == len(enters) == len(unit_types)):
    raise SystemExit("service postflight arrays differ")
services = [
    {"service": name, "unit_type": unit_type, "main_pid": pid, "nrestarts": restart,
     "active_state": "active", "invocation_id": invocation,
     "active_enter_timestamp_monotonic": entered}
    for name, unit_type, pid, restart, invocation, entered
    in zip(names, unit_types, pids, restarts, invocations, enters, strict=True)
]
state_bytes = json.dumps(services, sort_keys=True, separators=(",", ":")).encode()
data = {
    "schema": "genus-a0.3c-runtime-service-postflight-v1",
    "outcome": "verified",
    "consecutive_samples": 3,
    "services": services,
    "service_state_sha256": hashlib.sha256(state_bytes).hexdigest(),
    "bot_private_runtime_attested": os.environ["BOT_ATTESTED"] == "1",
    "learner_pinned_script_attested": os.environ["LEARNER_ATTESTED"] == "1",
    "paths_logged": False,
    "payloads_logged": False,
}
path=pathlib.Path(sys.argv[1]); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    printf '%s\n' "$target"
}

write_activation_receipt() {
    local manifest="$1" expected="$2" readiness="$3" verification="$4" previous="$5"
    local backup="$6" postflight="$7" identity="$8" target service_state evidence
    local target_manifest_path previous_manifest_path reauth reauth_hash
    safe_manifest_id "$manifest"
    safe_manifest_id "$previous"
    service_state="$($CORE_POINTER/bin/python - "$postflight" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
if data.get("schema") != "genus-a0.3c-runtime-service-postflight-v1" or data.get("outcome") != "verified":
    raise SystemExit("service postflight receipt differs")
print(data["service_state_sha256"])
PY
)"
    target_manifest_path="$SETS_ROOT/$manifest/manifest.json"
    previous_manifest_path="$SETS_ROOT/$previous/manifest.json"
    reauth="${OPERATOR_REAUTH_RECEIPT:-}"; reauth_hash=""
    [ -z "$reauth" ] || reauth_hash="$(sha256_file "$reauth")"
    for evidence in "$backup" "$readiness" "$verification" "$postflight" "$identity" "$target_manifest_path" "$previous_manifest_path"; do
        [ -f "$evidence" ] && [ ! -L "$evidence" ] && [ "$(stat -c %h "$evidence")" -eq 1 ] \
            || fail "Activation-Evidence ist nicht regulaer/einfach verlinkt" 70
        sync -f "$evidence"; fsync_dir "$(dirname "$evidence")"
    done
    if [ -n "$reauth" ]; then sync -f "$reauth"; fsync_dir "$(dirname "$reauth")"; fi
    target="$(receipt_target activation)"
    MANIFEST="$manifest" PREVIOUS="$previous" COMMIT="$expected" \
    TARGET_MANIFEST_PATH="$target_manifest_path" TARGET_MANIFEST_HASH="$(sha256_file "$target_manifest_path")" \
    PREVIOUS_MANIFEST_PATH="$previous_manifest_path" PREVIOUS_MANIFEST_HASH="$(sha256_file "$previous_manifest_path")" \
    BACKUP_RECEIPT="$backup" BACKUP_HASH="$(sha256_file "$backup")" \
    READINESS_MANIFEST="$readiness" READINESS_HASH="$(sha256_file "$readiness")" \
    VERIFICATION_RECEIPT="$verification" VERIFICATION_HASH="$(sha256_file "$verification")" \
    POSTFLIGHT_RECEIPT="$postflight" POSTFLIGHT_HASH="$(sha256_file "$postflight")" \
    IDENTITY_RECEIPT="$identity" IDENTITY_HASH="$(sha256_file "$identity")" SERVICE_STATE="$service_state" \
    REAUTH_RECEIPT="$reauth" REAUTH_HASH="$reauth_hash" \
        "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$target" <<'PY'
import json, os, pathlib, sys
data={"schema":"genus-a0.3c-runtime-activation-v2","outcome":"activated","candidate_commit":os.environ["COMMIT"],
      "previous_set_manifest":os.environ["PREVIOUS"],"previous_set_manifest_path":os.environ["PREVIOUS_MANIFEST_PATH"],"previous_set_manifest_sha256":os.environ["PREVIOUS_MANIFEST_HASH"],
      "activated_set_manifest":os.environ["MANIFEST"],"activated_set_manifest_path":os.environ["TARGET_MANIFEST_PATH"],"activated_set_manifest_sha256":os.environ["TARGET_MANIFEST_HASH"],
      "backup_receipt_path":os.environ["BACKUP_RECEIPT"],"backup_receipt_sha256":os.environ["BACKUP_HASH"],
      "readiness_manifest_path":os.environ["READINESS_MANIFEST"],"readiness_manifest_sha256":os.environ["READINESS_HASH"],
      "verification_receipt_path":os.environ["VERIFICATION_RECEIPT"],"verification_receipt_sha256":os.environ["VERIFICATION_HASH"],
      "active_identity_receipt_path":os.environ["IDENTITY_RECEIPT"],"active_identity_receipt_sha256":os.environ["IDENTITY_HASH"],
      "postflight_receipt_path":os.environ["POSTFLIGHT_RECEIPT"],"postflight_receipt_sha256":os.environ["POSTFLIGHT_HASH"],
      "operator_reauthorization_receipt_path":os.environ["REAUTH_RECEIPT"],"operator_reauthorization_receipt_sha256":os.environ["REAUTH_HASH"],
      "service_state_sha256":os.environ["SERVICE_STATE"],"core_embed_single_selector":True,
      "database_rollback_performed":False,"paths_logged":True,"payloads_logged":False}
path=pathlib.Path(sys.argv[1]); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    printf '%s\n' "$target"
}

write_transition_completion_receipt() {
    local outcome="$1" active active_hash services_csv target python
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"
    [ "${#recovery_services[@]}" -gt 0 ] || fail "Completion-Receipt braucht Service-Inventar" 70
    services_csv="$(IFS=,; printf '%s' "${recovery_services[*]}")"
    target="$RECEIPT_ROOT/completion-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
    [ ! -e "$target" ] || fail "Completion-Receipt existiert bereits" 70
    python="$(journal_python)"
    OUTCOME="$outcome" COMMIT="$(repo_commit)" ACTIVE="$active" ACTIVE_HASH="$active_hash" \
    AUTH_HASH="$(sha256_file "$AUTOSTART_APPROVAL")" SERVICES_CSV="$services_csv" \
        "$python" - "$target" <<'PY'
import json, os, pathlib, sys
if os.environ["OUTCOME"] not in {"rollback-restored","interrupted-restored"}:
    raise SystemExit("completion outcome differs")
data={"schema":"genus-a0.3c-runtime-transition-completion-v1","outcome":os.environ["OUTCOME"],
      "repo_commit":os.environ["COMMIT"],"active_manifest":os.environ["ACTIVE"],
      "active_manifest_sha256":os.environ["ACTIVE_HASH"],
      "start_authorization_sha256":os.environ["AUTH_HASH"],
      "active_services":[item for item in os.environ["SERVICES_CSV"].split(",") if item],
      "database_rollback_performed":False}
path=pathlib.Path(sys.argv[1]); flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
if hasattr(os,"O_NOFOLLOW"): flags|=os.O_NOFOLLOW
fd=os.open(path,flags,0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    printf '%s\n' "$target"
}

validate_completion_receipt() {
    local receipt="$1" python active previous schema backup
    [ -f "$receipt" ] && [ ! -L "$receipt" ] \
        && [ "$(stat -c %u "$receipt")" -eq "$(id -u)" ] \
        && [ "$(stat -c %a "$receipt")" = 600 ] && [ "$(stat -c %h "$receipt")" -eq 1 ] \
        || fail "Completion-Receipt ist nicht regulaer/user-owned/0600/einfach verlinkt" 70
    active="$(selector_manifest)"; python="$(journal_python)"
    schema="$("$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import json, pathlib, sys
value=json.loads(pathlib.Path(sys.argv[1]).read_text()).get("schema")
if not isinstance(value,str): raise SystemExit("completion schema is missing")
print(value)
PY
)"
    if [ "$schema" = genus-a0.3c-runtime-activation-v2 ]; then
        previous="$(selector_manifest "$PREVIOUS_LINK")"
        verify_target "$active" >/dev/null
        verify_target "$previous" >/dev/null
        backup="$("$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import json, pathlib, sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
print(data["backup_receipt_path"])
PY
)"
        validate_backup_receipt "$backup"
        COMMIT="$(repo_commit)" ACTIVE="$active" PREVIOUS="$previous" \
        ACTIVE_HASH="$(manifest_file_hash "$active")" PREVIOUS_HASH="$(manifest_file_hash "$previous")" \
        RECEIPT_ROOT_ENV="$RECEIPT_ROOT" READINESS_ROOT="$GENUS_HOME/.genus/a0.3c/readiness" \
        SETS_ROOT_ENV="$SETS_ROOT" CORE_STABLE="$CORE_POINTER/bin/python" JOURNAL="$ACTIVATION_JOURNAL" \
        BOOT_GUARD="$BOOT_GUARD_PATH" \
            "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import hashlib, json, os, pathlib, re, stat, sys
HEX=re.compile(r"[0-9a-f]{64}")
receipt=pathlib.Path(sys.argv[1]); receipt_root=pathlib.Path(os.environ["RECEIPT_ROOT_ENV"]).resolve()
readiness_root=pathlib.Path(os.environ["READINESS_ROOT"]).resolve(); sets_root=pathlib.Path(os.environ["SETS_ROOT_ENV"]).resolve()
commit, active, previous=os.environ["COMMIT"],os.environ["ACTIVE"],os.environ["PREVIOUS"]
def canonical(value): return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",", ":")).encode()
def stable_bytes(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: raise SystemExit("activation evidence is not a regular single-link file")
    fields=("st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        opened=os.fstat(fd)
        if any(getattr(opened,k)!=getattr(info,k) for k in fields): raise SystemExit("activation evidence changed during open")
        chunks=[]
        while chunk:=os.read(fd,1024*1024): chunks.append(chunk)
        final=os.fstat(fd)
        if any(getattr(final,k)!=getattr(opened,k) for k in fields): raise SystemExit("activation evidence changed during read")
    finally: os.close(fd)
    return b"".join(chunks)
def load(path_value,hash_value,root,direct=False):
    if not isinstance(path_value,str) or not HEX.fullmatch(str(hash_value)): raise SystemExit("activation evidence path/hash is malformed")
    path=pathlib.Path(path_value); resolved=path.resolve(strict=True); expected=root.resolve(strict=True)
    if expected not in resolved.parents or (direct and resolved.parent!=expected): raise SystemExit("activation evidence escapes its fixed root")
    payload=stable_bytes(path)
    if hashlib.sha256(payload).hexdigest()!=hash_value: raise SystemExit("activation evidence hash differs")
    return path,json.loads(payload)
def sealed(data,label):
    digest=data.get("receipt_sha256"); unsigned={k:v for k,v in data.items() if k!="receipt_sha256"}
    if not isinstance(digest,str) or digest!=hashlib.sha256(canonical(unsigned)).hexdigest(): raise SystemExit(f"{label} internal digest differs")
def identity(data,label):
    keys={"schema","runtime_fingerprint","runtime_fingerprint_sha256","invocation_identity","invocation_identity_sha256","environment","paths_logged","payloads_logged","identity_sha256"}
    if set(data)!=keys or data["schema"]!="genus-a0-3c-runtime-identity-v1" or data["paths_logged"] is not False or data["payloads_logged"] is not False: raise SystemExit(f"{label} identity schema differs")
    unsigned={k:v for k,v in data.items() if k!="identity_sha256"}
    if data["identity_sha256"]!=hashlib.sha256(canonical(unsigned)).hexdigest() or data["runtime_fingerprint_sha256"]!=hashlib.sha256(canonical(data["runtime_fingerprint"])).hexdigest() or data["invocation_identity_sha256"]!=hashlib.sha256(canonical(data["invocation_identity"])).hexdigest(): raise SystemExit(f"{label} identity digest differs")
    fingerprint=data["runtime_fingerprint"]; invocation=data["invocation_identity"]
    if fingerprint.get("exact_runtime_gate_pass") is not True or fingerprint.get("python_version_info")!=[3,13,15] or fingerprint.get("sqlite_version")!="3.53.4": raise SystemExit(f"{label} runtime gate differs")
    if invocation.get("expected_invocation_path_supplied") is not True or invocation.get("expected_invocation_lexical_match") is not True or invocation.get("expected_invocation_same_file") is not True or invocation.get("expected_invocation_attested") is not True: raise SystemExit(f"{label} invocation is not exact")
    return fingerprint
top=json.loads(stable_bytes(receipt))
keys={"schema","outcome","candidate_commit","previous_set_manifest","previous_set_manifest_path","previous_set_manifest_sha256","activated_set_manifest","activated_set_manifest_path","activated_set_manifest_sha256","backup_receipt_path","backup_receipt_sha256","readiness_manifest_path","readiness_manifest_sha256","verification_receipt_path","verification_receipt_sha256","active_identity_receipt_path","active_identity_receipt_sha256","postflight_receipt_path","postflight_receipt_sha256","operator_reauthorization_receipt_path","operator_reauthorization_receipt_sha256","service_state_sha256","core_embed_single_selector","database_rollback_performed","paths_logged","payloads_logged"}
if set(top)!=keys or top["schema"]!="genus-a0.3c-runtime-activation-v2" or top["outcome"]!="activated" or top["candidate_commit"]!=commit or top["activated_set_manifest"]!=active or top["previous_set_manifest"]!=previous: raise SystemExit("activation receipt schema/selector binding differs")
if top["core_embed_single_selector"] is not True or top["database_rollback_performed"] is not False or top["paths_logged"] is not True or top["payloads_logged"] is not False: raise SystemExit("activation receipt safety booleans differ")
target_path,target=load(top["activated_set_manifest_path"],top["activated_set_manifest_sha256"],sets_root/active)
previous_path,previous_data=load(top["previous_set_manifest_path"],top["previous_set_manifest_sha256"],sets_root/previous)
if target_path!=(sets_root/active/"manifest.json") or previous_path!=(sets_root/previous/"manifest.json") or target.get("schema")!="genus-a0.3c-runtime-set-v1" or target.get("manifest_id")!=active or target.get("repo_commit")!=commit or previous_data.get("manifest_id")!=previous: raise SystemExit("set manifest evidence differs")
_,backup=load(top["backup_receipt_path"],top["backup_receipt_sha256"],receipt_root,True)
if backup.get("schema")!="genus-a0.3c-backup-v2" or backup.get("repo_commit")!=commit: raise SystemExit("backup crossbinding differs")
_,readiness=load(top["readiness_manifest_path"],top["readiness_manifest_sha256"],readiness_root)
readiness_keys={"schema","candidate_commit","runtime_identity","runtime_identity_sha256","runtime_fingerprint","candidate_invocation_identity_sha256","a0_3b_code_sha256","a0_3c_code_sha256","candidate_config","gate_evidence","retuning_allowed_within_series","product_activation_authorized","paths_logged","payloads_logged","manifest_sha256"}
if set(readiness)!=readiness_keys or readiness["schema"]!="genus-a0-3c-runtime-manifest-v1" or readiness["candidate_commit"]!=commit or readiness["manifest_sha256"]!=hashlib.sha256(canonical({k:v for k,v in readiness.items() if k!="manifest_sha256"})).hexdigest() or readiness["retuning_allowed_within_series"] is not False or readiness["product_activation_authorized"] is not False or readiness["paths_logged"] is not False or readiness["payloads_logged"] is not False: raise SystemExit("readiness manifest contract differs")
pinned_fingerprint=identity(readiness["runtime_identity"],"readiness")
if readiness["runtime_identity_sha256"]!=readiness["runtime_identity"]["identity_sha256"] or readiness["runtime_fingerprint"]!=pinned_fingerprint: raise SystemExit("readiness identity binding differs")
_,verification=load(top["verification_receipt_path"],top["verification_receipt_sha256"],receipt_root,True)
verify_keys={"schema","outcome","manifest_sha256","candidate_commit","runtime_identity_sha256","current_invocation_identity_sha256","expected_invocation_attested","candidate_config_sha256","a0_3b_code_sha256","a0_3c_code_sha256","gate_evidence","wal_reset_fix_gate_pass","paths_logged","payloads_logged","receipt_sha256"}
if set(verification)!=verify_keys or verification["schema"]!="genus-a0-3c-manifest-verification-v1": raise SystemExit("verification receipt schema differs")
sealed(verification,"verification")
if verification["outcome"]!="verified" or verification["candidate_commit"]!=commit or verification["manifest_sha256"]!=readiness["manifest_sha256"] or verification["runtime_identity_sha256"]!=readiness["runtime_identity_sha256"] or verification["current_invocation_identity_sha256"]!=readiness["candidate_invocation_identity_sha256"] or verification["candidate_config_sha256"]!=hashlib.sha256(canonical(readiness["candidate_config"])).hexdigest() or verification["a0_3b_code_sha256"]!=readiness["a0_3b_code_sha256"] or verification["a0_3c_code_sha256"]!=readiness["a0_3c_code_sha256"] or verification["gate_evidence"]!=readiness["gate_evidence"] or verification["expected_invocation_attested"] is not True or verification["wal_reset_fix_gate_pass"] is not True or verification["paths_logged"] is not False or verification["payloads_logged"] is not False: raise SystemExit("verification/readiness crossbinding differs")
_,active_identity=load(top["active_identity_receipt_path"],top["active_identity_receipt_sha256"],receipt_root,True)
active_fingerprint=identity(active_identity,"active")
stable_binding=hashlib.sha256(os.fsencode(os.path.normcase(os.path.abspath(os.environ["CORE_STABLE"])))).hexdigest()
if active_fingerprint!=pinned_fingerprint or active_identity["invocation_identity"].get("expected_invocation_path_sha256")!=stable_binding: raise SystemExit("active runtime/stable invocation differs from readiness")
_,postflight=load(top["postflight_receipt_path"],top["postflight_receipt_sha256"],receipt_root,True)
post_keys={"schema","outcome","consecutive_samples","services","service_state_sha256","bot_private_runtime_attested","learner_pinned_script_attested","paths_logged","payloads_logged"}
if set(postflight)!=post_keys or postflight["schema"]!="genus-a0.3c-runtime-service-postflight-v1" or postflight["outcome"]!="verified" or postflight["consecutive_samples"]!=3 or postflight["paths_logged"] is not False or postflight["payloads_logged"] is not False: raise SystemExit("postflight schema differs")
services=postflight["services"]
if postflight["service_state_sha256"]!=hashlib.sha256(canonical(services)).hexdigest() or top["service_state_sha256"]!=postflight["service_state_sha256"]: raise SystemExit("service state digest differs")
journal=json.loads(stable_bytes(pathlib.Path(os.environ["JOURNAL"])))
allowed={"genus-network-watchdog.timer","genus-network-watchdog.service","genus-learner.service","genus-telegram-bot.service","genus-telegram-bot-fallback.service"}
if [item.get("service") for item in services]!=journal["prior_active_services"] or len({item.get("service") for item in services})!=len(services) or any(set(item)!={"service","unit_type","main_pid","nrestarts","active_state","invocation_id","active_enter_timestamp_monotonic"} or item.get("service") not in allowed or item.get("active_state")!="active" or item.get("unit_type")!=("timer" if item.get("service","").endswith(".timer") else "service") or not isinstance(item.get("main_pid"),int) or isinstance(item.get("main_pid"),bool) or item.get("main_pid",-1)<0 or not isinstance(item.get("nrestarts"),int) or isinstance(item.get("nrestarts"),bool) or item.get("nrestarts",-1)<0 or not isinstance(item.get("active_enter_timestamp_monotonic"),int) or isinstance(item.get("active_enter_timestamp_monotonic"),bool) or item.get("active_enter_timestamp_monotonic",0)<=0 or not isinstance(item.get("invocation_id"),str) or not item.get("invocation_id") for item in services): raise SystemExit("postflight service inventory differs")
names={item["service"] for item in services}
if postflight["bot_private_runtime_attested"] is not ("genus-telegram-bot.service" in names) or postflight["learner_pinned_script_attested"] is not ("genus-learner.service" in names): raise SystemExit("postflight invocation booleans differ")
reauth_path,reauth_hash=top["operator_reauthorization_receipt_path"],top["operator_reauthorization_receipt_sha256"]
if bool(reauth_path)!=bool(reauth_hash): raise SystemExit("reauthorization path/hash pair differs")
if reauth_path:
    _,reauth=load(reauth_path,reauth_hash,receipt_root,True)
    reauth_keys={"schema","old_commit","new_commit","old_tree","new_tree","active_manifest","active_manifest_sha256","stale_approval_path","stale_approval_sha256","guard_path","guard_sha256","allowed_diff_sha256","intended_command","boot_approval_updated","paths_logged","payloads_logged"}
    if set(reauth)!=reauth_keys or reauth["schema"]!="genus-a0.3c-operator-reauthorization-v1" or reauth["new_commit"]!=commit or reauth["active_manifest"]!=previous or reauth["active_manifest_sha256"]!=top["previous_set_manifest_sha256"] or reauth["intended_command"]!="stage-and-activate" or reauth["boot_approval_updated"] is not False or reauth["paths_logged"] is not True or reauth["payloads_logged"] is not False: raise SystemExit("operator reauthorization binding differs")
    if not re.fullmatch(r"[0-9a-f]{40}",reauth["old_commit"]) or any(not HEX.fullmatch(str(reauth[key])) for key in ("old_tree","new_tree","active_manifest_sha256","stale_approval_sha256","guard_sha256","allowed_diff_sha256")): raise SystemExit("operator reauthorization digest differs")
    stale_path,stale=load(reauth["stale_approval_path"],reauth["stale_approval_sha256"],receipt_root,True)
    if stale.get("schema")!="genus-a0.3c-runtime-start-authorization-v2" or stale.get("repo_commit")!=reauth["old_commit"] or stale.get("active_manifest")!=previous or stale.get("active_manifest_sha256")!=reauth["active_manifest_sha256"]: raise SystemExit("stale approval evidence differs")
    guard=pathlib.Path(reauth["guard_path"])
    if guard!=pathlib.Path(os.environ["BOOT_GUARD"]) or hashlib.sha256(stable_bytes(guard)).hexdigest()!=reauth["guard_sha256"]: raise SystemExit("reauthorization guard evidence differs")
PY
        return 0
    fi
    COMMIT="$(repo_commit)" ACTIVE="$active" ACTIVE_HASH="$(manifest_file_hash "$active")" \
    AUTH_HASH="$(sha256_file "$AUTOSTART_APPROVAL")" \
        "$python" - "$receipt" <<'PY'
import json, os, pathlib, sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
if data.get("schema") == "genus-a0.3c-runtime-transition-completion-v1":
    if set(data) != {"schema","outcome","repo_commit","active_manifest","active_manifest_sha256","start_authorization_sha256","active_services","database_rollback_performed"}:
        raise SystemExit("transition completion schema differs")
    if data["outcome"] not in {"rollback-restored","interrupted-restored"} or data["repo_commit"] != os.environ["COMMIT"] or data["active_manifest"] != os.environ["ACTIVE"] or data["active_manifest_sha256"] != os.environ["ACTIVE_HASH"] or data["start_authorization_sha256"] != os.environ["AUTH_HASH"] or not data["active_services"] or data["database_rollback_performed"] is not False:
        raise SystemExit("transition completion binding differs")
else: raise SystemExit("completion receipt schema differs")
PY
}

journal_field() {
    local field="$1" python
    python="$(journal_python)"
    "$python" - "$ACTIVATION_JOURNAL" "$field" <<'PY'
import json, pathlib, sys
value=json.loads(pathlib.Path(sys.argv[1]).read_text())[sys.argv[2]]
if isinstance(value, (dict, list)): raise SystemExit("journal field is not scalar")
print(value)
PY
}

journal_service_lines() {
    local python
    python="$(journal_python)"
    "$python" - "$ACTIVATION_JOURNAL" <<'PY'
import json, pathlib, sys
allowed={"genus-network-watchdog.timer","genus-network-watchdog.service","genus-learner.service","genus-telegram-bot.service","genus-telegram-bot-fallback.service"}
values=json.loads(pathlib.Path(sys.argv[1]).read_text())["prior_active_services"]
if len(values)!=len(set(values)) or any(value not in allowed for value in values):
    raise SystemExit("journal service inventory differs")
print("\n".join(values))
PY
}

stop_all_genus_units() {
    local unit load_state result=0
    for unit in "${AUTOSTART_UNITS[@]}"; do
        load_state="$($SYSTEMCTL_BIN show "$unit" -p LoadState --value 2>/dev/null || true)"
        [ "$load_state" = not-found ] && continue
        systemctl_root stop "$unit" || result=70
    done
    return "$result"
}

start_recorded_services() {
    local unit active
    validate_autostart_approval
    for unit in "${recovery_services[@]}"; do
        systemctl_root start "$unit" || return 70
        active="$($SYSTEMCTL_BIN show "$unit" -p ActiveState --value 2>/dev/null || true)"
        [ "$active" = active ] || return 70
    done
}

attest_recovered_services() {
    local deadline=$((SECONDS + 30)) consecutive=0 unit active pid restarts entered ok
    while [ "$SECONDS" -lt "$deadline" ]; do
        ok=1
        for unit in "${recovery_services[@]}"; do
            active="$($SYSTEMCTL_BIN show "$unit" -p ActiveState --value 2>/dev/null || true)"
            [ "$active" = active ] || { ok=0; break; }
            if [[ "$unit" = *.timer ]]; then
                entered="$($SYSTEMCTL_BIN show "$unit" -p ActiveEnterTimestampMonotonic --value 2>/dev/null || true)"
                [[ "$entered" =~ ^[0-9]+$ ]] || { ok=0; break; }
                continue
            fi
            pid="$($SYSTEMCTL_BIN show "$unit" -p MainPID --value 2>/dev/null || true)"
            restarts="$($SYSTEMCTL_BIN show "$unit" -p NRestarts --value 2>/dev/null || true)"
            [[ "$pid" =~ ^[0-9]+$ ]] && [[ "$restarts" =~ ^[0-9]+$ ]] || { ok=0; break; }
            case "$unit" in
                genus-telegram-bot.service)
                    [ "$pid" -gt 0 ] && as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin \
                        "$SYSTEM_PYTHON_BIN" -I -P - "$pid" "$CORE_POINTER/bin/python" <<'PY' >/dev/null 2>&1 || { ok=0; break; }
import os, pathlib, sys
command=pathlib.Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes().split(b"\0")
if os.fsencode(sys.argv[2]) not in command: raise SystemExit("recovered bot invocation differs")
PY
                    ;;
                genus-learner.service)
                    [ "$pid" -gt 0 ] && as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin \
                        "$SYSTEM_PYTHON_BIN" -I -P - "$pid" "$REPO_DIR/deploy/pi_learn.sh" <<'PY' >/dev/null 2>&1 || { ok=0; break; }
import os, pathlib, sys
command=pathlib.Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes().split(b"\0")
if os.fsencode(sys.argv[2]) not in command: raise SystemExit("recovered learner invocation differs")
PY
                    ;;
            esac
        done
        if [ "$ok" -eq 1 ]; then
            consecutive=$((consecutive + 1))
            [ "$consecutive" -ge 3 ] && return 0
        else
            consecutive=0
        fi
        sleep 1
    done
    return 70
}

restore_selector_from_journal() {
    local prior previous current
    validate_activation_journal 1
    prior="$(journal_field prior_active_manifest)"
    previous="$(journal_field prior_previous_manifest)"
    current="$(selector_manifest)"
    if [ -z "$prior" ] && [ -z "$current" ]; then
        prepare_legacy_pointer_unit
        current="$(selector_manifest)"
        [[ "$current" = legacy-* ]] \
            || fail "Recovery konnte die direkte Legacy-Venv nicht manifestieren" 70
    fi
    if [ -z "$prior" ] && [[ "$current" = legacy-* ]]; then
        verify_target "$current" >/dev/null
        rebind_activation_journal legacy-ready "$current"
        prior="$current"
        previous="$current"
    fi
    if [ -n "$prior" ]; then
        verify_target "$prior" >/dev/null
        if [ "$current" != "$prior" ]; then atomic_link "sets/$prior" "$ACTIVE_LINK"; fi
        if [ -n "$previous" ]; then
            verify_target "$previous" >/dev/null
            atomic_link "sets/$previous" "$PREVIOUS_LINK"
        else
            rm -f -- "$PREVIOUS_LINK"; fsync_dir "$STATE_ROOT"
        fi
        rebind_activation_journal guarded "$prior"
        verify_target "$prior" >/dev/null
        [ "$(selector_manifest)" = "$prior" ] \
            && [ "$(selector_manifest "$PREVIOUS_LINK")" = "$previous" ] \
            || return 70
        if [ -n "$previous" ]; then verify_target "$previous" >/dev/null; fi
    else
        [ -z "$current" ] || return 70
        [ -d "$CORE_POINTER" ] && [ ! -L "$CORE_POINTER" ] \
            && [ -d "$EMBED_POINTER" ] && [ ! -L "$EMBED_POINTER" ] \
            || return 70
    fi
}

force_pending_transition_fail_closed() (
    local result=0 attempt_status
    set +e
    (
        set -Eeuo pipefail
        install_systemd_autostart_guard
        systemd_autostart_guard_present
    )
    attempt_status=$?
    [ "$attempt_status" -eq 0 ] || result=70
    (
        set -Eeuo pipefail
        remove_autostart_approval
    )
    attempt_status=$?
    [ "$attempt_status" -eq 0 ] || result=70
    if [ -e "$AUTOSTART_APPROVAL" ] || [ -L "$AUTOSTART_APPROVAL" ]; then result=70; fi
    (
        set -Eeuo pipefail
        disable_genus_cron_block
    )
    attempt_status=$?
    [ "$attempt_status" -eq 0 ] || result=70
    GENUS_DB_PATH="$DB_PATH" "$CORE_POINTER/bin/genus" pause \
        --reason "A0.3c transition verification/finalization failed" >/dev/null 2>&1 || result=70
    (
        set -Eeuo pipefail
        stop_all_genus_units
    )
    attempt_status=$?
    [ "$attempt_status" -eq 0 ] || result=70
    (
        set -Eeuo pipefail
        prove_no_old_runtime_processes
    )
    attempt_status=$?
    [ "$attempt_status" -eq 0 ] || result=70
    (
        set -Eeuo pipefail
        prove_no_db_handles
    )
    attempt_status=$?
    [ "$attempt_status" -eq 0 ] || result=70
    if [ "$result" -ne 0 ]; then
        printf '[A0.3c] FEHLER: fail-closed Sicherung war nicht vollstaendig attestierbar\n' >&2
    fi
    return "$result"
)

finalize_guarded_transition() {
    systemd_autostart_guard_present
    validate_autostart_approval
    restore_genus_cron_block
    verify_live_crontab "$ACTIVATION_CRON_SNAPSHOT"
    systemd_autostart_guard_present
    validate_autostart_approval
    consume_operator_reauthorization
    clear_activation_state
}

recover_pending_activation() {
    local phase receipt receipt_hash actual_hash services_output recovery_status fail_closed_status approval_status
    local -a recovery_services=()
    if [ ! -e "$ACTIVATION_JOURNAL" ]; then
        if [ -e "$ACTIVE_LINK" ] || [ -L "$ACTIVE_LINK" ] || [ -e "$AUTOSTART_APPROVAL" ] || [ -L "$AUTOSTART_APPROVAL" ]; then
            systemd_autostart_guard_present
            set +e
            ( set -Eeuo pipefail; validate_autostart_approval )
            approval_status=$?
            set -e
            if [ "$approval_status" -ne 0 ]; then
                [ -e "$OPERATOR_REAUTH_TOKEN" ] && [ ! -L "$OPERATOR_REAUTH_TOKEN" ] \
                    || fail "stale Boot-Approval ist nicht fuer einen Operator-Transition autorisiert" 70
                validate_operator_reauthorization
            fi
        fi
        if [ -e "$ACTIVATION_CRON_SNAPSHOT" ] || [ -e "$ACTIVATION_CRON_DISABLED" ]; then
            if [ -f "$ACTIVATION_CRON_SNAPSHOT" ] && verify_live_crontab "$ACTIVATION_CRON_SNAPSHOT"; then
                rm -f -- "$ACTIVATION_CRON_SNAPSHOT" "$ACTIVATION_CRON_DISABLED"; fsync_dir "$STATE_ROOT"
            else
                fail "verwaiste Activation-Artefakte koennen nicht sicher bereinigt werden" 70
            fi
        fi
        return 0
    fi
    set +e
    (
        set -Eeuo pipefail
        recover_incomplete_migration
        validate_activation_journal 1
        phase="$(journal_field phase)"
        if [ "$phase" = receipt-written ]; then
            validate_activation_journal
            validate_autostart_approval
            receipt="$(journal_field activation_receipt_path)"
            receipt_hash="$(journal_field activation_receipt_sha256)"
            [ -f "$receipt" ] && [ ! -L "$receipt" ] && [ "$(stat -c %h "$receipt")" -eq 1 ] \
                || fail "persistierter Activation-Receipt ist nicht regulaer" 70
            actual_hash="$(sha256_file "$receipt")"
            [ "$actual_hash" = "$receipt_hash" ] \
                || fail "persistierter Activation-Receipt driftet" 70
            validate_completion_receipt "$receipt"
            services_output="$(journal_service_lines)"
            [ -n "$services_output" ] \
                || fail "persistiertes Service-Inventar ist leer/ungueltig" 70
            mapfile -t recovery_services <<< "$services_output"
            attest_recovered_services
            finalize_guarded_transition
            log "vollstaendig attestierte Activation nach Unterbrechung finalisiert"
            exit 0
        fi
        [ ! -e "$OPERATOR_REAUTH_TOKEN" ] \
            || fail "unterbrochener reautorisierter Transition bleibt absichtlich fail-closed; keine alte Runtime unter neuem Repo starten" 70
        install_systemd_autostart_guard
        remove_autostart_approval
        disable_genus_cron_block
        services_output="$(journal_service_lines)"
        [ -n "$services_output" ] \
            || fail "persistiertes Service-Inventar ist leer/ungueltig" 70
        mapfile -t recovery_services <<< "$services_output"
        GENUS_DB_PATH="$DB_PATH" "$CORE_POINTER/bin/genus" pause \
            --reason "A0.3c interrupted activation recovery"
        stop_all_genus_units
        prove_no_old_runtime_processes
        prove_no_db_handles
        restore_selector_from_journal
        write_autostart_approval
        start_recorded_services
        attest_recovered_services
        GENUS_DB_PATH="$DB_PATH" "$CORE_POINTER/bin/genus" resume
        receipt="$(write_transition_completion_receipt interrupted-restored)"
        validate_completion_receipt "$receipt"
        update_activation_journal receipt-written "$receipt"
        finalize_guarded_transition
        log "unterbrochenen Runtimewechsel auf den verifizierten Ausgangszustand restauriert"
    )
    recovery_status=$?
    set -e
    if [ "$recovery_status" -eq 0 ]; then
        return 0
    fi
    set +e
    force_pending_transition_fail_closed
    fail_closed_status=$?
    set -e
    [ "$fail_closed_status" -eq 0 ] \
        || printf '[A0.3c] FEHLER: fail-closed Recovery ist unvollstaendig\n' >&2
    fail "Activation-Recovery/Finalisierung gescheitert; Journal und Snapshots bleiben pending" \
        "$recovery_status"
}

activation_fault_point() {
    local phase="$1" configured="${GENUS_A03C_TEST_FAULT_PHASE:-}" kind="${GENUS_A03C_TEST_FAULT_KIND:-}"
    [ "$configured" = "$phase" ] || return 0
    [ "${GENUS_A03C_TEST_MODE:-0}" = 1 ] || fail "Fault-Injection ist ausserhalb des Testmodus verboten" 70
    case "$kind" in
        explicit-fail) fail "injected explicit failure at $phase" 97 ;;
        set-e) false ;;
        INT) kill -INT "$$" ;;
        TERM) kill -TERM "$$" ;;
        KILL) kill -KILL "$$" ;;
        *) fail "unbekannte Fault-Injection" 70 ;;
    esac
}

switch_with_quiescence() {
    local expected="$1" target_manifest="$2" mode="$3" readiness="${4:-}" readiness_receipt=""
    local current_target="" previous_selector="" backup_receipt="" postflight_receipt=""
    local active_identity_receipt="" activation_receipt="" restore_status
    local -a recovery_services=()
    assert_expected_commit "$expected"
    init_user_roots
    acquire_operator_lock
    [ -f "$DB_PATH" ] || fail "Produkt-DB fehlt" 65
    require_command "$FUSER_BIN"
    recover_pending_activation
    if [ -e "$OPERATOR_REAUTH_TOKEN" ]; then
        [ "$mode" = activate ] \
            || fail "Operator-Reauthorization erlaubt nur stage gefolgt von activate, niemals rollback" 70
        [ "$target_manifest" = "$(selector_manifest "$STAGED_LINK")" ] \
            || fail "reautorisierte Activation muss exakt das staged NEW-Commit-Set verwenden" 70
        [[ "$target_manifest" != legacy-* ]] \
            || fail "Reauthorization darf kein Legacy-Set aktivieren" 70
    fi
    recover_incomplete_migration
    verify_target "$target_manifest" >/dev/null
    if [ "$mode" = activate ]; then
        readiness_receipt="$(verify_readiness_manifest "$target_manifest" "$expected" "$readiness")"
    fi
    remember_services
    assert_not_previously_paused
    capture_activation_crontab
    install_systemd_autostart_guard
    systemd_autostart_guard_present
    create_activation_journal "$expected" "$target_manifest" "$mode" "$readiness"
    cleanup_switch() {
        local status="${1:-$?}"
        trap - EXIT INT TERM
        set +e
        recover_pending_activation
        restore_status=$?
        if [ "$status" -ne 0 ]; then exit "$status"; fi
        exit "$restore_status"
    }
    # EXIT also catches fail() and set -e. Persistent cron/systemd guards and the
    # fsynced journal make KILL/power-loss recovery safe on the next invocation.
    trap 'cleanup_switch $?' EXIT
    trap 'cleanup_switch 130' INT
    trap 'cleanup_switch 143' TERM
    disable_genus_cron_block
    remove_autostart_approval
    update_activation_journal guarded
    if [ "$mode" = activate ]; then
        prove_no_backup_in_progress
        backup_receipt="$(fresh_backup_receipt)"
    fi
    GENUS_DB_PATH="$DB_PATH" "$CORE_POINTER/bin/genus" pause --reason "A0.3c runtime switch"
    update_activation_journal paused
    stop_services
    update_activation_journal stopped
    activation_fault_point after-stop
    prove_no_old_runtime_processes
    prove_no_db_handles
    prepare_legacy_pointer_unit
    current_target="$(readlink "$ACTIVE_LINK")"
    previous_selector="${current_target##*/}"
    rebind_activation_journal legacy-ready "$previous_selector"
    validate_activation_journal
    atomic_link "$current_target" "$PREVIOUS_LINK"
    atomic_link "sets/$target_manifest" "$ACTIVE_LINK"
    rebind_activation_journal swapped "$target_manifest"
    activation_fault_point after-swap
    verify_target "$target_manifest" >/dev/null
    if [[ "$target_manifest" != legacy-* ]]; then
        active_identity_receipt="$(attest_active_pointer_unit "$target_manifest")"
    fi
    GENUS_DB_PATH="$DB_PATH" "$CORE_POINTER/bin/genus" paused >/dev/null
    update_activation_journal target-verified
    write_autostart_approval
    validate_autostart_approval
    start_previous_services
    GENUS_DB_PATH="$DB_PATH" "$CORE_POINTER/bin/genus" resume
    update_activation_journal resumed
    activation_fault_point after-resume
    if [ "$mode" = activate ]; then
        postflight_receipt="$(attest_restarted_services)"
        update_activation_journal postflight
        activation_receipt="$(write_activation_receipt "$target_manifest" "$expected" "$readiness" "$readiness_receipt" \
            "$previous_selector" "$backup_receipt" "$postflight_receipt" "$active_identity_receipt")"
        validate_completion_receipt "$activation_receipt"
        update_activation_journal receipt-written "$activation_receipt"
    else
        recovery_services=("${active_services[@]}")
        attest_recovered_services
        activation_receipt="$(write_transition_completion_receipt rollback-restored)"
        validate_completion_receipt "$activation_receipt"
        update_activation_journal receipt-written "$activation_receipt"
    fi
    finalize_guarded_transition
    SERVICES_RESTARTED=0
    trap - EXIT INT TERM
    log "$mode abgeschlossen: $target_manifest"
}

rollback_runtime() {
    local expected="$1" target
    assert_expected_commit "$expected"
    init_user_roots
    acquire_operator_lock
    require_command "$FUSER_BIN"
    recover_pending_activation
    target="$(selector_manifest "$PREVIOUS_LINK")"
    [ -n "$target" ] || fail "kein vorheriges Runtime-Set" 65
    [[ "$target" =~ ^legacy-[a-f0-9]{64}$ ]] \
        || fail "rollback akzeptiert nur das gebundene Legacy-Set; Roll-forward braucht activate+Readiness" 65
    switch_with_quiescence "$expected" "$target" rollback ""
}

reauthorize_runtime() {
    local old="$1" new="$2" active active_hash old_tree new_tree guard_hash diff_file diff_hash
    local path stale_copy receipt token
    [[ "$old" =~ ^[a-f0-9]{40}$ ]] && [[ "$new" =~ ^[a-f0-9]{40}$ ]] && [ "$old" != "$new" ] \
        || fail "reauthorize braucht verschiedene volle OLD/NEW SHA-1" 64
    init_user_roots
    acquire_operator_lock
    assert_expected_commit "$new"
    [ ! -e "$ACTIVATION_JOURNAL" ] && [ ! -L "$ACTIVATION_JOURNAL" ] \
        || fail "Reauthorization ist mit pending Activation verboten" 70
    [ ! -e "$OPERATOR_REAUTH_TOKEN" ] && [ ! -L "$OPERATOR_REAUTH_TOKEN" ] \
        || fail "Operator-Reauthorization ist bereits pending" 70
    systemd_autostart_guard_present
    "$GIT_BIN" -C "$REPO_DIR" merge-base --is-ancestor "$old" "$new" \
        || fail "NEW ist kein sauberer Fast-Forward von OLD" 65
    active="$(selector_manifest)"; active_hash="$(manifest_file_hash "$active")"
    validate_stale_autostart_approval "$old"
    pointer_dir_valid "$CORE_POINTER" core && pointer_dir_valid "$EMBED_POINTER" embed \
        || fail "aktive Core-/Embed-Pointer sind vor Reauthorization nicht exakt" 70
    if [ -e "$ACTIVATION_CRON_SNAPSHOT" ] || [ -e "$ACTIVATION_CRON_DISABLED" ]; then
        [ -f "$ACTIVATION_CRON_SNAPSHOT" ] && verify_live_crontab "$ACTIVATION_CRON_SNAPSHOT" \
            || fail "verwaiste Cron-Evidenz ist vor Reauthorization nicht sicher" 70
        rm -f -- "$ACTIVATION_CRON_SNAPSHOT" "$ACTIVATION_CRON_DISABLED"
        fsync_dir "$STATE_ROOT"
    fi
    diff_file="$(mktemp "$STATE_ROOT/reauthorize.diff.XXXXXX")"
    "$GIT_BIN" -C "$REPO_DIR" diff --name-only -z "$old" "$new" > "$diff_file"
    while IFS= read -r -d '' path; do
        case "$path" in
            deploy/pi_a0_3c_runtime.sh|deploy/README.md|docs/*|tests/*|experiments/*|.github/*|README*|CONTRIBUTING.md) ;;
            *) fail "Fast-Forward beruehrt live-importierbaren/nicht freigegebenen Pfad: $path" 65 ;;
        esac
    done < "$diff_file"
    diff_hash="$(sha256_file "$diff_file")"; rm -f -- "$diff_file"
    old_tree="$("$GIT_BIN" -C "$REPO_DIR" rev-parse "$old^{tree}")"
    new_tree="$("$GIT_BIN" -C "$REPO_DIR" rev-parse "$new^{tree}")"
    guard_hash="$(sha256_file "$BOOT_GUARD_PATH")"
    stale_copy="$(receipt_target stale-start-authorization)"
    install -m 0600 "$AUTOSTART_APPROVAL" "$stale_copy"
    sync -f "$stale_copy"; fsync_dir "$RECEIPT_ROOT"
    [ "$(sha256_file "$stale_copy")" = "$(sha256_file "$AUTOSTART_APPROVAL")" ] \
        || fail "stale Approval-Copy driftete" 70
    receipt="$(receipt_target operator-reauthorization)"
    OLD="$old" NEW="$new" OLD_TREE="$old_tree" NEW_TREE="$new_tree" ACTIVE="$active" ACTIVE_HASH="$active_hash" \
    STALE_PATH="$stale_copy" STALE_HASH="$(sha256_file "$stale_copy")" GUARD_PATH="$BOOT_GUARD_PATH" \
    GUARD_HASH="$guard_hash" DIFF_HASH="$diff_hash" \
        "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$receipt" <<'PY'
import json,os,pathlib,sys
data={"schema":"genus-a0.3c-operator-reauthorization-v1","old_commit":os.environ["OLD"],"new_commit":os.environ["NEW"],
      "old_tree":os.environ["OLD_TREE"],"new_tree":os.environ["NEW_TREE"],"active_manifest":os.environ["ACTIVE"],
      "active_manifest_sha256":os.environ["ACTIVE_HASH"],"stale_approval_path":os.environ["STALE_PATH"],
      "stale_approval_sha256":os.environ["STALE_HASH"],"guard_path":os.environ["GUARD_PATH"],"guard_sha256":os.environ["GUARD_HASH"],
      "allowed_diff_sha256":os.environ["DIFF_HASH"],"intended_command":"stage-and-activate","boot_approval_updated":False,
      "paths_logged":True,"payloads_logged":False}
path=pathlib.Path(sys.argv[1]); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    token="$OPERATOR_REAUTH_TOKEN"
    RECEIPT="$receipt" RECEIPT_HASH="$(sha256_file "$receipt")" OLD="$old" NEW="$new" \
    ACTIVE="$active" ACTIVE_HASH="$active_hash" GUARD_HASH="$guard_hash" \
        "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P - "$token" <<'PY'
import json,os,pathlib,sys
data={"schema":"genus-a0.3c-operator-reauthorization-token-v1","receipt_path":os.environ["RECEIPT"],
      "receipt_sha256":os.environ["RECEIPT_HASH"],"old_commit":os.environ["OLD"],"new_commit":os.environ["NEW"],
      "active_manifest":os.environ["ACTIVE"],"active_manifest_sha256":os.environ["ACTIVE_HASH"],
      "guard_sha256":os.environ["GUARD_HASH"],"intended_command":"stage-and-activate"}
path=pathlib.Path(sys.argv[1]); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try: os.write(fd,(json.dumps(data,sort_keys=True,separators=(",", ":"))+"\n").encode()); os.fsync(fd)
finally: os.close(fd)
directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
try: os.fsync(directory)
finally: os.close(directory)
PY
    validate_operator_reauthorization
    log "cleanen Fast-Forward fuer genau stage+activate reautorisiert; Boot-Approval bleibt absichtlich stale"
    printf '%s\n' "$receipt"
}

status_command() {
    local format="${1:-}" active="" previous="" staged=""
    active="$(readlink "$ACTIVE_LINK" 2>/dev/null || true)"
    previous="$(readlink "$PREVIOUS_LINK" 2>/dev/null || true)"
    staged="$(readlink "$STAGED_LINK" 2>/dev/null || true)"
    if [ "$format" = --json ]; then
        printf '{"active":"%s","previous":"%s","runtime_present":%s,"staged":"%s"}\n' \
            "${active##*/}" "${previous##*/}" "$([ -x "$RUNTIME_PREFIX/bin/python3.13" ] && echo true || echo false)" "${staged##*/}"
    elif [ -z "$format" ]; then
        printf 'runtime=%s\nactive=%s\nprevious=%s\nstaged=%s\n' \
            "$([ -x "$RUNTIME_PREFIX/bin/python3.13" ] && echo present || echo absent)" \
            "${active##*/}" "${previous##*/}" "${staged##*/}"
    else
        fail "unbekannte status-Option" 64
    fi
}

main() {
    local command="${1:-}" expected manifest
    case "$command" in
        status) shift; [ "$#" -le 1 ] || fail "zu viele Argumente" 64; status_command "${1:-}" ;;
        stage) [ "$#" -le 2 ] || fail "stage akzeptiert hoechstens EXPECTED_SUPPLY_SEAL" 64; stage_set "${2:-}" ;;
        verify) shift; [ "$#" -le 1 ] || fail "zu viele Argumente" 64; init_user_roots; manifest="$(resolve_manifest "${1:-active}")"; verify_target "$manifest" ;;
        activate)
            [ "$#" -ge 3 ] && [ "$#" -le 4 ] || fail "activate braucht EXPECTED_COMMIT READINESS_MANIFEST [SET_MANIFEST]" 64
            expected="$2"; manifest="$(resolve_manifest "${4:-staged}")"
            switch_with_quiescence "$expected" "$manifest" activate "$3"
            ;;
        rollback) [ "$#" -eq 2 ] || fail "rollback braucht EXPECTED_COMMIT" 64; rollback_runtime "$2" ;;
        reauthorize) [ "$#" -eq 3 ] || fail "reauthorize braucht EXPECTED_OLD_COMMIT EXPECTED_NEW_COMMIT" 64; reauthorize_runtime "$2" "$3" ;;
        -h|--help|help) usage ;;
        *) usage >&2; fail "unbekannter Befehl" 64 ;;
    esac
}

if [ "${GENUS_A03C_SOURCE_ONLY:-0}" != 1 ]; then
    main "$@"
fi
