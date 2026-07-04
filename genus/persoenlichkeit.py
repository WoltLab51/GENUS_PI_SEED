"""Die PERSÖNLICHKEITS-Schicht (Ronnys Design, 2026-07-04): „eine eigene Schicht, je
nachdem was GENUS grad macht änderbar, ausgerichtet auf Nutzer und Rolle."

Drei Schichten, wissenschaftlich sauber getrennt (Trait-Theorie vs. Goffmans Rollen vs.
linguistisches Register):

  WESEN     fix, lebt in Code und Gates: ehrlich, transparent, benennt Lücken, fragt um
            Erlaubnis, erfindet nie. Keine Konfiguration ändert das — das IST GENUS.
  ART       GENUS' eigener Grundton, träge: Merkmale als WISSEN im Graphen
            (``art:<nutzer>`` -merkmal-> wert, Quelle des Stellenden, volle Herkunft).
            Ronnys Start: neugierig + warm. Per Chat stellbar („sei knapper");
            Selbst-Kalibrierung aus Feedback ist der benannte spätere Schritt (gedeckelt,
            träge, nie am Wesen).
  REGISTER  situativ, pro Rolle: die antwortende Zwicky-Zelle IST der Situations-Marker.
            Werkzeug pinnt präzise-knapp (kein Witz an einem Integral), die WACHE
            (Gates, Fehler, Governance) pinnt nüchtern — STRUKTURELL, im Code, damit
            keine Einstellung je Ernstes verspielt macht. Der Morgen hebt die Wärme um
            eine Stufe.

Die eiserne Leitplanke: Persönlichkeit ist eine Eigenschaft der SPRACHE, nie des WISSENS.
Kein Merkmal ändert je einen Fakt, eine Vertrauenszahl oder einen Ehrlichkeits-Hinweis.
"""
from __future__ import annotations

from genus import sources

NUTZER = "ronny"   # Föderations-fertig: die Schicht ist von Anfang an nutzer-geschlüsselt
ART_PREFIX = "art:"

# Die Merkmal-Achsen (Zwicky, minimal — Merkmal erst wenn erkannt + notwendig), jede mit
# GEORDNETEN Werten: der Chat-Regler („sei wärmer") bewegt sich stufenweise darauf.
MERKMALE: dict[str, tuple[str, ...]] = {
    "waerme": ("nuechtern", "neutral", "warm", "herzlich"),
    "humor": ("aus", "dezent"),
    "neugier": ("aus", "ja"),
    "knappheit": ("knapp", "mittel", "ausfuehrlich"),
}

# Anzeige-Namen für den Chat (intern ASCII wie überall, im Gespräch echte Umlaute).
ANZEIGE: dict[str, str] = {
    "waerme": "Wärme", "humor": "Humor", "neugier": "Neugier", "knappheit": "Knappheit",
}
WERT_ANZEIGE: dict[str, str] = {"nuechtern": "nüchtern", "ausfuehrlich": "ausführlich"}

# GENUS' Grundton (Ronny, 2026-07-04): neugierig als der eigene Kern, warm als Temperatur.
ART_SEED: dict[str, str] = {
    "waerme": "warm",
    "humor": "aus",
    "neugier": "ja",
    "knappheit": "mittel",
}

# Rollen-Register: harte PINS leben im Code (Teil des Wesens-Schutzes, nicht stellbar);
# "morgen" hebt die Wärme relativ um eine Stufe. Alles andere ist die pure ART.
ROLLEN_PINS: dict[str, dict[str, str]] = {
    "plausch": {},
    "werkzeug": {"knappheit": "knapp", "humor": "aus", "neugier": "aus"},
    "wache": {"waerme": "nuechtern", "humor": "aus", "neugier": "aus"},
    "morgen": {},
}


def _art_knoten(nutzer: str) -> str:
    return f"{ART_PREFIX}{nutzer}"


def saet_art(conn, nutzer: str = NUTZER) -> int:
    """Sät den Grundton — NUR fehlende Merkmale (eine bestehende, ggf. per Chat gestellte
    Einstellung wird bei einem Re-Deploy nie überschrieben)."""
    from genus import reactors

    gesaet = 0
    for merkmal, wert in ART_SEED.items():
        vorhanden = sources.relations(conn, subject=_art_knoten(nutzer), predicate=merkmal)
        if not vorhanden:
            reactors.observe_relation(conn, _art_knoten(nutzer), merkmal, wert, nutzer)
            gesaet += 1
    return gesaet


def art(conn, nutzer: str = NUTZER) -> dict[str, str]:
    """Der aktuelle Grundton aus dem Graphen; ungesäte Merkmale fallen auf die Saat."""
    werte = dict(ART_SEED)
    for merkmal in MERKMALE:
        rows = sources.relations(conn, subject=_art_knoten(nutzer), predicate=merkmal)
        if rows:
            werte[merkmal] = rows[0]["object"]
    return werte


def register(conn, rolle: str = "plausch", nutzer: str = NUTZER) -> dict[str, str]:
    """Das wirksame Ausdrucks-Register: ART aus dem Graphen, überlagert von den
    Code-Pins der Rolle; „morgen" hebt die Wärme um eine Stufe."""
    werte = art(conn, nutzer)
    werte.update(ROLLEN_PINS.get(rolle, {}))
    if rolle == "morgen":
        stufen = MERKMALE["waerme"]
        i = stufen.index(werte["waerme"]) if werte["waerme"] in stufen else 1
        werte["waerme"] = stufen[min(i + 1, len(stufen) - 1)]
    return werte


def stelle(conn, merkmal: str, richtung: int, nutzer: str = NUTZER) -> dict:
    """Der Chat-Regler: bewegt ein Merkmal um EINE Stufe (±1) auf seiner geordneten
    Achse. Die alte Kante wird zurückgenommen (ehrliche Historie), die neue gesät —
    Quelle ist der Nutzer selbst (er hat es ausdrücklich gesagt, volles Vertrauen wie
    bei „Merke dir"). An der Grenze passiert ehrlich nichts."""
    from genus import reactors

    if merkmal not in MERKMALE:
        return {"gestellt": False, "grund": f"„{merkmal}“ ist kein Merkmal."}
    stufen = MERKMALE[merkmal]
    aktuell = art(conn, nutzer)[merkmal]
    i = stufen.index(aktuell) if aktuell in stufen else 0
    neu_i = i + richtung
    if not 0 <= neu_i < len(stufen):
        return {"gestellt": False, "merkmal": merkmal, "wert": aktuell,
                "grund": f"„{merkmal}“ steht schon auf „{aktuell}“ — weiter geht es nicht."}
    neu = stufen[neu_i]
    for r in sources.relations(conn, subject=_art_knoten(nutzer), predicate=merkmal):
        if r["source"] == nutzer:
            reactors.retract_relation(conn, _art_knoten(nutzer), merkmal, r["object"],
                                      source=nutzer, reason="per Chat gestellt")
    reactors.observe_relation(conn, _art_knoten(nutzer), merkmal, neu, nutzer)
    return {"gestellt": True, "merkmal": merkmal, "wert": neu}
