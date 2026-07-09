"""Meldet die ersten Werkzeuge beim Werkzeugbauer an (genus/werkzeug.py) -- der Beweis, dass
die Form wirklich trägt, nicht nur auf dem Papier (Ronnys Fragen vom 2026-07-03).

Bewusst eine eigene, kleine Datei statt die Meldung in mathematik.py selbst zu verstecken:
mathematik.py bleibt reine Rechenfähigkeit, die niemals etwas über companion.py (die
Formulierung fürs Gespräch) wissen muss -- die Abhängigkeitsrichtung bleibt sauber (ein
Kern-Werkzeug kennt seinen Konsumenten nicht). Diese Datei darf beide kennen, weil ihr
einziger Zweck das Verbinden ist -- genau wie deploy/seed_ziele.sh nur verbindet, nicht rechnet.

Die vier Mathe-Werkzeuge laufen NEBEN dem bestehenden Muster-Pfad in companion.py her
(Strangler, nicht Ersatz -- docs/GENUS_AUDIT_2026_07.md §9): die Regex-Schnellspur bleibt die
ms-schnelle Antwort für die vier festen Formulierungen, die Registry macht sie zusätzlich für
einen künftigen Planer sichtbar und beweisbar korrekt verdrahtet (wortlautfest kann hier nicht
vergessen werden, anders als beim Muster-Pfad, wo es einmal genau das passierte)."""
from __future__ import annotations

from genus import companion, mathematik, werkzeug


def registriere_mathe_werkzeuge() -> None:
    """Idempotent (verdrahten ersetzt per Name) -- mehrfacher Aufruf ist sicher."""
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="ableitung",
        beschreibung="Die Ableitung eines Funktionsterms -- exakt, nie geraten.",
        parameter={
            "term": werkzeug.Parameter("Text", pflicht=True),
            "variable": werkzeug.Parameter("Text", standard="x"),
            "ordnung": werkzeug.Parameter("Zahl", standard=1),
        },
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        liefert={"ableitung": "Text", "term": "Text", "variable": "Text", "ordnung": "Zahl"},
        implementierung=mathematik.ableitung,
        formulierung=companion.narrate_ableitung,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="extremstellen",
        beschreibung=(
            "Die Extremstellen eines Funktionsterms -- kritische Punkte über f'=0, "
            "klassifiziert über f''."
        ),
        parameter={
            "term": werkzeug.Parameter("Text", pflicht=True),
            "variable": werkzeug.Parameter("Text", standard="x"),
        },
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        liefert={"punkte": "Liste", "term": "Text", "variable": "Text"},
        implementierung=mathematik.extremstellen,
        formulierung=companion.narrate_extremstellen,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="stammfunktion",
        beschreibung="Eine Stammfunktion (unbestimmtes Integral) eines Funktionsterms.",
        parameter={
            "term": werkzeug.Parameter("Text", pflicht=True),
            "variable": werkzeug.Parameter("Text", standard="x"),
        },
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        liefert={"stammfunktion": "Text", "term": "Text", "variable": "Text"},
        implementierung=mathematik.stammfunktion,
        formulierung=companion.narrate_stammfunktion,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="integral",
        beschreibung="Das bestimmte Integral eines Funktionsterms zwischen zwei Grenzen.",
        parameter={
            "term": werkzeug.Parameter("Text", pflicht=True),
            "untere_grenze": werkzeug.Parameter("Text", pflicht=True),
            "obere_grenze": werkzeug.Parameter("Text", pflicht=True),
            "variable": werkzeug.Parameter("Text", standard="x"),
        },
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        liefert={"integral": "Text", "term": "Text", "variable": "Text", "untere_grenze": "Text", "obere_grenze": "Text"},
        implementierung=mathematik.integral,
        formulierung=companion.narrate_integral,
    ))
    # Zwei weitere Kern-Schritte -- registriert primär als REZEPT-Bausteine (bewusst noch
    # ohne eigene Muster-Schnellspur/Formulierung; die kommen, wenn sie als eigenständige
    # Aufgabenarten gebraucht werden -- Merkmal erst wenn erkannt + notwendig).
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="nullstellen",
        beschreibung="Die reellen Nullstellen eines Funktionsterms (f=0), exakt.",
        parameter={
            "term": werkzeug.Parameter("Text", pflicht=True),
            "variable": werkzeug.Parameter("Text", standard="x"),
        },
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        liefert={"nullstellen": "Liste", "term": "Text", "variable": "Text"},
        implementierung=mathematik.nullstellen,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="verhalten_unendlich",
        beschreibung="Das Grenzverhalten eines Funktionsterms für x gegen plus/minus Unendlich.",
        parameter={
            "term": werkzeug.Parameter("Text", pflicht=True),
            "variable": werkzeug.Parameter("Text", standard="x"),
        },
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        liefert={"plus_unendlich": "Text", "minus_unendlich": "Text", "term": "Text", "variable": "Text"},
        implementierung=mathematik.verhalten_unendlich,
    ))
    # DAS ERSTE ECHTE REZEPT (das rezept-Feld war seit dem Werkzeugbauer vorgesehen, aber
    # bewusst ungenutzt, bis der erste echte Anwendungsfall da ist -- das ist er): die
    # Kurvendiskussion ist eine KOMPOSITION aus drei registrierten Kern-Schritten. Die
    # Komposition ist DATEN, die Ausführung der eine generische Kern-Mechanismus
    # (werkzeug.rezept_implementierung); das Vertrauen ist das des schwächsten Schritts --
    # hier alle "kern"/sympy. pruefen() verweigert ein Rezept, das auf Unregistriertes zeigt.
    kurvendiskussion_rezept = (
        ("kern", "nullstellen"),
        ("kern", "extremstellen"),
        ("kern", "verhalten_unendlich"),
    )
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="kurvendiskussion",
        beschreibung=(
            "Die Kurvendiskussion eines Funktionsterms -- komponiert aus Nullstellen, "
            "Extremstellen und Grenzverhalten (das erste Rezept)."
        ),
        parameter={
            "term": werkzeug.Parameter("Text", pflicht=True),
            "variable": werkzeug.Parameter("Text", standard="x"),
        },
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        liefert={"schritte": "Liste", "term": "Text", "variable": "Text"},
        implementierung=werkzeug.rezept_implementierung(kurvendiskussion_rezept),
        formulierung=companion.narrate_kurvendiskussion,
        rezept=kurvendiskussion_rezept,
    ))
