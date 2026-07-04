"""Der Werkzeugbauer -- Inversion ② des Audits (docs/GENUS_AUDIT_2026_07.md), verdrahtet aus
Ronnys eigener Form-Frage vom 2026-07-03 ("woraus besteht ein Werkzeug eigentlich genau?").

Ein Werkzeug zerfällt in zwei Teile:
  DATEN (diese Datei, ``Werkzeug``-Objekt):    Name, Beschreibung, Parameter, ob es schreibt,
                                                ob sein Ergebnis wortlautfest ist, welche
                                                Vertrauensstufe sein Ergebnis trägt.
  CODE (bleibt zwingend Code, nur GEBUNDEN):   die Implementierung (rechnet/liest/schreibt)
                                                und optional eine Formulierung (Ergebnis -> Satz).

Der Bauer selbst ist ein DREI-Schritt-Rezept (Prüfen -> Verdrahten -> Registriert), rein aus
Kern-Schritten -- kein Modell nötig, weil das Prüfen einer Spec keine Sprachfrage ist. Er ist
damit sein eigenes erstes komponiertes Werkzeug (Ronny: "ich nehme an, der Werkzeugmacher
verwendet auch Werkzeuge?" -- ja, exakt: Prüfen und Verdrahten SIND kleine Kern-Werkzeuge,
hier nur noch nicht selbst registriert, weil irgendwo ein erstes Mal von Hand gebaut werden
muss -- derselbe Bootstrap-Boden wie RASTER_SEED/ZIEL_SEED).

Das Pflichtfeld ``wortlautfest`` hat bewusst KEINEN Default -- eine Werkzeug-Spec lässt sich
gar nicht erst bauen, ohne diese Entscheidung zu treffen. Das ist die strukturelle Antwort auf
den echten Bug, der das Ganze auslöste: die Stimme lief drei Werkzeuge lang unbemerkt am
Muster-Pfad vorbei, weil kein Feld sie zwang, "wortlautfest?" zu beantworten.

"Testen" (der dritte Schritt im Bild) ist bewusst NICHT eine Laufzeit-Pytest-Ausführung
innerhalb dieses Moduls -- das wäre eine eigene, größere Sandbox-Aufgabe (Selbst-Codieren
Stufe 2, nicht hier). Stattdessen: ein Vertrags-Test (tests/test_werkzeug.py), der über die
GESAMTE Registry läuft, wie test_membrane_purity.py es für Membranen schon tut -- dieselbe
CI-Gate-Disziplin, keine neue Maschinerie.

"Registriert" hat zwei Ebenen (Phase 3 Scheibe 2, docs/GENUS_ARCHITEKTUR.md §4): die
LAUFZEIT-Registry wird bei jedem Start aus Code neu aufgebaut (wie RULES/DETECTORS/
REACTORS -- der Code ist die Quelle, kein dynamisches Laden). Die ENTSCHEIDUNG aber, dass
ein Werkzeug mit diesem Vertrag Teil der Hülle ist, wird als ``werkzeug_registriert``-Event
protokolliert (:func:`protokolliere_registrierungen`) -- dedupliziert über den
Vertrags-Fingerabdruck, sodass ein Prozess-Start nichts spammt, aber jede ECHTE
Vertragsänderung (z.B. ein wortlautfest-Wechsel) Geschichte schreibt. Bewusst roh (keine
Projektion): die Registry kommt weiterhin aus Code; erst wenn Selbst-Codieren Stufe 1/2
GENUS selbst Werkzeuge vorschlagen lässt, wird daraus die gegatete, projizierte Quelle.
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Callable

from genus import ledger


@dataclass(frozen=True)
class Parameter:
    """Ein einzelner Parameter eines Werkzeugs -- reine Beschreibung, keine Ausführung."""
    typ: str                     # "Text" | "Zahl" (self-calibration-no-presets: kein Enum auf
                                  # Vorrat, bis eine dritte Art wirklich gebraucht wird)
    pflicht: bool = False
    standard: object = None


@dataclass(frozen=True)
class Werkzeug:
    """Die vollständige Form (Ronnys Frage): DATEN-Teil (name..pruefbar_als) + gebundener
    CODE-Teil (implementierung, formulierung, muster). ``rezept`` bleibt hier bewusst als
    Feld vorgesehen, aber ungenutzt -- der erste echte Anwendungsfall (Kurvendiskussion, eine
    Komposition aus Nullstellen+Extremstellen+Verhalten im Unendlichen) ist noch nicht gebaut;
    es jetzt schon zu befüllen wäre Merkmal auf Vorrat."""
    name: str
    beschreibung: str
    parameter: dict[str, Parameter]
    schreibt: bool
    wortlautfest: bool                          # KEIN Default -- die Entscheidung ist Pflicht
    pruefbar_als: str                           # z.B. "sympy" | "graph" | "mensch"
    implementierung: Callable[..., dict]
    formulierung: Callable[[dict], str] | None = None
    muster: tuple = field(default_factory=tuple)
    rezept: tuple | None = None                 # für komponierte Werkzeuge; heute ungenutzt


def pruefen(werkzeug: Werkzeug) -> list[str]:
    """Ist die Spec vollständig UND stimmt sie mit der echten Implementierung überein? Gibt
    eine Liste von Fehlern zurück (leer = geprüft, bereit fürs Verdrahten). Prüft niemals RUHIG
    durch -- ein unvollständiger Vertrag wird nie stillschweigend registriert."""
    fehler: list[str] = []
    if not werkzeug.name.strip():
        fehler.append("Name fehlt.")
    if not werkzeug.beschreibung.strip():
        fehler.append(f"«{werkzeug.name}»: Beschreibung fehlt.")
    if not werkzeug.pruefbar_als.strip():
        fehler.append(f"«{werkzeug.name}»: pruefbar_als fehlt -- welche Vertrauensstufe trägt das Ergebnis?")
    if not callable(werkzeug.implementierung):
        fehler.append(f"«{werkzeug.name}»: implementierung ist nicht aufrufbar.")
        return fehler   # ohne aufrufbare Implementierung ist der Signatur-Abgleich sinnlos
    echte_parameter = set(inspect.signature(werkzeug.implementierung).parameters)
    fehlend = set(werkzeug.parameter) - echte_parameter
    if fehlend:
        fehler.append(
            f"«{werkzeug.name}»: Spec verspricht Parameter {sorted(fehlend)}, die "
            f"implementierung gar nicht entgegennimmt."
        )
    if werkzeug.formulierung is not None and not callable(werkzeug.formulierung):
        fehler.append(f"«{werkzeug.name}»: formulierung ist gesetzt, aber nicht aufrufbar.")
    return fehler


REGISTRY: dict[str, Werkzeug] = {}


def verdrahten(werkzeug: Werkzeug) -> Werkzeug:
    """Prüft und registriert -- verweigert bei jedem Vertragsbruch (nie ein kaputtes Werkzeug
    scharfschalten). Re-Verdrahten desselben Namens ersetzt den alten Eintrag (idempotent für
    Entwicklung/Neuladen, kein Duplikat-Risiko wie bei Ledger-Kanten)."""
    fehler = pruefen(werkzeug)
    if fehler:
        raise ValueError("Werkzeug-Vertrag verletzt:\n" + "\n".join(fehler))
    REGISTRY[werkzeug.name] = werkzeug
    return werkzeug


def registriert(name: str) -> Werkzeug | None:
    return REGISTRY.get(name)


def alle() -> list[Werkzeug]:
    """Alle registrierten Werkzeuge, nach Name sortiert -- das, was der Planer sieht."""
    return [REGISTRY[n] for n in sorted(REGISTRY)]


def stimme_geeignet(name: str) -> bool:
    """Darf ein Ergebnis dieses Werkzeugs der Stimme angeboten werden? Die strukturelle
    Umkehrung von wortlautfest -- niemand kann das mehr vergessen, weil es aus der Pflicht-
    Entscheidung der Spec folgt, nicht aus einer zweiten, separat zu pflegenden Menge
    (genau die Lücke, die companion.py's _STIMME_GEEIGNET beim Muster-Pfad hatte)."""
    w = registriert(name)
    return w is not None and not w.wortlautfest


def _vertrags_fingerabdruck(w: Werkzeug) -> dict:
    """Der DATEN-Vertrag eines Werkzeugs, so wie er im Ledger steht -- bewusst OHNE die
    Beschreibung (Prosa darf sich ändern, ohne eine neue Entscheidung zu sein) und ohne
    den Code-Teil (der ist gebunden, nicht serialisierbar)."""
    return {
        "name": w.name,
        "parameter": {
            n: {"typ": p.typ, "pflicht": p.pflicht, "standard": p.standard}
            for n, p in sorted(w.parameter.items())
        },
        "schreibt": w.schreibt,
        "wortlautfest": w.wortlautfest,
        "pruefbar_als": w.pruefbar_als,
    }


def protokolliere_registrierungen(conn, quelle: str = "code") -> int:
    """Die Registrierungs-ENTSCHEIDUNG wird Ledger-Geschichte (Phase 3 Scheibe 2): für
    jedes registrierte Werkzeug, dessen aktueller Vertrag noch nicht als jüngstes
    ``werkzeug_registriert``-Event im Ledger steht, wird genau eines geschrieben.
    Idempotent über den Vertrags-Fingerabdruck: ein zweiter Aufruf (jeder Prozess-Start)
    schreibt nichts; eine echte Vertragsänderung (wortlautfest-Wechsel, neuer Parameter)
    schreibt ein NEUES Event -- die Historie der Hülle bleibt vollständig und ehrlich.
    ``quelle``: heute "code" (von Hand gebaut); später schreibt Selbst-Codieren hier
    seine eigene, gegatete Herkunft. Gibt die Zahl neu protokollierter Entscheidungen
    zurück."""
    neu = 0
    for w in alle():
        vertrag = _vertrags_fingerabdruck(w)
        row = conn.execute(
            "SELECT payload FROM event_log WHERE event_type = 'werkzeug_registriert' "
            "AND json_extract(payload, '$.name') = ? ORDER BY id DESC LIMIT 1",
            (w.name,),
        ).fetchone()
        if row is not None:
            alt = json.loads(row["payload"])
            if {k: alt.get(k) for k in vertrag} == vertrag:
                continue
        payload = dict(vertrag)
        payload["beschreibung"] = w.beschreibung
        payload["quelle"] = quelle
        ledger.append(conn, "werkzeug_registriert", payload)
        neu += 1
    if neu:
        conn.commit()
    return neu
