"""Der ABNAHME-VERTRAG (Ronny 2026-07-07): die dritte, bisher fehlende Sperrklinke des
Selbst-Codier-Gatters. GENUS muss keinen starken Code-Forger schlagen — sein Vorsprung ist
ein Gatter, das JEDE generierte Zelle entweder BEWEISBAR korrekt macht oder ehrlich ablehnt.
Beweisbar heißt drei unabhängige, deterministische Klinken, die ALLE greifen müssen, bevor
„bestanden": STRUKTUR (kompilierbar, exakt der Zellen-Vertrag — AST-Leitplanke/GBNF, da),
SICHERHEIT (keine Modell-/Netz-/Prozess-Tokens — Verbots-Scan, da) und — die hier gebaute
dritte — VERHALTEN.

Bis jetzt war der generierte Fähigkeits-Test ein ``pytest.skip``: „bestanden" hieß also nur
„Signatur stimmt", nicht „die Zelle tut, was sie soll" — eine Zelle, die schlicht ``return
None`` liefert, galt als merge-reif. Ein Abnahme-Vertrag schließt genau diese Blindstelle.

Ein Abnahme-Vertrag ist eine kleine Liste von Beispielfällen als DATEN: (guess-Eingabe +
ein Graph-Zustand) → erwarteter deutscher Antwortsatz ODER erwartetes ``None`` (das ehrliche
Passen). Aus ihm erzeugt der Kern DETERMINISTISCH einen echten pytest, der den geskippten
Fähigkeits-Test ersetzt. „Bestanden" verlangt dann echten Verhaltens-Beweis.

Entscheidend: der Forger schreibt den Vertrag NIE (sonst prüfte sich das Modell selbst) — er
stammt aus der Lücke und wird vom Menschen bei der Freigabe bestätigt. Damit prüft das Gatter
gegen einen forger-UNABHÄNGIGEN Erwartungssatz: modell-agnostisch per Konstruktion, gültig
für den schwachen Pi-Schmied wie für ein starkes Modell später. Das ist es, was einen
Baustein »bewährt« macht — „bewährt" ist kein Etikett, sondern etwas, das ein Baustein sich
durch seinen bestandenen Vertrag VERDIENT.
"""
from __future__ import annotations

from dataclasses import dataclass

# Woran ``werkstatt.protokolliere_pruefung`` erkennt, dass ein Test wirklich VERHALTEN prüft
# (und nicht der alte Skip-Platzhalter ist): der erzeugte Test trägt diese Marke in Zeile 2.
MARKER = "# ABNAHME-VERTRAG"


@dataclass
class Abnahmefall:
    """Ein Beispielfall: die ``guess``-Eingabe (wie der Deuter sie liefert) + ein
    Graph-Zustand (Kanten als ``(subject, predicate, object, quelle)``) → das erwartete
    Ergebnis: ein deutscher Antwortsatz, oder ``None`` für das ehrliche Passen (die Zelle
    schweigt, wenn der Graph nichts hergibt)."""
    guess: dict
    graph: tuple = ()
    frage: str = ""              # optionaler question-Text (die meisten Zellen nutzen nur guess)
    erwartet: str | None = None


@dataclass
class Abnahmevertrag:
    blatt: str
    faelle: tuple = ()


def pruefe_vertrag(vertrag: Abnahmevertrag) -> list[str]:
    """Ein Abnahme-Vertrag ist erst gültig, wenn er BEIDE Belege erzwingt: mindestens einen
    Treffer-Fall (``erwartet`` = ein Satz) UND mindestens einen Passt-nicht-Fall (``erwartet``
    = ``None``). Ohne den None-Fall bewiese man nur, dass die Zelle redet, nie dass sie
    schweigt, wenn sie nichts weiß — und das ist die halbe Zellen-Disziplin (nie Fakten
    erfinden). Gibt die Mängel zurück (leere Liste = fügbar), dieselbe Prüf-Form wie
    ``bauplan.pruefe_bauplan`` / ``werkzeug.pruefen``."""
    maengel: list[str] = []
    faelle = list(vertrag.faelle)
    if not faelle:
        return ["kein einziger Abnahmefall — ohne Fall kein Beweis"]
    if not any(f.erwartet is not None for f in faelle):
        maengel.append("kein Treffer-Fall (erwartet = ein Satz) — unbewiesen, dass die Zelle "
                       "je antwortet")
    if not any(f.erwartet is None for f in faelle):
        maengel.append("kein Passt-nicht-Fall (erwartet = None) — unbewiesen, dass die Zelle "
                       "ehrlich schweigt, wenn der Graph nichts hergibt")
    for i, f in enumerate(faelle):
        if not isinstance(f.guess, dict):
            maengel.append(f"Fall {i}: guess ist kein dict")
        if f.erwartet is not None and not isinstance(f.erwartet, str):
            maengel.append(f"Fall {i}: erwartet ist weder ein Satz (str) noch None")
        for kante in f.graph:
            if not (isinstance(kante, (tuple, list)) and len(kante) == 4
                    and all(isinstance(x, str) for x in kante)):
                maengel.append(f"Fall {i}: Kante {kante!r} ist kein "
                               f"(subject, predicate, object, quelle) aus vier Strings")
    return maengel


