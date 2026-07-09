#!/usr/bin/env bash
# Lädt Qwen2.5-Coder-7B-Instruct (Q4_K_M, ~4,4 GiB, offizielles Qwen-GGUF-Repo) nach
# ~/.genus/models/ -- der Kandidat für den SCHMIED-Slot (Ronny 2026-07-09: "wird nicht
# rennen, aber vielleicht laufen; GENUS kann nachts nebenbei coden"). Wiederaufnehmbar
# (curl -C -), Idle-Priorität (der laufende Kern hat Vorrang), prüft die exakte Größe.
# Mit --benchmark läuft danach der bestehende Schmied-Benchmark gegen das neue Modell
# (deploy/schmied_benchmark.py) -- Messen vor Verdrahten, wie beim Deuter-Bakeoff.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
MODEL_DIR="${GENUS_MODEL_DIR:-$HOME/.genus/models}"
MODEL_FILE="$MODEL_DIR/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
MODEL_URL="${GENUS_CODER7B_URL:-https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf}"
ERWARTETE_BYTES=4683073536   # per HEAD verifiziert (X-Linked-Size), 2026-07-09

mkdir -p "$MODEL_DIR"

ist_bytes() { stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0; }

if [ "$(ist_bytes)" = "$ERWARTETE_BYTES" ]; then
    echo "[CODER7B] Modell liegt bereits vollständig: $MODEL_FILE"
else
    echo "[CODER7B] lade (fortsetzbar, idle-prio) -> $MODEL_FILE"
    nice -n 19 ionice -c3 curl -L -C - --retry 5 --retry-delay 30 \
        -o "$MODEL_FILE" "$MODEL_URL"
    if [ "$(ist_bytes)" != "$ERWARTETE_BYTES" ]; then
        echo "[CODER7B] FEHLER: Größe $(ist_bytes) != erwartet $ERWARTETE_BYTES -- nicht benutzen." >&2
        exit 1
    fi
    echo "[CODER7B] Download vollständig + größen-verifiziert."
fi

if [ "${1:-}" = "--benchmark" ]; then
    echo "[CODER7B] starte Schmied-Benchmark (idle-prio) -- das dauert; Ergebnis unten."
    cd "$REPO_DIR"
    nice -n 19 ionice -c3 .venv/bin/python deploy/schmied_benchmark.py "$MODEL_FILE"
fi
