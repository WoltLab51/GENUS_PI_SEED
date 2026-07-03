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
(f'(x) = ...). Aufgabenarten bisher: Ableitungen (die häufigste, grundlegendste Analysis-
Aufgabe) und Extremstellen (baut direkt auf der Ableitung auf -- kritische Punkte über f'=0,
klassifiziert über f'', ehrlich "unklar", wenn der Test selbst nichts hergibt, z.B. bei x³/x⁴
in 0). Weitere Aufgabenarten (Integrale, Kurvendiskussion als Komposition, Vektorrechnung,
Wahrscheinlichkeit) sind benannte, nicht gebaute nächste Schritte -- siehe docs/GENUS_ABITUR.md.
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
        # expand(), nicht simplify(): simplify() faktorisiert ein Polynom manchmal um
        # (z.B. 4x^3+12x^2+8x -> 4x(x^2+3x+2)) -- mathematisch gleich, aber nicht die
        # erwartete Schul-Normalform. expand() liefert live geprüft immer die ausmultiplizierte
        # Form, ohne je ein falsches Ergebnis zu produzieren.
        ergebnis = sympy.expand(sympy.diff(ausdruck, var, ordnung))
        return {
            "ok": True,
            "term": str(ausdruck),
            "variable": variable,
            "ordnung": ordnung,
            "ableitung": str(ergebnis),
        }
    except (sympy.SympifyError, TypeError, ValueError, SyntaxError) as exc:
        return {"ok": False, "fehler": f"«{term}» ist kein lesbarer Funktionsterm ({exc})."}


def extremstellen(term: str, variable: str = "x") -> dict:
    """Die Extremstellen von ``term`` -- kritische Punkte (f'=0), klassifiziert über die zweite
    Ableitung (f''>0 Minimum, f''<0 Maximum). Baut direkt auf :func:`ableitung` auf (dieselbe
    Vorprüfung, dieselbe Ehrlichkeitsdisziplin: nie geraten).

    Gibt ``{"ok": True, "term": ..., "variable": ..., "punkte": [{"x", "y", "art"}, ...]}``
    zurück (reelle Extremstellen, aufsteigend sortiert; ``punkte`` ist leer, wenn es
    nachweislich keine gibt). Ein Punkt, an dem auch f''=0 ist, bekommt ehrlich
    ``"art": "unklar (weitere Untersuchung nötig)"`` statt einer geratenen Klassifikation."""
    unbekannt = _unbekanntes_wort(term, variable)
    if unbekannt is not None:
        return {"ok": False, "fehler": f"«{unbekannt}» in «{term}» ist kein bekanntes Symbol."}
    try:
        var = sympy.symbols(variable)
        ausdruck = _zu_ausdruck(term, variable)
        f1 = sympy.diff(ausdruck, var)
        f2 = sympy.diff(ausdruck, var, 2)
        kandidaten = sympy.solve(sympy.Eq(f1, 0), var)
        punkte = []
        for x0 in kandidaten:
            if not x0.is_real:
                continue   # komplexe Nullstellen von f' sind im Schulkontext nicht gemeint
            f2_wert = sympy.simplify(f2.subs(var, x0))
            if not f2_wert.is_number:
                art = "unklar (f'' nicht auswertbar)"
            elif f2_wert > 0:
                art = "Minimum"
            elif f2_wert < 0:
                art = "Maximum"
            else:
                art = "unklar (weitere Untersuchung nötig)"
            y0 = sympy.simplify(ausdruck.subs(var, x0))
            punkte.append({"x": str(x0), "y": str(y0), "art": art})
        punkte.sort(key=lambda p: sympy.sympify(p["x"]))
        return {"ok": True, "term": str(ausdruck), "variable": variable, "punkte": punkte}
    except (sympy.SympifyError, TypeError, ValueError, SyntaxError, NotImplementedError) as exc:
        return {"ok": False, "fehler": f"«{term}» ist kein lesbarer Funktionsterm ({exc})."}


def stammfunktion(term: str, variable: str = "x") -> dict:
    """Eine Stammfunktion (unbestimmtes Integral) von ``term`` -- exakt über sympy, mit der
    Integrationskonstante "+ C" (Teil der korrekten Schulantwort; sympy liefert sie nicht von
    sich aus, da C beliebig ist)."""
    unbekannt = _unbekanntes_wort(term, variable)
    if unbekannt is not None:
        return {"ok": False, "fehler": f"«{unbekannt}» in «{term}» ist kein bekanntes Symbol."}
    try:
        ausdruck = _zu_ausdruck(term, variable)
        var = sympy.symbols(variable)
        ergebnis = sympy.expand(sympy.integrate(ausdruck, var))   # siehe ableitung(): Normalform
        return {
            "ok": True, "term": str(ausdruck), "variable": variable,
            "stammfunktion": f"{ergebnis} + C",
        }
    except (sympy.SympifyError, TypeError, ValueError, SyntaxError, NotImplementedError) as exc:
        return {"ok": False, "fehler": f"«{term}» ist kein lesbarer Funktionsterm ({exc})."}


def integral(term: str, untere_grenze: str, obere_grenze: str, variable: str = "x") -> dict:
    """Das bestimmte Integral von ``term`` über [``untere_grenze``, ``obere_grenze``] -- der
    Flächeninhalt unter dem Graphen MIT Vorzeichen (Fläche unterhalb der x-Achse zählt negativ,
    wie in der Schulrechnung üblich; der reine Betrags-Flächeninhalt bräuchte vorher die
    Nullstellen im Intervall -- eine eigene, hier noch nicht gebaute Aufgabenart, siehe
    docs/GENUS_ABITUR.md). Grenzen dürfen Zahlen oder Konstanten wie "pi" sein, keine Variablen."""
    for stueck in (term, untere_grenze, obere_grenze):
        unbekannt = _unbekanntes_wort(stueck, variable)
        if unbekannt is not None:
            return {"ok": False, "fehler": f"«{unbekannt}» in «{stueck}» ist kein bekanntes Symbol."}
    try:
        ausdruck = _zu_ausdruck(term, variable)
        var = sympy.symbols(variable)
        a = _zu_ausdruck(untere_grenze, variable)
        b = _zu_ausdruck(obere_grenze, variable)
        ergebnis = sympy.simplify(sympy.integrate(ausdruck, (var, a, b)))
        return {
            "ok": True, "term": str(ausdruck), "variable": variable,
            "untere_grenze": str(a), "obere_grenze": str(b), "integral": str(ergebnis),
        }
    except (sympy.SympifyError, TypeError, ValueError, SyntaxError, NotImplementedError) as exc:
        return {"ok": False, "fehler": f"«{term}» ist kein lesbarer Funktionsterm ({exc})."}
