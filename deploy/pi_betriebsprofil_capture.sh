#!/usr/bin/env bash
set -Eeuo pipefail

# The hourly H0.1 due check must stay cheap, private and bounded even if the
# command below ever regresses.  A normal --quiet no-op produces no syslog
# entry at all.
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_BIN="${GENUS_BIN:-$REPO_DIR/.venv/bin/genus}"
PROFILE_DIR="${GENUS_PROFILE_DIR:-}"
MAX_LOG_BYTES=4096
OUTPUT_FILE="$(mktemp)"

cleanup() {
    rm -f -- "$OUTPUT_FILE"
}
trap cleanup EXIT

if [ -z "$PROFILE_DIR" ] || [ ! -d "$PROFILE_DIR" ] || [ -L "$PROFILE_DIR" ]; then
    printf '%s\n' '[profile-dir] missing or unsafe private profile directory' > "$OUTPUT_FILE"
    /usr/bin/logger --tag genus-betriebsprofil --priority user.err \
        -- "$(/usr/bin/head -c "$MAX_LOG_BYTES" "$OUTPUT_FILE")" || true
    exit 66
fi

# Keep draining stdout/stderr after the first 4096 bytes.  Stopping the reader
# at the limit would send SIGPIPE to GENUS and replace its real exit status.
set +e
/usr/bin/timeout --signal=TERM --kill-after=5s 180s \
    /usr/bin/nice -n 10 "$GENUS_BIN" betriebsprofil capture --quiet 2>&1 \
    | { /usr/bin/head -c "$MAX_LOG_BYTES"; /usr/bin/cat >/dev/null; } \
    > "$OUTPUT_FILE"
pipeline_status=("${PIPESTATUS[@]}")
set -e
status="${pipeline_status[0]}"

# Exit 0 plus no output is the expected hourly no-op before baseline, between
# due points and after h72.  Do not create a noisy heartbeat for that case.
if [ "$status" -eq 0 ] && [ ! -s "$OUTPUT_FILE" ]; then
    exit 0
fi

if [ "$status" -eq 0 ]; then
    prefix='[capture] '
    priority='user.notice'
else
    prefix="[exit=$status] "
    priority='user.err'
fi

# Prefix and command output together never exceed 4096 bytes per invocation.
payload_bytes=$((MAX_LOG_BYTES - ${#prefix}))
{
    printf '%s' "$prefix"
    if [ -s "$OUTPUT_FILE" ]; then
        /usr/bin/head -c "$payload_bytes" "$OUTPUT_FILE"
    else
        printf '%s' 'no output'
    fi
} | /usr/bin/logger --tag genus-betriebsprofil --priority "$priority" || true

# Logging is best effort.  The wrapper's public status is always the status of
# GENUS (or timeout's 124/137), never an incidental syslog transport failure.
exit "$status"
