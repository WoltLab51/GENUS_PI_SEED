"""Rechen-Werkzeuge (Abitur-Analysis): Ableitung, Extremstellen, Stammfunktion, bestimmtes
Integral und Kurvendiskussion -- jede als deterministisches Muster, das NUR eine erkennbare
Aufgabenstellung auffasst und exakt über :mod:`genus.mathematik` (sympy) rechnet, nie rät.

Herausgelöst aus ``companion.py`` (2026-07-09, Modularisierung Schritt ②): das Rechnen sind
Werkzeuge (das „Ausführen"), kein Dispatch -- genau die Schicht, aus der der Tool-Planer ③
später komponiert. Die ``*_frage``/``narrate_*``-Paare sind read-time und modellfrei; die
Kurvendiskussion rechnet bereits DURCH die Werkzeug-Registry (das erste komponierte Werkzeug).

companion re-exportiert die zehn öffentlichen Namen, damit ``companion.ableitung_frage`` usw.
(die Muster-Dispatch in ``_muster_antwort``, werkzeuge_seed.formulierung, die Tests)
unveraendert weiterlaeuft.
"""
import re

# Filler-Wörter zwischen Aufgaben-Verb und Kern („bestimme BITTE die Ableitung"). Bewusste
# lokale Kopie des companion-Fragments: die Rechen-Muster sind ein eigenständiger Parser -- ein
# Modul-Ebene-Import zurück nach companion (das rechnen importiert) schüfe einen Zyklus, und ein
# eigenes Fragment-Modul waere für einen Einzeiler zu viel. Bleibt mit companion._FILL in Sync.
_FILL = r"(?:(?:eigentlich|denn|jetzt|nochmal|noch|so|überhaupt|gerade|wirklich)\s+)*"

_ORDNUNGSWORT = {"erste": 1, "zweite": 2, "dritte": 3}
_MATHTERM = r"([A-Za-z0-9äöüÄÖÜß\s\^\*\+\-/,\.\(\)]+?)"
_ABLEITUNG_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne|wie\s+lautet)\s+" + _FILL + r"die\s+(?:(erste|zweite|dritte)\s+)?"
        r"ableitung\s+von\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"[.!?]?\s*$", re.I),
    re.compile(r"\bleite\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"\s+ab[.!?]?\s*$", re.I),
]


def _ableitung_frage(text: str) -> dict | None:
    """Erkennt eine feste Ableitungs-Aufgabenformulierung; ``None`` sonst. Gibt
    ``{"term", "variable", "ordnung"}`` zurück -- reine Extraktion, keine Rechnung."""
    m = _ABLEITUNG_PATTERNS[0].search(text)
    if m:
        ordnung = _ORDNUNGSWORT.get((m.group(1) or "").lower(), 1)
        return {"term": m.group(3).strip(), "variable": m.group(2), "ordnung": ordnung}
    m = _ABLEITUNG_PATTERNS[1].search(text)
    if m:
        return {"term": m.group(2).strip(), "variable": m.group(1), "ordnung": 1}
    return None


def ableitung_frage(text: str) -> dict:
    """Die Ableitungs-Aufgabe in ``text``, exakt gerechnet; ``{"berechnung_q": False}``,
    wenn keine erkennbare Aufgabenstellung vorliegt."""
    from genus import mathematik

    gefunden = _ableitung_frage(text)
    if gefunden is None:
        return {"berechnung_q": False}
    r = mathematik.ableitung(gefunden["term"], gefunden["variable"], gefunden["ordnung"])
    r["berechnung_q"] = True
    return r


def narrate_ableitung(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    strich = "'" * r["ordnung"]
    return (f"f{strich}({r['variable']}) = {r['ableitung']} "
            f"(exakt berechnet, für f({r['variable']}) = {r['term']}).")


_EXTREMSTELLEN_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne|wie\s+lautet)\s+" + _FILL + r"die\s+extremstellen\s+von\s+"
        r"f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"[.!?]?\s*$", re.I),
]


def _extremstellen_frage(text: str) -> dict | None:
    m = _EXTREMSTELLEN_PATTERNS[0].search(text)
    if m is None:
        return None
    return {"term": m.group(2).strip(), "variable": m.group(1)}


def extremstellen_frage(text: str) -> dict:
    """Die Extremstellen-Aufgabe in ``text``, exakt gerechnet; ``{"berechnung_q": False}``,
    wenn keine erkennbare Aufgabenstellung vorliegt. Baut auf :func:`mathematik.extremstellen`
    auf -- dieselbe Rand/Kern-Trennung wie :func:`ableitung_frage`."""
    from genus import mathematik

    gefunden = _extremstellen_frage(text)
    if gefunden is None:
        return {"berechnung_q": False}
    r = mathematik.extremstellen(gefunden["term"], gefunden["variable"])
    r["berechnung_q"] = True
    return r


