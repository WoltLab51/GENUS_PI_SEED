"""Die DEDUKTION als allgemeines Werkzeug (Ronny 2026-07-06: „heb die Deduktion zum
allgemeinen Werkzeug heraus"). Das Modus-Ponens-Muster existierte zweimal fest verdrahtet —
genus/inference.py (transitiver Kettenschluss über is_a/part_of) und genus/recht.py (die
Subsumtion über braucht/bewirkt-Baupläne) — und ist hier zu EINEM domänenfreien Schließer
herausgehoben (Methoden-Landkarte 2026-07-05, Empfehlung 2).

Eine REGEL ist ein Bauplan im Graphen: `regel -braucht-> praemisse` (Konjunktion — ALLE nötig),
`regel -bewirkt-> folge`. Eine Prämisse kann selbst eine Regel sein (Rekursion, der
Merkmal-Baum, dieselbe Kletterei wie is_a). Drei Schluss-Richtungen:

- ``schliesse(regel, gegeben)`` — prüft EINE Regel gegen die gegebenen Fakten.
- ``leite_ab(gegeben)`` — VORWÄRTS: alle Folgen, die aus Fakten + Regeln entstehen, bis zum
  Fixpunkt (eine abgeleitete Folge kann die nächste Regel erfüllen).
- ``beweise(ziel, gegeben)`` — RÜCKWÄRTS: „beweise mir Z" — suche eine Regel, die Z bewirkt,
  und zeige, ob ihre Prämissen (rekursiv) gelten. Das ist die neue Richtung, die es in keiner
  der beiden alten Engines gab.

Gläsern wie die is_a-Inferenz: jede abgeleitete Folge trägt ihre PRÄMISSENKETTE, und das
Vertrauen ist die SCHWÄCHSTE Prämisse (min über die Quellen-Vertrauen — eine Kette ist nur so
stark wie ihr schwächstes Glied). Read-time, erzeugt nichts. Domänenfrei: die Regeln sind
DATEN; Recht (genus/recht.py) ist die erste Domäne, aber dieser Schließer kennt kein Recht.
"""
from __future__ import annotations

from genus import sources

BRAUCHT = "braucht"
BEWIRKT = "bewirkt"


def _objekte(conn, subjekt: str, praedikat: str) -> list[str]:
    return [r["object"] for r in sources.relations(conn, subject=subjekt, predicate=praedikat)]


def ist_regel(conn, knoten: str, braucht: str = BRAUCHT) -> bool:
    """Ist ``knoten`` eine Regel (hat er Prämissen)? -- ein zusammengesetztes Merkmal ist es auch."""
    return bool(_objekte(conn, knoten, braucht))


def schliesse(conn, regel: str, gegeben: dict[str, str],
              braucht: str = BRAUCHT, bewirkt: str = BEWIRKT) -> dict:
    """Prüft EINE Regel gegen ``gegeben`` (Atom → Quelle). Eine Prämisse ist erfüllt, wenn sie
    direkt gegeben ist ODER selbst eine Regel ist, deren Prämissen (rekursiv) alle gelten.
    Vertrauen = schwächste erfüllte Prämisse. Read-time."""
    praemissen: list[dict] = []
    for atom in _objekte(conn, regel, braucht):
        if ist_regel(conn, atom, braucht):                 # zusammengesetzt -> hinabsteigen
            sub = schliesse(conn, atom, gegeben, braucht, bewirkt)
            praemissen.append({"atom": atom, "erfuellt": sub["erfuellt"], "quelle": None,
                               "trust": sub["vertrauen"], "art": "abgeleitet", "unter": sub})
        elif atom in gegeben:                               # direkt gegeben, mit Quelle
            q = gegeben[atom]
            praemissen.append({"atom": atom, "erfuellt": True, "quelle": q, "art": "gegeben",
                               "trust": round(sources.source_trust(conn, q), 3)})
        else:                                               # offen
            praemissen.append({"atom": atom, "erfuellt": False, "quelle": None,
                               "trust": None, "art": "offen"})
    erfuellt = bool(praemissen) and all(p["erfuellt"] for p in praemissen)
    belegte = [p for p in praemissen if p["erfuellt"] and p["trust"] is not None]
    folge = _objekte(conn, regel, bewirkt)
    return {"regel": regel, "folge": folge[0] if folge else None, "erfuellt": erfuellt,
            "praemissen": praemissen, "offen": [p for p in praemissen if not p["erfuellt"]],
            "vertrauen": min((p["trust"] for p in belegte), default=None)}


