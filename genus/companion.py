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


def _objects(conn, form: str, predicate: str) -> list[str]:
    return [r["object"] for r in sources.relations(conn, subject=f"{form}@de", predicate=predicate)]


def _prominent_concept(conn, form: str) -> str | None:
    """The concept a word most prominently expresses (the grounded Wikidata pick), if known."""
    rows = sources.relations(conn, subject=f"{form}@de", predicate="expresses")
    if not rows:
        return None
    grounded = [r["object"] for r in rows if r["source"] == "wikidata"]
    return grounded[0] if grounded else rows[0]["object"]


def _known(conn, form: str) -> bool:
    return bool(_objects(conn, form, "expresses") or _objects(conn, form, "defined_as")
               or _objects(conn, form, "primary_gloss"))


def answer(conn, question: str) -> dict:
    """Answer a question about a word GENUS knows; ``{found: False}`` if it knows no word in it.

    Picks the *last* known content word (in "Was ist ein X?" the asked-about word comes last),
    each tried as written and capitalised (German nouns). A noun usually resolves to a CONCEPT
    (meaning + is_a + other languages); a verb/adjective often has no concept node but still
    carries its glosses + part of speech -- answered word-level so the companion reaches beyond
    nouns. A real parse of the question is the LLM's job at the edge later.
    """
    found: str | None = None
    for tok in _WORD.findall(question):
        for form in (tok, tok[:1].upper() + tok[1:]):
            if _known(conn, form):
                found = form
                break
    if found is None:
        return {"found": False, "question": question}

    base = {"found": True, "word": found, "languages": [],
            "pos": sorted(set(_objects(conn, found, "pos")))}
    qid = _prominent_concept(conn, found)
    if qid is not None:
        c = sources.concept_meaning(conn, qid)
        langs = list(dict.fromkeys(  # other-language forms, order-preserving dedup
            w.rsplit("@", 1)[0] for w in c["words"] if not w.endswith("@de")))
        return {**base, "concept": qid, "label": c["label"], "meaning": c["meaning"],
                "is_a": [sources.display(conn, p) for p in c["is_a"]], "languages": langs[:6]}
    # word-level (e.g. a verb): its own glosses + part of speech, no concept node yet
    meaning = _objects(conn, found, "primary_gloss") or _objects(conn, found, "defined_as")
    return {**base, "concept": None, "label": found, "meaning": meaning, "is_a": []}


_POS_DE = {"noun": "Substantiv", "verb": "Verb", "adjective": "Adjektiv", "adverb": "Adverb"}
_LABEL = re.compile(r"^Q\d+\s*\((.*)\)$")


def _join_de(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " und " + items[-1]


def narrate(a: dict) -> str:
    """A fluent, deterministic German answer composed from the verified facts -- a glass-box
    voice (no generative model, nothing invented). The structure stays queryable behind it."""
    if not a.get("found"):
        return "Dazu kennt GENUS noch kein Wort."
    pos = a.get("pos") or []
    tag = f" ({_join_de([_POS_DE.get(p, p) for p in pos])})" if pos else ""
    if a["meaning"]:
        sentence = f"Unter »{a['word']}«{tag} versteht GENUS: {a['meaning'][0].rstrip('.')}"
    else:
        sentence = f"»{a['word']}«{tag} kennt GENUS, aber eine Bedeutung ist noch nicht erschlossen"
    if a["is_a"]:
        labels = [_LABEL.sub(r"\1", x) for x in a["is_a"]]
        sentence += f"; es zählt zu {_join_de(labels)}"
    sentence += "."
    if a["languages"]:
        sentence += f" In anderen Sprachen: {', '.join(a['languages'][:4])}."
    return sentence
