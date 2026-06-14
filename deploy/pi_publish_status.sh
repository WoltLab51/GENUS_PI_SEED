#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"
STATUS_REPO_DIR="${GENUS_STATUS_REPO_DIR:-$HOME/GENUS_PI_STATUS}"
STATUS_REPO_URL="${GENUS_STATUS_REPO_URL:-git@github-genus-pi-status:WoltLab51/GENUS_PI_STATUS.git}"
PUSH="${GENUS_STATUS_PUSH:-1}"

if [ -z "${GENUS_CORE_ID:-}" ]; then
    echo "[STATUS] GENUS_CORE_ID is required"
    exit 1
fi
SAFE_CORE_ID="$(printf '%s' "$GENUS_CORE_ID" | tr -c 'A-Za-z0-9._-' '_')"

cd "$REPO_DIR"
SEED_COMMIT="$(git rev-parse HEAD)"
export GENUS_DB_PATH="$DB_PATH"
export GENUS_SEED_COMMIT="$SEED_COMMIT"

if [ ! -d "$STATUS_REPO_DIR/.git" ]; then
    echo "[STATUS] cloning $STATUS_REPO_URL -> $STATUS_REPO_DIR"
    mkdir -p "$(dirname "$STATUS_REPO_DIR")"
    git clone "$STATUS_REPO_URL" "$STATUS_REPO_DIR"
fi

mkdir -p \
    "$STATUS_REPO_DIR/anchors" \
    "$STATUS_REPO_DIR/status/$SAFE_CORE_ID"

if [ -d "$STATUS_REPO_DIR/doctor/$SAFE_CORE_ID" ]; then
    echo "[STATUS] removing legacy public doctor report"
    rm -rf "$STATUS_REPO_DIR/doctor/$SAFE_CORE_ID"
fi

echo "[STATUS] exporting anchor"
.venv/bin/genus ledger anchor create --out "$STATUS_REPO_DIR/anchors"

echo "[STATUS] exporting structured status"
.venv/bin/python "$SCRIPT_DIR/export_pi_status.py" \
    "$STATUS_REPO_DIR/status/$SAFE_CORE_ID/latest.json"

cd "$STATUS_REPO_DIR"

if [ -z "$(git config --get user.name || true)" ]; then
    git config user.name "GENUS Pi"
fi
if [ -z "$(git config --get user.email || true)" ]; then
    git config user.email "genus-pi@users.noreply.github.com"
fi

git add anchors "status/$SAFE_CORE_ID"
git add -A "doctor/$SAFE_CORE_ID" 2>/dev/null || true

if git diff --cached --quiet; then
    echo "[STATUS] no changes to commit"
else
    git commit -m "Update $GENUS_CORE_ID status"
fi

if [ "$PUSH" = "1" ]; then
    echo "[STATUS] pushing status repo"
    git push -u origin HEAD:main
else
    echo "[STATUS] push skipped (GENUS_STATUS_PUSH=$PUSH)"
fi

echo "[STATUS] done"