def regeln_die_bewirken(conn, ziel: str, bewirkt: str = BEWIRKT) -> list[str]:
    return [r["subject"] for r in sources.relations(conn, predicate=bewirkt, object=ziel)]


def beweise(conn, ziel: str, gegeben: dict[str, str],
            braucht: str = BRAUCHT, bewirkt: str = BEWIRKT) -> dict | None:
    """RÜCKWÄRTS-Verkettung — „beweise mir ``ziel``": sucht die Regeln, die ``ziel`` bewirken,
    und gibt den ersten GELUNGENEN Beweis zurück (oder, wenn keiner gelingt, den besten
    Teil-Beweis mit den wenigsten offenen Prämissen — ehrlich, was noch fehlt). ``None``, wenn
    keine Regel ``ziel`` überhaupt bewirken kann (dann ist ``ziel`` kein ableitbares Ziel)."""
    versuche = [schliesse(conn, r, gegeben, braucht, bewirkt)
                for r in regeln_die_bewirken(conn, ziel, bewirkt)]
    if not versuche:
        return None
    gelungen = [v for v in versuche if v["erfuellt"]]
    bestes = gelungen[0] if gelungen else min(versuche, key=lambda v: len(v["offen"]))
    return {"beweisbar": bool(gelungen), "ziel": ziel, "ergebnis": bestes}


def leite_ab(conn, gegeben: dict[str, str], braucht: str = BRAUCHT, bewirkt: str = BEWIRKT,
             max_runden: int = 8) -> list[dict]:
    """VORWÄRTS-Verkettung — welche Folgen entstehen aus ``gegeben`` + allen Regeln? Bis zum
    Fixpunkt (eine abgeleitete Folge kann die nächste Regel erfüllen), gegen Endlosigkeit
    gedeckelt. Gibt die NEU abgeleiteten Folgen mit Regel + Vertrauen zurück."""
    bekannt = dict(gegeben)
    abgeleitet: list[dict] = []
    alle_regeln = {r["subject"] for r in sources.relations(conn, predicate=braucht)}
    for _ in range(max(1, max_runden)):
        neu = False
        for regel in sorted(alle_regeln):
            e = schliesse(conn, regel, bekannt, braucht, bewirkt)
            if e["erfuellt"] and e["folge"] and e["folge"] not in bekannt:
                bekannt[e["folge"]] = f"deduktion:{regel}"
                abgeleitet.append({"folge": e["folge"], "regel": regel, "vertrauen": e["vertrauen"]})
                neu = True
        if not neu:
            break
    return abgeleitet


def _name(conn, knoten: str) -> str:
    anzeige = sources.display(conn, knoten)
    return anzeige.split("@", 1)[0] if "@" in anzeige else anzeige


def narrate(conn, e: dict) -> str:
    """Ein gläserner Beweis: die Prämissen (erfüllt/offen mit Quelle), die Folge, und das
    Vertrauen = schwächste Prämisse. Die domänenfreie Schwester von genus why."""
    zeilen = [f"Regel: {_name(conn, e['regel'])}"
              + (f" ⇒ {_name(conn, e['folge'])}" if e["folge"] else "")]
    for p in e["praemissen"]:
        if p["erfuellt"]:
            beleg = (f"gegeben ({p['quelle']})" if p["art"] == "gegeben"
                     else "abgeleitet (Unter-Regel erfüllt)")
            zeilen.append(f"• {_name(conn, p['atom'])} — erfüllt, {beleg}")
        else:
            zeilen.append(f"• {_name(conn, p['atom'])} — NICHT erfüllt")
    if e["erfuellt"]:
        zeilen.append(f"→ bewiesen (Vertrauen = schwächste Prämisse: {e['vertrauen']}).")
    else:
        offen = ", ".join(_name(conn, p["atom"]) for p in e["offen"])
        zeilen.append(f"→ nicht bewiesen; es fehlt: {offen}.")
    return "\n".join(zeilen)
