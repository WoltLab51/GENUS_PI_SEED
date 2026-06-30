#!/usr/bin/env bash
set -Eeuo pipefail

# Permanent home for the edge embedder -- the local model that does WSD (disambiguate.py) and
# the sense->concept bridge (bridge_senses.py). Replaces the /tmp scratch venv: a real venv
# under ~/.genus, fastembed (ONNX, no heavyweight torch), and the model pre-downloaded so the
# first call is instant. Idempotent. The model lives only here at the edge, never in the core.

GENUS_USER="${GENUS_USER:-${SUDO_USER:-$(id -un)}}"
GENUS_HOME="${GENUS_HOME:-$(getent passwd "$GENUS_USER" | cut -d: -f6)}"
EMBED_VENV="${GENUS_EMBED_VENV:-$GENUS_HOME/.genus/embed-venv}"
MODEL="${GENUS_EMBED_MODEL:-sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2}"

if [ ! -d "$EMBED_VENV" ]; then
    echo "[EMBED] creating venv $EMBED_VENV"
    python3 -m venv "$EMBED_VENV"
fi
"$EMBED_VENV/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
echo "[EMBED] installing fastembed (ONNX)"
"$EMBED_VENV/bin/pip" install -q fastembed

echo "[EMBED] pre-downloading model: $MODEL"
GENUS_EMBED_MODEL="$MODEL" "$EMBED_VENV/bin/python" - <<'PY'
import os
from fastembed import TextEmbedding
m = os.environ["GENUS_EMBED_MODEL"]
emb = TextEmbedding(model_name=m)
list(emb.embed(["bereit"]))  # force the ONNX session + a first embed
print("[EMBED] ready:", m)
PY

echo "[EMBED] done. venv=$EMBED_VENV"
echo "[EMBED] use:  GENUS_DB_PATH=~/.genus/genus.sqlite3 $EMBED_VENV/bin/python deploy/disambiguate.py Hund \"...\""
