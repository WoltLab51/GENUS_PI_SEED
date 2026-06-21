#!/usr/bin/env bash
set -Eeuo pipefail

# Structural-material membrane for repo.commits_per_day.
#
# This runs on the WORKSTATION (the X1), not on the Pi: "GENUS observes your
# work" means the machine where you actually commit, not the Pi's pull cadence.
# It counts commits in a time window and hands the COUNT to the Pi's core over
# SSH. Only the number and its provenance travel — never commit messages,
# diffs, or file names (git log is piped straight into wc -l).
#
# If the X1 is off, this script simply does not run: no observation is recorded
# and the belief ages. That is deliberate. "No measurement" is not "quiet" —
# absence of evidence is not evidence of absence. A real run that finds zero
# commits DOES record quiet; a missing run records nothing.

REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
WINDOW_HOURS="${GENUS_REPO_WINDOW_HOURS:-24}"
PI_HOST="${GENUS_PI_HOST:-ronny@pi.local}"
PI_REPO="${GENUS_PI_REPO_DIR:-/home/ronny/GENUS_PI_SEED}"
PI_DB="${GENUS_PI_DB_PATH:-/home/ronny/.genus/genus.sqlite3}"
MEASURED_ON="${GENUS_MEASURED_ON:-$(hostname)}"

# Count only. The text of git log never leaves this machine; we keep the line count.
commits="$(git -C "$REPO_DIR" log --since="${WINDOW_HOURS} hours ago" --oneline | wc -l | tr -d '[:space:]')"

echo "[REPO] $(date -u +%Y-%m-%dT%H:%M:%SZ) commits(${WINDOW_HOURS}h)=$commits measured_on=$MEASURED_ON"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_HOST" \
    "cd '$PI_REPO' && GENUS_DB_PATH='$PI_DB' .venv/bin/genus observe-repo \
        --commits-per-day $commits --measured-on '$MEASURED_ON' --window-hours $WINDOW_HOURS"
