"""Der WERKPLAN -- die allgemeine Daten-Fluss-Komposition geprüfter Werkzeuge (Tool-Planer
③, Ronnys Wachstums-Wende „Kreislauf statt Muster", konsequent freie Fassung 2026-07-09).

Ein Plan ist reine DATEN: eine geordnete Folge von SCHRITTEN, jeder ruft EIN registriertes
Werkzeug (:mod:`genus.werkzeug`) und benennt, WOHER jeder Eingang kommt -- aus einer Plan-
Eingabe oder aus der Ausgabe eines FRÜHEREN Schritts. Damit fließen Ergebnisse durch die Kette
(anders als der linear/mathe-geformte ``werkzeug.rezept_implementierung``, wo jeder Schritt
dieselben ``(term, variable)`` bekommt). Die Ausführung ist der EINE Kern-Mechanismus hier --
kein komponiertes Werkzeug schreibt je wieder seine eigene Schleife.

Zwei Leinen, die die Freiheit erst bezahlbar machen (Organ, kein Orakel):
  * die GRAMMATIK (:func:`pruefe_plan`): ein Schritt darf nur ein REGISTRIERTES Werkzeug nennen
    und nur RÜCKWÄRTS auf schon berechnete Schritte verweisen -> azyklisch per Konstruktion, kein
    erfundenes Werkzeug. (Der spätere GBNF-geführte Modell-Planer kann nur Gültiges bilden.)
  * die Ausführung ist rein lesend + deterministisch; jedes Werkzeug trägt sein eigenes, schon
    geprüftes Vertrauen (der PRÜFER der Antwort sitzt im Werkzeug/Graphen, nicht hier).

Refs sind bewusst reine Tupel (immutable, hashbar, serialisierbar) -- ein Plan ist damit ein
Datenwert, den ein Modell später als GBNF-Struktur erzeugen und der Kern verifizieren kann.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from genus import werkzeug


@dataclass(frozen=True)
class Schritt:
    """Ein Plan-Schritt: rufe ``werkzeug`` und lege sein Ergebnis unter ``ausgabe`` ab.
    ``eingaben`` bindet jeden Parameter an eine QUELLE (Tupel):
      ``("in", <plan-eingabe>)``            -- ein Eingang des ganzen Plans
      ``("aus", <schritt>, <feld>)``        -- ein Feld aus der Ergebnis-dict eines früheren Schritts
    """
    ausgabe: str
    werkzeug: str
    eingaben: tuple = ()          # ((parametername, quelle), ...)


@dataclass(frozen=True)
class Werkplan:
    """Ein komponiertes Werkzeug als DATEN: benannte Eingänge, eine Schrittfolge, und welcher
    Schritt-Ausgang die Antwort ist. Ganz ohne Code -- ausgeführt vom EINEN Mechanismus unten."""
    eingaben: tuple               # Namen der Plan-Eingänge
    schritte: tuple               # (Schritt, ...)
    ergebnis: str                 # welcher Schritt-Ausgang die Antwort trägt


def _aufloesen(quelle: tuple, eingaben: dict, umgebung: dict):
    """Ein Quellen-Tupel zu seinem Laufzeit-Wert -- Plan-Eingabe oder früheres Schritt-Feld."""
    art = quelle[0]
    if art == "in":
        return eingaben[quelle[1]]
    if art == "aus":
        return umgebung[quelle[1]][quelle[2]]
    raise ValueError(f"Unbekannte Quelle {quelle!r}")


def pruefe_plan(plan: Werkplan) -> list[str]:
    """Die GRAMMATIK-Prüfung: nennt jeder Schritt ein registriertes Werkzeug, und verweist jede
    Eingabe nur auf eine Plan-Eingabe oder einen SCHON gesehenen (früheren) Schritt? Rückwärts-
    only -> azyklisch. Leere Liste = wohlgeformt. (Kein Aufruf, keine DB nötig -- reine Form.)"""
    fehler: list[str] = []
    gesehen: set[str] = set()
    for s in plan.schritte:
        if werkzeug.registriert(s.werkzeug) is None:
            fehler.append(f"Schritt «{s.ausgabe}»: Werkzeug «{s.werkzeug}» ist nicht registriert.")
        for param, quelle in s.eingaben:
            if not isinstance(quelle, tuple) or not quelle:
                fehler.append(f"Schritt «{s.ausgabe}»: Eingabe «{param}» hat keine gültige Quelle.")
            elif quelle[0] == "in":
                if quelle[1] not in plan.eingaben:
                    fehler.append(f"Schritt «{s.ausgabe}»: Eingabe «{param}» verweist auf die "
                                  f"unbekannte Plan-Eingabe «{quelle[1]}».")
            elif quelle[0] == "aus":
                if quelle[1] not in gesehen:
                    fehler.append(f"Schritt «{s.ausgabe}»: Eingabe «{param}» verweist auf den "
                                  f"Schritt «{quelle[1]}», der (noch) nicht berechnet ist.")
            else:
                fehler.append(f"Schritt «{s.ausgabe}»: Eingabe «{param}» hat unbekannte "
                              f"Quellen-Art «{quelle[0]}».")
        gesehen.add(s.ausgabe)
    if plan.ergebnis not in gesehen:
        fehler.append(f"Der Ergebnis-Schritt «{plan.ergebnis}» kommt im Plan nicht vor.")
    return fehler


def fuehre_aus(conn, plan: Werkplan, **eingaben) -> dict:
    """Führt einen wohlgeformten Plan deterministisch aus und gibt die UMGEBUNG zurück
    (jeder Schritt-Ausgang unter seinem Namen; die Antwort steht unter ``plan.ergebnis``).
    Verweigert einen malformten Plan (wie ``werkzeug.verdrahten`` einen kaputten Vertrag) --
    ein von Hand gebauter Plan darf nie stillschweigend Unsinn rechnen. ``conn`` wird nur den
    Werkzeugen injiziert, die es in ihrer Signatur führen (graph-lesende); reine Werkzeuge
    (z.B. eine Schnittmengen-Prüfung) bekommen es nicht."""
    fehler = pruefe_plan(plan)
    if fehler:
        raise ValueError("Werkplan verletzt die Grammatik:\n" + "\n".join(fehler))
    umgebung: dict = {}
    for s in plan.schritte:
        kwargs = {param: _aufloesen(quelle, eingaben, umgebung) for param, quelle in s.eingaben}
        impl = werkzeug.registriert(s.werkzeug).implementierung
        if "conn" in inspect.signature(impl).parameters:
            kwargs["conn"] = conn
        umgebung[s.ausgabe] = impl(**kwargs)
    return umgebung