def _kopf(vertrag: Abnahmevertrag) -> list[str]:
    faelle = list(vertrag.faelle)
    treffer = sum(1 for f in faelle if f.erwartet is not None)
    passt_nicht = sum(1 for f in faelle if f.erwartet is None)
    name = vertrag.blatt.replace("-", "_")
    return [
        f'"""Abnahme-Tests für den Entwurf „{vertrag.blatt}“ — VERHALTEN gegen einen',
        "forger-UNABHÄNGIGEN Erwartungssatz (den Abnahme-Vertrag). Der Kern hat diesen Test",
        "deterministisch aus dem Vertrag erzeugt; er ersetzt den früher geskippten",
        'Fähigkeits-Test. Läuft nur in der Werkstatt-Probefahrt, nie im lebenden Kern."""',
        f"{MARKER}: {len(faelle)} Fälle ({treffer} Treffer, {passt_nicht} Passt-nicht)",
        "import inspect",
        "",
        "from genus import db, reactors",
        f"from zelle_{name} import zelle_{name}",
        "",
        "",
        "def _graph(kanten):",
        '    conn = db.connect(":memory:")',
        "    for subject, praedikat, objekt, quelle in kanten:",
        "        reactors.observe_relation(conn, subject, praedikat, objekt, quelle)",
        "    return conn",
        "",
        "",
        "def test_vertrag_signatur():",
        f"    parameter = list(inspect.signature(zelle_{name}).parameters)",
        '    assert parameter == ["conn", "guess", "question", "last_question",',
        '                         "last_answer", "stimme"]',
    ]


def baue_test(vertrag: Abnahmevertrag) -> str:
    """Erzeugt DETERMINISTISCH die Sandbox-Test-Datei aus dem Vertrag: pro Fall wird der
    Fixture-Graph in einer frischen In-Memory-DB aufgebaut, die Zelle gerufen und ihr
    Ergebnis gegen ``erwartet`` geprüft. Byte-stabil bei gleichem Vertrag (der Fingerabdruck
    bleibt gleich). Wirft ``ValueError`` bei einem nicht prüfbaren Vertrag — nie stilles
    Erzeugen (dieselbe Disziplin wie ``bauplan.fuege_zusammen``)."""
    maengel = pruefe_vertrag(vertrag)
    if maengel:
        raise ValueError("Abnahme-Vertrag nicht prüfbar:\n" + "\n".join(maengel))
    name = vertrag.blatt.replace("-", "_")
    zeilen = _kopf(vertrag)
    for i, f in enumerate(vertrag.faelle):
        kanten = [tuple(k) for k in f.graph]
        zeilen += [
            "",
            "",
            f"def test_abnahme_fall_{i}():",
            f"    conn = _graph({kanten!r})",
            f"    ergebnis = zelle_{name}(conn, {f.guess!r}, {f.frage!r}, None, None)",
            f"    assert ergebnis == {f.erwartet!r}",
        ]
    return "\n".join(zeilen) + "\n"


def aus_json(daten: dict) -> Abnahmevertrag:
    """Liest einen Abnahme-Vertrag aus einer JSON-Struktur (für die CLI ``--abnahme-datei``):
    ``{"blatt": ..., "faelle": [{"guess": {...}, "graph": [[s,p,o,q], ...], "frage": ...,
    "erwartet": <satz|null>}, ...]}``. Reine Übersetzung, keine Prüfung (die macht
    :func:`pruefe_vertrag`)."""
    faelle = tuple(
        Abnahmefall(
            guess=f.get("guess") or {},
            graph=tuple(tuple(k) for k in (f.get("graph") or [])),
            frage=f.get("frage") or "",
            erwartet=f.get("erwartet"),
        )
        for f in daten.get("faelle", [])
    )
    return Abnahmevertrag(blatt=daten["blatt"], faelle=faelle)
