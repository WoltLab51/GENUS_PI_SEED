"""Rechenfähigkeit -- die erste echte Aufgabenart des Abitur-Ziels (docs/GENUS_ABITUR.md).

Ronny, klar: "GENUS soll die Aufgaben einer Abiturprüfung schaffen" -- nicht nur die Wörter
kennen. Eine Fachliste (Wortschatz) beantwortet "was ist eine Ableitung?", aber nicht "bestimme
die Ableitung von f(x) = 3x² + 2x". Das ist keine Wissensfrage, sondern eine RECHNUNG -- und
Mathematik ist exakt, kein Schätzfeld für ein Sprachmodell (LLMs rechnen nachweislich
unzuverlässig: Vorzeichenfehler, falsch angewandte Regeln, überzeugend falsche Ergebnisse).

Deshalb rechnet hier `sympy`, eine echte Computer-Algebra-Bibliothek -- deterministisch, exakt,
jeder Schritt reproduzierbar. Das ist keine Ausnahme vom gläsernen Kern-Prinzip, sondern seine
konsequente Anwendung auf ein Gebiet, das GENAU SO funktioniert: eine Ableitung hat ein
einziges richtiges Ergebnis, das man nachrechnen kann, keine Quelle, der man vertrauen muss.

Rand/Kern-Aufteilung wie überall sonst in diesem Begleiter: das PARSEN einer Aufgabenstellung
("Bestimme die Ableitung von f(x) = ...") ist ein deterministisches Muster (wie relate/common/
gender_question in companion.py) -- kein Deuter nötig für diese feste Formulierung. Das RECHNEN
ist der exakte Kern (dieses Modul). Die AUSGABE folgt der gewohnten deutschen Schulnotation
(f'(x) = ...). Erste Aufgabenart: Ableitungen (die häufigste, grundlegendste Analysis-Aufgabe --
Extremstellen/Kurvendiskussion bauen später direkt darauf auf). Weitere Aufgabenarten
(Integrale, Nullstellen, Vektorrechnung, Wahrscheinlichkeit) sind benannte, nicht gebaute
nächste Schritte -- siehe die Roadmap, nicht hier vorweggenommen.
"""
from __future__ import annotations

import re

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

# deutsche Schulschreibweise: "^" für Potenzen, "3x" für "3*x" (implizite Multiplikation)
_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application, convert_xor)

# sympy's implizite Multiplikation ist zu großzügig: ein Buchstaben-Wirrwarr wie "das ist kein
# term" wird klaglos als Produkt einzelner Symbole (d*a*s*i*s*t*...) geparst -- live gefunden,
# keine Ausnahme, ein plausibel aussehendes FALSCHES Ergebnis. Deshalb: jede alphabetische
# Zeichenkette im Term muss entweder die erfragte Variable oder ein bekannter Funktions-/
# Konstantenname sein, sonst wird ehrlich abgelehnt, bevor sympy überhaupt zum Zug kommt.
_ERLAUBTE_NAMEN = {"sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs", "e", "pi"}
_WORT = re.compile(r"[A-Za-zäöüÄÖÜß]+")


def _unbekanntes_wort(term: str, variable: str) -> str | None:
    for wort in _WORT.findall(term):
        if wort != variable and wort.lower() not in _ERLAUBTE_NAMEN:
            return wort
    return None


def _zu_ausdruck(term: str, variable: str) -> sympy.Expr:
    """Parst einen geprüften Funktionsterm in deutscher Schulschreibweise zu einem
    sympy-Ausdruck. "e" ist die Eulersche Zahl (nicht die Variable) -- außer die erfragte
    Variable heißt selbst "e"."""
    var = sympy.symbols(variable)
    local = {variable: var}
    if variable != "e":
        local["e"] = sympy.E
    return parse_expr(term, transformations=_TRANSFORMATIONS, local_dict=local)


def ableitung(term: str, variable: str = "x", ordnung: int = 1) -> dict:
    """Die ``ordnung``-te Ableitung von ``term`` nach ``variable`` -- exakt, deterministisch.

    Gibt bei Erfolg ``{"ok": True, "term": ..., "variable": ..., "ordnung": ...,
    "ableitung": ...}`` zurück (Terme als vereinfachte, lesbare Strings). Bei einem nicht
    interpretierbaren Term (unbekanntes Wort ODER ein sympy-Parse-/Rechenfehler)
    ``{"ok": False, "fehler": "<Grund>"}`` -- nie ein erfundenes Ergebnis, dieselbe
    Ehrlichkeitsdisziplin wie überall sonst im Begleiter."""
    unbekannt = _unbekanntes_wort(term, variable)
    if unbekannt is not None:
        return {"ok": False, "fehler": f"«{unbekannt}» in «{term}» ist kein bekanntes Symbol."}
    try:
        ausdruck = _zu_ausdruck(term, variable)
        var = sympy.symbols(variable)
        ergebnis = sympy.simplify(sympy.diff(ausdruck, var, ordnung))
        return {
            "ok": True,
            "term": str(ausdruck),
            "variable": variable,
            "ordnung": ordnung,
            "ableitung": str(ergebnis),
        }
    except (sympy.SympifyError, TypeError, ValueError, SyntaxError) as exc:
        return {"ok": False, "fehler": f"«{term}» ist kein lesbarer Funktionsterm ({exc})."}
