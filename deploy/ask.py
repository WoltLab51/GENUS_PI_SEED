#!/usr/bin/env python3
"""Smart companion (edge): ask GENUS and the embedder deutet *which sense* the question means.

Where `genus ask` (core, deterministic) answers with a word's prominent sense, this reads the
word's rich DBnary glosses, embeds the question against each, and picks the sense that fits the
CONTEXT (cosine; the margin to the runner-up is the confidence). If a concept is bound to that
sense (the bridge's `model:embedder` binding), it adds the concept's is_a + other languages.
The model lives HERE at the edge; the knowing stays in the core (read-only graph + genus CLI).
READ-ONLY. Run with the embedder venv, e.g.:
  GENUS_DB_PATH=~/.genus/genus.sqlite3 ~/.genus/embed-venv/bin/python deploy/ask.py "Was ist ein Hund im Bergwerk?"
"""
import os
import re
import sqlite3
import sys

import numpy as np
from fastembed import TextEmbedding

DB = os.environ.get("GENUS_DB_PATH", os.path.expanduser("~/.genus/genus.sqlite3"))
MODEL = os.environ.get("GENUS_EMBED_MODEL",
                       "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
LANG = os.environ.get("GENUS_ASK_LANG", "de")
QP, PP = ("query: ", "passage: ") if "e5" in MODEL else ("", "")
_WORD = re.compile(r"[\wäöüÄÖÜß]+", re.UNICODE)


def main() -> int:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        print("usage: ask.py <frage>")
        return 2
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        # the last known content word (one that carries glosses)
        word = None
        for tok in _WORD.findall(question):
            for form in (tok, tok[:1].upper() + tok[1:]):
                if conn.execute("SELECT 1 FROM relation_projection WHERE subject=? "
                                "AND predicate='defined_as' LIMIT 1", (f"{form}@{LANG}",)).fetchone():
                    word = form
        if word is None:
            print("[ASK] GENUS kennt kein Wort aus der Frage (noch nicht gelernt).")
            return 0
        subj = f"{word}@{LANG}"
        glosses = [r[0] for r in conn.execute(
            "SELECT DISTINCT object FROM relation_projection "
            "WHERE subject=? AND predicate='defined_as'", (subj,))]
        # concept bound to each gloss (via the bridge), to enrich the answer
        gloss_concept = {r[1]: r[0] for r in conn.execute(
            "SELECT subject, object FROM relation_projection WHERE predicate='defined_as' "
            "AND subject LIKE 'Q%'")}
    finally:
        conn.close()

    emb = TextEmbedding(model_name=MODEL)
    e = lambda ts: list(emb.embed(ts))
    cos = lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    qv = e([QP + question])[0]
    ranked = sorted(zip(glosses, e([PP + g for g in glosses])),
                    key=lambda gv: cos(qv, gv[1]), reverse=True)
    top = ranked[0][0]
    margin = cos(qv, ranked[0][1]) - (cos(qv, ranked[1][1]) if len(ranked) > 1 else 0.0)

    print(f"[ASK] „{word}" im Sinn deiner Frage:")
    print(f"  → {top}")
    qid = gloss_concept.get(top)
    if qid:
        print(f"     (Konzept {qid} — siehe `genus concept {qid}`)")
    print(f"     Confidence {margin:.2f} (Abstand zum nächsten Sinn)")
    if len(ranked) > 1:
        print(f"     andere Lesart: {ranked[1][0][:56]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
