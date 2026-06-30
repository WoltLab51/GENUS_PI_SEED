#!/usr/bin/env python3
"""Edge embedder BRIDGE membrane -- the first time a model WRITES into GENUS.

For a word, the local embedder matches each of its candidate CONCEPTS (real `expresses` Q-ids
-- never invented) to the DBnary sense gloss that best fits the concept's own description (its
German label + its is_a parents). The match is written as a CAPPED, low-trust `model:embedder`
claim `Q -defined_as-> "<gloss>"`; the weave then adjudicates -- it corroborates the
deterministic primary where they agree, contradicts where they don't, and the teacher-loop can
correct. Hallucination is structurally impossible: the model only CHOOSES among real concepts,
and source_trust caps model:* below grounded knowledge.

Model lives HERE at the edge; writes go through the genus CLI (a separate, grounded process).
GENUS_BRIDGE_DRYRUN=1 prints the matches without writing -- verify before the graph is touched.
"""
import os
import sqlite3
import subprocess
import sys

import numpy as np
from fastembed import TextEmbedding

DB = os.environ.get("GENUS_DB_PATH", os.path.expanduser("~/.genus/genus.sqlite3"))
MODEL = os.environ.get("GENUS_EMBED_MODEL",
                       "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
LANG = os.environ.get("GENUS_BRIDGE_LANG", "de")
GENUS = os.environ.get("GENUS_BIN",
                       os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "genus"))
MIN_SIM = float(os.environ.get("GENUS_BRIDGE_MIN_SIM", "0.35"))
DRYRUN = os.environ.get("GENUS_BRIDGE_DRYRUN", "0") == "1"
QP, PP = ("query: ", "passage: ") if "e5" in MODEL else ("", "")


def german_label(conn, qid):
    row = conn.execute(
        "SELECT subject FROM relation_projection WHERE predicate IN ('label', 'expresses') "
        "AND object = ? AND subject LIKE '%@' || ? LIMIT 1", (qid, LANG)).fetchone()
    return row[0].rsplit("@", 1)[0] if row else qid


def concept_desc(conn, qid):
    parents = [r[0] for r in conn.execute(
        "SELECT DISTINCT object FROM relation_projection WHERE subject = ? AND predicate = 'is_a'",
        (qid,))]
    return " · ".join([german_label(conn, qid)] + [german_label(conn, p) for p in parents])


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: bridge_senses.py <word>")
        return 2
    word = sys.argv[1]
    subj = f"{word}@{LANG}"
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)   # read-only graph access
    try:
        glosses = [r[0] for r in conn.execute(
            "SELECT DISTINCT object FROM relation_projection "
            "WHERE subject = ? AND predicate = 'defined_as'", (subj,))]
        cands = [r[0] for r in conn.execute(
            "SELECT DISTINCT object FROM relation_projection "
            "WHERE subject = ? AND predicate = 'expresses'", (subj,))]
        descs = {q: concept_desc(conn, q) for q in cands}
    finally:
        conn.close()
    if not glosses or not cands:
        print(f"[BRG] {subj}: keine Glossen/Kandidaten")
        return 0

    emb = TextEmbedding(model_name=MODEL)
    embed = lambda ts: list(emb.embed(ts))
    cos = lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    gvecs = embed([PP + g for g in glosses])

    n = 0
    for q in cands:
        qv = embed([QP + descs[q]])[0]
        best = max(range(len(glosses)), key=lambda i: cos(qv, gvecs[i]))
        sim = cos(qv, gvecs[best])
        if sim < MIN_SIM:
            continue
        gloss = glosses[best]
        if DRYRUN:
            print(f"[BRG] {q}  ⟵{sim:.2f}⟶  {gloss[:56]}")
        else:
            subprocess.run([GENUS, "relate", q, "defined_as", gloss, "--source", "model:embedder"],
                           check=False, stdout=subprocess.DEVNULL)
        n += 1
    print(f"[BRG] {word}: {n} Konzept→Sinn-Bindung(en) "
          f"({'dry-run' if DRYRUN else 'geschrieben als model:embedder'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
