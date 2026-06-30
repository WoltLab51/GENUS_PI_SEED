#!/usr/bin/env python3
"""Edge WSD membrane -- the companion's 'deuten' step, the first time a model touches GENUS.

Given a word and a context, pick which of the word's senses (DBnary glosses, read from the
graph) best fits -- via a LOCAL embedding model (semantic similarity, ~100 MB, CPU). The
cosine margin to the runner-up is the confidence. The model lives HERE at the edge, never in
the core (membrane purity); this is READ-ONLY -- it outputs the disambiguation. The write-path
(recording it as a low-trust `model:embedder` claim, capped + graph-verified) is the next
slice. Self-contained and capped: no graph mutation, no network, one request at a time.

Run with a Python that has fastembed, e.g.:
  GENUS_DB_PATH=~/.genus/genus.sqlite3 /path/to/embed-venv/bin/python deploy/disambiguate.py Hund "Erzwagen im Bergwerk"
"""
import os
import sqlite3
import sys

import numpy as np
from fastembed import TextEmbedding

DB = os.environ.get("GENUS_DB_PATH", os.path.expanduser("~/.genus/genus.sqlite3"))
MODEL = os.environ.get("GENUS_EMBED_MODEL",
                       "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
LANG = os.environ.get("GENUS_DISAMBIG_LANG", "de")
QP, PP = ("query: ", "passage: ") if "e5" in MODEL else ("", "")


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: disambiguate.py <word> <context>")
        return 2
    word, context = sys.argv[1], sys.argv[2]
    subj = f"{word}@{LANG}"

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)   # read-only: never mutate the ledger
    try:
        glosses = [r[0] for r in conn.execute(
            "SELECT DISTINCT object FROM relation_projection "
            "WHERE subject = ? AND predicate = 'defined_as'", (subj,))]
    finally:
        conn.close()
    if not glosses:
        print(f"[WSD] keine Sinne für {subj} im Graph")
        return 0

    emb = TextEmbedding(model_name=MODEL)
    embed = lambda ts: list(emb.embed(ts))
    cos = lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    qv = embed([QP + context])[0]
    gvs = embed([PP + g for g in glosses])
    ranked = sorted(((g, cos(qv, gv)) for g, gv in zip(glosses, gvs)), key=lambda x: -x[1])
    top = ranked[0]
    margin = top[1] - (ranked[1][1] if len(ranked) > 1 else 0.0)

    print(f"[WSD] '{word}' im Kontext: \"{context}\"")
    print(f"  → {top[0]}")
    print(f"     Ähnlichkeit {top[1]:.3f} · Abstand zum nächsten {margin:.3f}  (= Confidence)")
    for g, s in ranked[1:4]:
        print(f"     {s:.3f}  {g[:64]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
