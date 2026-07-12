"""Die VERWANDTSCHAFT: Begriffe nach BEDEUTUNGS-NÄHE, als GEWICHT — Ronnys „keine Definitionen,
sondern Gewichte".

Das kristalline Netz (is_a, part_of, …) sagt WELCHE Begriffe verbunden sind — aber darin sind
alle Geschwister GLEICH nah: „Wolf" und „Goldfisch" hängen beide unter „Tier", ohne dass das
Netz sagt, welcher „Hund" näher ist. Die ``verwandt``-Kanten schließen genau diese Lücke: sie
tragen ein GEWICHT (den Cosinus zweier Bedeutungs-Vektoren des Embedders) in ihrer Herleitung
(``cos=0.71``). Geschrieben werden sie OFFLINE von deploy/verwandtschaft.py (Quelle
``model:embedder``, gedeckelt unter Gegründetem — model:* überstimmt nie Wissen).

Dieses Modul ist das reine LESE-Ende im Kern-venv: kein Modell zur Frage-Zeit, nur ein Graph-
Lesen und ein Sortieren nach Gewicht. Symmetrisch gelesen (Verwandtschaft hat keine Richtung).
Membran: importiert nur genus.* (die Lese-Grundlage wortgraph + sources), nie ein Organ.
"""
from __future__ import annotations

from genus.wortgraph import _konzept_name, _last_known_word, _prominent_concept

PREDIKAT = "verwandt"


def gewicht_aus_herleitung(derivation: str | None) -> float | None:
    """Das Cosinus-Gewicht aus der Herleitung (``"cos=0.71"``) — ``None``, wenn keins da ist.
    Toleriert weitere Herleitungs-Bestandteile (Leerzeichen-/Semikolon-getrennt)."""
    if not derivation:
        return None
    for teil in derivation.replace(";", " ").split():
        if teil.startswith("cos="):
            try:
                return float(teil[4:])
            except ValueError:
                return None
    return None


def _gewichtete_nachbarn(conn, qid: str) -> list[tuple[str, float]]:
    """Die ``verwandt``-Kanten eines Konzepts mit Gewicht, BEIDE Richtungen (symmetrisch),
    direkt aus der Projektion gelesen — der geteilte :func:`sources.relations`-Leser gibt die
    Herleitung (und damit das Gewicht) nicht her, darum hier eine eigene, enge Abfrage."""
    rows = conn.execute(
        "SELECT object AS andere, derivation FROM relation_projection "
        "  WHERE subject = ? AND predicate = ? "
        "UNION "
        "SELECT subject AS andere, derivation FROM relation_projection "
        "  WHERE object = ? AND predicate = ?",
        (qid, PREDIKAT, qid, PREDIKAT),
    ).fetchall()
    paare: list[tuple[str, float]] = []
    for r in rows:
        andere, derivation = (r["andere"], r["derivation"]) if hasattr(r, "keys") else (r[0], r[1])
        g = gewicht_aus_herleitung(derivation)
        if g is not None and andere != qid:
            paare.append((andere, g))
    return paare


def verwandte(conn, wort: str, k: int = 5) -> dict:
    """Die ``k`` nächsten verwandten Begriffe zu ``wort``, nach Gewicht (Bedeutungs-Nähe) geordnet.

    ``{found, wort, concept, verwandte: [{name, gewicht}]}`` — der nächste zuerst. ``found=False``,
    wenn GENUS das Wort nicht kennt (dann versucht der aufrufende Pfad weiter); ``found=True`` mit
    LEERER Liste, wenn das Wort bekannt ist, aber (noch) keine gewichteten Nachbarn hat (ehrlich:
    das Ähnlichkeits-Netz ist dort noch dünn, keine Erfindung)."""
    found = _last_known_word(conn, wort)
    if found is None:
        return {"found": False}
    qid = _prominent_concept(conn, found)
    if qid is None:
        return {"found": True, "wort": found, "concept": None, "verwandte": []}
    beste: dict[str, float] = {}
    for andere, g in _gewichtete_nachbarn(conn, qid):
        name = _konzept_name(conn, andere)
        if name is None or name == found:
            continue   # ein blanker Q-Knoten sagt einem Menschen nichts; sich selbst nie
        if name not in beste or g > beste[name]:
            beste[name] = g   # bei Dubletten (zwei Q-ids, gleicher Name) das stärkere Gewicht
    rang = sorted(beste.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return {"found": True, "wort": found, "concept": qid,
            "verwandte": [{"name": n, "gewicht": round(g, 3)} for n, g in rang]}
