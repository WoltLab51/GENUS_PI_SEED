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


def bridge_word(conn, emb, word) -> int:
    """Bridge one word's candidate concepts to their best-fitting glosses (shared model)."""
    subj = f"{word}@{LANG}"
    glosses = [r[0] for r in conn.execute(
        "SELECT DISTINCT object FROM relation_projection "
        "WHERE subject = ? AND predicate = 'defined_as'", (subj,))]
    cands = [r[0] for r in conn.execute(
        "SELECT DISTINCT object FROM relation_projection "
        "WHERE subject = ? AND predicate = 'expresses'", (subj,))]
    if not glosses or not cands:
        return 0
    embed = lambda ts: list(emb.embed(ts))
    cos = lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    gvecs = embed([PP + g for g in glosses])
    n = 0
    for q in cands:
        qv = embed([QP + concept_desc(conn, q)])[0]
        best = max(range(len(glosses)), key=lambda i: cos(qv, gvecs[i]))
        sim = cos(qv, gvecs[best])
        if sim < MIN_SIM:
            continue
        if DRYRUN:
            print(f"[BRG] {word}: {q}  ⟵{sim:.2f}⟶  {glosses[best][:52]}")
        else:
            subprocess.run([GENUS, "relate", q, "defined_as", glosses[best],
                            "--source", "model:embedder"], check=False, stdout=subprocess.DEVNULL)
        n += 1
    return n


def eligible_words(conn):
    return [r[0].rsplit("@", 1)[0] for r in conn.execute(
        "SELECT DISTINCT subject FROM relation_projection "
        "WHERE predicate = 'defined_as' AND subject LIKE '%@' || ?", (LANG,))]


def main() -> int:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)   # read-only graph access
    try:
        words = sys.argv[1:] or eligible_words(conn)         # one word, or a full batch
        emb = TextEmbedding(model_name=MODEL)                # load the model ONCE
        total, touched = 0, 0
        for word in words:
            n = bridge_word(conn, emb, word)
            total += n
            touched += 1 if n else 0
    finally:
        conn.close()
    print(f"[BRG] {total} Konzept→Sinn-Bindung(en) über {touched}/{len(words)} Wort(e) "
          f"({'dry-run' if DRYRUN else 'geschrieben als model:embedder'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
