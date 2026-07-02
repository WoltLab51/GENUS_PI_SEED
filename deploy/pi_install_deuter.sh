#!/usr/bin/env bash
set -Eeuo pipefail

# Permanent home for the Deuter -- the local model genus.companion.respond_with_deuter falls
# back to as a LAST resort, when the deterministic pipeline finds nothing at all. Unlike the
# embedder (its own venv, reloaded per word in the batch learner), this model must stay WARM
# inside the same long-lived process as the Telegram bot -- a reload per message would cost
# ~2-3s extra on every question. So: no new venv, llama-cpp-python goes straight into the
# existing .venv (a deploy/-only dependency; genus/ never imports it -- membrane purity is
# about WHAT genus/ imports, not where a deploy/ dependency happens to live). Idempotent.
#
# Model choice is MEASURED, not guessed: 7 models/families benchmarked on the Pi (0.5B-3.8B,
# Qwen/Llama/Gemma/Phi) -- Qwen2.5-1.5B-Instruct matched the accuracy of models 2-4x its size
# at the lowest cost of the reliable tier. See the roadmap for the full comparison.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GENUS_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
VENV="${GENUS_VENV:-$REPO_DIR/.venv}"
MODEL_DIR="${GENUS_MODEL_DIR:-$GENUS_HOME/.genus/models}"
MODEL_FILE="$MODEL_DIR/qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_URL="${GENUS_DEUTER_MODEL_URL:-https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf}"

mkdir -p "$MODEL_DIR"

echo "[DEUTER] installing llama-cpp-python into $VENV"
CMAKE_ARGS="-DGGML_NATIVE=ON" "$VENV/bin/pip" install -q llama-cpp-python

if [ -s "$MODEL_FILE" ]; then
    echo "[DEUTER] model already present: $MODEL_FILE"
else
    echo "[DEUTER] downloading model (~1.1 GB): $MODEL_URL"
    curl -sL -o "$MODEL_FILE.part" "$MODEL_URL"
    mv "$MODEL_FILE.part" "$MODEL_FILE"
fi

echo "[DEUTER] verifying: a first (cold) interpretation"
GENUS_DEUTER_MODEL="$MODEL_FILE" "$VENV/bin/python" "$SCRIPT_DIR/deuter.py" "Was ist ein Hund?"

echo "[DEUTER] done. model=$MODEL_FILE"
