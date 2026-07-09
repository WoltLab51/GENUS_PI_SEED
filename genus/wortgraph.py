"""Die LESE-GRUNDLAGE des Begleiters: die kleinen Helfer, die ein Wort/einen Knoten im
Wort-Graphen nachschlagen, benennen und deutsch formatieren. KEINE Antwort-Logik, KEIN
Dispatch -- die geteilte Schicht, auf der BEIDE oberen Schichten (auskunft = Werkzeuge,
companion = Orchestrierung) nach unten lesen, genau wie sie beide auf ``sources`` lesen.

Herausgelöst aus ``companion.py`` (2026-07-09, Modularisierung Schritt ③, „das Geteilte
wandert nach unten", Phase 0 der Ziel-Architektur). Rein lesend; nur ``sources`` + ``re``,
keine Modul-Ebene-Importe aus der Gesprächsschicht -> azyklisch.
"""
import re

from genus import sources


_WORD = re.compile(r"[\wäöüÄÖÜß]+", re.UNICODE)


def _objects(conn, form: str, predicate: str) -> list[str]:
    return [r["object"] for r in sources.relations(conn, subject=f"{form}@de", predicate=predicate)]


def _prominent_concept(conn, form: str) -> str | None:
    """The concept a word most prominently expresses -- lives in ``sources`` now
    (Phase 0 der Ziel-Architektur: das Geteilte wandert nach unten); thin delegation
    kept for the internal callers."""
    return sources.prominentes_konzept(conn, form)


def _known(conn, form: str) -> bool:
    return sources.bekanntes_wort(conn, form)


def _last_known_word(conn, question: str) -> str | None:
    """The last word in ``question`` GENUS has anything recorded about (as written or
    capitalised) -- in "Was ist ein X?" the asked-about word comes last."""
    found: str | None = None
    for tok in _WORD.findall(question):
        for form in (tok, tok[:1].upper() + tok[1:]):
            if _known(conn, form):
                found = form
                break
    return found

def _join_de(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " und " + items[-1]

def _konzept_name(conn, node: str) -> str | None:
    """Der menschliche Name eines Graph-Knotens für die Vertiefung -- ``None``, wenn es
    keinen gibt (ein blanker Q-Knoten sagt einem Menschen nichts; nie kryptisch)."""
    anzeige = sources.display(conn, node)
    m = re.search(r"\(([^)]+)\)$", anzeige)
    if m:
        return m.group(1)
    if "@" in anzeige:
        return anzeige.rsplit("@", 1)[0]
    return None

_LABEL_IN = re.compile(r"^Q\d+\s*\((.*)\)$")


def _forms(tok: str):
    """The token as written and capitalised -- German nouns are stored capitalised."""
    return (tok, tok[:1].upper() + tok[1:])


def _concept_form(conn, tok: str) -> str | None:
    """The written/capitalised form of ``tok`` that GENUS knows as a concept, if any."""
    for form in _forms(tok):
        if _prominent_concept(conn, form) is not None:
            return form
    return None


def _concepts_of(conn, tok: str) -> tuple[set[str], str | None]:
    """All concepts a word expresses, and the known form -- for the object side of the question."""
    for form in _forms(tok):
        qids = {r["object"] for r in sources.relations(conn, subject=f"{form}@de", predicate=sources.EXPRESSES)}
        if qids:
            return qids, form
    return set(), None


def _label(conn, node: str) -> str:
    """A concept rendered as a plain German word (not a Q-id) for a readable path -- the
    canonical label if the graph has one, else any German word expressing it, else the node."""
    shown = sources.display(conn, node)
    m = _LABEL_IN.match(shown)
    if m:
        return m.group(1)
    if shown != node:              # display appended something in another form
        return shown
    words = sources.lexicalize(conn, node, "de")   # a bare concept id -> lexicalize it
    return words[0] if words else node


def _collapse(path: list[str]) -> list[str]:
    out: list[str] = []
    for p in path:
        if not out or out[-1] != p:
            out.append(p)
    return out
