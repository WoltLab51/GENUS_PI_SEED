"""The companion: ask GENUS about a word and it answers from its own knowledge graph.

Deterministic and model-free in this first slice -- it finds a word GENUS knows in the
question, looks up that word's prominent concept, and reports the concept's meaning (the German
gloss) and its is_a, straight from the graph. So "Was ist ein Hund?" is answered from recorded,
provenanced knowledge, not interpolation. Later slices sharpen it: the edge embedder picks
*which sense* the question means (WSD from context), and a generative voice makes the answer
fluent. Here the knowing + a clean template are enough -- and the whole thing stays glass-box.
"""
from __future__ import annotations

import re

from genus import sources

_WORD = re.compile(r"[\wäöüÄÖÜß]+", re.UNICODE)


def _prominent_concept(conn, form: str) -> str | None:
    """The concept a word most prominently expresses (the grounded Wikidata pick), if known."""
    rows = sources.relations(conn, subject=f"{form}@de", predicate="expresses")
    if not rows:
        return None
    grounded = [r["object"] for r in rows if r["source"] == "wikidata"]
    return grounded[0] if grounded else rows[0]["object"]


def answer(conn, question: str) -> dict:
    """Answer a question about a word GENUS knows; ``{found: False}`` if it knows no word in it.

    Picks the *last* known content word (in "Was ist ein X?" the asked-about word comes last),
    each tried as written and capitalised (German nouns). A real parse of the question is the
    LLM's job at the edge later; this deterministic pick handles definitional questions.
    """
    found: tuple[str, str] | None = None
    for tok in _WORD.findall(question):
        for form in (tok, tok[:1].upper() + tok[1:]):
            qid = _prominent_concept(conn, form)
            if qid:
                found = (form, qid)
                break
    if found is None:
        return {"found": False, "question": question}
    form, qid = found
    c = sources.concept_meaning(conn, qid)
    return {
        "found": True,
        "word": form,
        "concept": qid,
        "label": c["label"],
        "meaning": c["meaning"],
        "is_a": [sources.display(conn, p) for p in c["is_a"]],
        "languages": [w.rsplit("@", 1)[0] for w in c["words"] if not w.endswith("@de")][:6],
    }