def narrate_extremstellen(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    if not r["punkte"]:
        return f"f({r['variable']}) = {r['term']} hat keine Extremstellen (exakt berechnet)."
    zeilen = [f"{p['art']} bei {r['variable']} = {p['x']} (f({r['variable']}) = {p['y']})"
              for p in r["punkte"]]
    return (f"Extremstellen von f({r['variable']}) = {r['term']}: " + "; ".join(zeilen)
            + " (exakt berechnet).")


_BOUND = r"([A-Za-z0-9\.\-]+)"
_STAMMFUNKTION_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne|wie\s+lautet)\s+" + _FILL + r"(?:eine|die)\s+stammfunktion\s+"
        r"von\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"[.!?]?\s*$", re.I),
]
_INTEGRAL_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne)\s+" + _FILL + r"das\s+integral\s+von\s+f\(?(\w)\)?\)?\s*=\s*"
        + _MATHTERM + r"\s+(?:in\s+den\s+grenzen\s+von|zwischen)\s+" + _BOUND
        + r"\s+(?:bis|und)\s+" + _BOUND + r"[.!?]?\s*$", re.I),
]


def stammfunktion_frage(text: str) -> dict:
    """Die Stammfunktions-Aufgabe in ``text``, exakt gerechnet (inkl. "+ C"); ``{"berechnung_q":
    False}``, wenn keine erkennbare Aufgabenstellung vorliegt."""
    from genus import mathematik

    m = _STAMMFUNKTION_PATTERNS[0].search(text)
    if m is None:
        return {"berechnung_q": False}
    r = mathematik.stammfunktion(m.group(2).strip(), m.group(1))
    r["berechnung_q"] = True
    return r


def narrate_stammfunktion(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    return (f"F({r['variable']}) = {r['stammfunktion']} "
            f"(exakt berechnet, für f({r['variable']}) = {r['term']}).")


def integral_frage(text: str) -> dict:
    """Die Aufgabe eines bestimmten Integrals in ``text``, exakt gerechnet; ``{"berechnung_q":
    False}``, wenn keine erkennbare Aufgabenstellung ("...in den Grenzen von a bis b" /
    "...zwischen a und b") vorliegt."""
    from genus import mathematik

    m = _INTEGRAL_PATTERNS[0].search(text)
    if m is None:
        return {"berechnung_q": False}
    r = mathematik.integral(m.group(2).strip(), m.group(3), m.group(4), m.group(1))
    r["berechnung_q"] = True
    return r


_KURVENDISKUSSION_PATTERNS = [
    re.compile(
        r"\b(?:f(?:ü|ue)hre\s+" + _FILL + r"eine\s+)?kurvendiskussion\s+"
        r"(?:f(?:ü|ue)r|von|zu)\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM
        + r"(?:\s+durch)?[.!?]?\s*$", re.I),
]


def kurvendiskussion_frage(text: str) -> dict:
    """Die Kurvendiskussions-Aufgabe in ``text`` -- gerechnet DURCH die Werkzeug-Registry
    (das erste komponierte Werkzeug im echten Dispatch): das Rezept schlägt seine drei
    Kern-Schritte zur Laufzeit im Register nach. ``{"berechnung_q": False}``, wenn keine
    erkennbare Aufgabenstellung vorliegt."""
    from genus import werkzeug, werkzeuge_seed

    m = _KURVENDISKUSSION_PATTERNS[0].search(text)
    if m is None:
        return {"berechnung_q": False}
    werkzeuge_seed.registriere_mathe_werkzeuge()
    r = werkzeug.registriert("kurvendiskussion").implementierung(m.group(2).strip(), m.group(1))
    r["berechnung_q"] = True
    return r


def _unendlich_lesbar(wert: str) -> str:
    return {"oo": "+∞", "-oo": "−∞"}.get(wert, wert)


def narrate_kurvendiskussion(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    je_schritt = {s["schritt"]: s for s in r["schritte"]}
    v = r["variable"]
    ns = je_schritt["nullstellen"]["nullstellen"]
    ns_text = ", ".join(f"{v} = {n}" for n in ns) if ns else "keine"
    punkte = je_schritt["extremstellen"]["punkte"]
    ex_text = ("; ".join(f"{p['art']} bei {v} = {p['x']} (f({v}) = {p['y']})" for p in punkte)
               if punkte else "keine")
    vu = je_schritt["verhalten_unendlich"]
    return (f"Kurvendiskussion für f({v}) = {r['term']}:\n"
            f"• Nullstellen: {ns_text}\n"
            f"• Extremstellen: {ex_text}\n"
            f"• Verhalten im Unendlichen: f → {_unendlich_lesbar(vu['plus_unendlich'])} für "
            f"{v} → +∞, f → {_unendlich_lesbar(vu['minus_unendlich'])} für {v} → −∞\n"
            f"(exakt berechnet, als Rezept: Nullstellen → Extremstellen → Grenzverhalten)")


def narrate_integral(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    return (f"Das bestimmte Integral von f({r['variable']}) = {r['term']} in den Grenzen von "
            f"{r['untere_grenze']} bis {r['obere_grenze']} ist {r['integral']} (exakt berechnet).")
