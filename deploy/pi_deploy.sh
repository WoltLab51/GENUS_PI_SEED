#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="${GENUS_DEPLOY_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${GENUS_DB_PATH:-$HOME/.genus/genus.sqlite3}"
ANCHOR_DIR="${GENUS_ANCHOR_DIR:-$HOME/.genus/anchors}"
SKIP_TESTS="${GENUS_DEPLOY_SKIP_TESTS:-0}"
SKIP_ANCHOR="${GENUS_DEPLOY_SKIP_ANCHOR:-0}"

cd "$REPO_DIR"

echo "[DEPLOY] repo=$REPO_DIR branch=$BRANCH"
echo "[DEPLOY] db=$DB_PATH"

if [ -n "$(git status --porcelain)" ]; then
    echo "[DEPLOY] working tree is dirty; refusing to deploy"
    git status --short
    exit 1
fi

current_branch="$(git branch --show-current)"
if [ "$current_branch" != "$BRANCH" ]; then
    echo "[DEPLOY] expected branch $BRANCH, got $current_branch"
    exit 1
fi

git fetch origin "$BRANCH"
local_rev="$(git rev-parse HEAD)"
remote_rev="$(git rev-parse "origin/$BRANCH")"

if [ "$local_rev" != "$remote_rev" ]; then
    echo "[DEPLOY] fast-forwarding $local_rev -> $remote_rev"
    git pull --ff-only origin "$BRANCH"
else
    echo "[DEPLOY] already up to date at $local_rev"
fi

mkdir -p "$(dirname "$DB_PATH")" "$ANCHOR_DIR"

if [ ! -d ".venv" ]; then
    echo "[DEPLOY] creating .venv"
    "$PYTHON_BIN" -m venv .venv
fi

echo "[DEPLOY] installing package"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"

export GENUS_DB_PATH="$DB_PATH"

# Autonome Aktivität pausieren (Cron-Ticks, Membranen, Lerner), damit die Selbst-Checks
# unten in Ruhe laufen -- live gefunden (2026-07-04): der Replay-Idempotenz-Check verlor
# ein Rennen gegen einen 5-Minuten-Tick ("state changed after replay", ein Wettlauf, keine
# Korruption) und brach den Deploy ab. Der trap garantiert das Aufwecken, auch bei Fehlern.
echo "[DEPLOY] pausing autonomous activity for a quiet self-check"
.venv/bin/genus pause --reason "deploy self-check"
trap '.venv/bin/genus resume >/dev/null 2>&1 || true; echo "[DEPLOY] resumed autonomous activity"' EXIT

if [ "$SKIP_TESTS" != "1" ]; then
    echo "[DEPLOY] running tests (hermetic: ambient GENUS_* unset so they never touch the live ledger)"
    env -u GENUS_DB_PATH -u GENUS_CORE_ID -u GENUS_PAUSE_FILE .venv/bin/python -m pytest
else
    echo "[DEPLOY] skipping tests"
fi

echo "[DEPLOY] rebuilding projection with the deployed code"
# A projection-LOGIC change (a new derivation, a bounded window) makes the stored
# projection differ from a fresh replay. Rebuild it here, tolerating the legitimate
# "state changed" exit, so the checks below compare a consistent state. Without
# this the integrity check aborts the deploy on any projection-logic change.
.venv/bin/genus replay || true

echo "[DEPLOY] integrity before sealing"
.venv/bin/genus integrity check

if .venv/bin/genus ledger head | grep -q "head="; then
    echo "[DEPLOY] sealing already initialized"
else
    echo "[DEPLOY] opening sealing epoch"
    .venv/bin/genus ledger seal-init
fi

echo "[DEPLOY] verifying seal chain"
.venv/bin/genus ledger verify

if [ "$SKIP_ANCHOR" != "1" ]; then
    if [ -z "${GENUS_CORE_ID:-}" ]; then
        echo "[DEPLOY] GENUS_CORE_ID not set; skipping anchor export"
    else
        echo "[DEPLOY] exporting offline anchor"
        .venv/bin/genus ledger anchor create --out "$ANCHOR_DIR"
    fi
else
    echo "[DEPLOY] skipping anchor export"
fi

echo "[DEPLOY] replay check (must be idempotent after the rebuild)"
.venv/bin/genus replay

echo "[DEPLOY] final integrity check"
.venv/bin/genus integrity check

echo "[DEPLOY] doctor check"
.venv/bin/genus doctor

# Der laufende Bot (warmer Prozess) lädt Code nur beim Start: das Neustart-Flag bittet
# ihn, sich nach dem aktuellen Poll-Zyklus (~25 s) sauber zu beenden -- systemd
# (Restart=always) bringt ihn mit dem frisch deployten Code zurück. Kein sudo nötig.
touch "$(dirname "$DB_PATH")/telegram_bot.neustart"
echo "[DEPLOY] Bot-Neustart angefordert (Flag) — greift binnen eines Poll-Zyklus"

echo "[DEPLOY] done"
