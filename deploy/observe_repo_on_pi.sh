#!/usr/bin/env bash
set -Eeuo pipefail

# Structural-material membrane for repo.commits_per_day — Pi-side, robust variant.
#
# The X1 membrane only feeds when the workstation is on and logged in, so the
# belief starves whenever you are away. This runs on the always-on Pi instead:
# it fetches the published history from the remote and counts commits in a time
# window over origin/<branch>. The subject shifts slightly — from "your local
# commit moment" to the PUBLISHED development of GENUS — which is exactly "GENUS
# observes its own development", continuously and independently of the X1.
#
# Counts only: git log is piped straight into wc -l / awk, so commit messages,
# diffs, and file names never enter the ledger. If the fetch fails (no network,
# remote down), nothing is recorded and the belief ages — absence is not quiet.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$GENUS_HOME/.genus/genus.sqlite3}"
LOG_DIR="${GENUS_LOG_DIR:-$GENUS_HOME/.genus/logs}"
WINDOW_HOURS="${GENUS_REPO_WINDOW_HOURS:-24}"
BRANCH="${GENUS_REPO_BRANCH:-main}"

mkdir -p "$LOG_DIR"

log() {
    printf '[REPO] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
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

# Update our view of the published history. A failed fetch records nothing.
if ! git -C "$REPO_DIR" fetch --quiet origin "$BRANCH" 2>/dev/null; then
    log "fetch failed — no observation recorded"
    exit 0
fi

ref="origin/${BRANCH}"

# Count only. The text of git log never leaves the membrane; we keep the count.
commits="$(git -C "$REPO_DIR" log "$ref" --since="${WINDOW_HOURS} hours ago" --oneline \
    | wc -l | tr -d '[:space:]')"

# Churn: added+deleted lines over the window. --numstat carries file names in
# column 3; awk reads only columns 1 and 2 and emits a single number, so file
# names are never transmitted. Binary files show "-" and are skipped.
lines="$(git -C "$REPO_DIR" log "$ref" --since="${WINDOW_HOURS} hours ago" --numstat --pretty=tformat: \
    | awk '{ if ($1 != "-") a += $1; if ($2 != "-") d += $2 } END { print a + d + 0 }')"

log "commits(${WINDOW_HOURS}h)=$commits lines=$lines measured_on=pi ref=$ref"
run_genus observe-repo \
    --commits-per-day "$commits" --lines-changed "$lines" \
    --measured-on pi --window-hours "$WINDOW_HOURS" >/dev/null
