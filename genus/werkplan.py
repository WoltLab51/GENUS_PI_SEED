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
import itertools
from dataclasses import dataclass, field

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
    """Die GRAMMATIK-Prüfung: nennt jeder Schritt ein registriertes Werkzeug, verweist jede
    Eingabe nur auf eine Plan-Eingabe oder einen SCHON gesehenen (früheren) Schritt (Rückwärts-
    only -> azyklisch), und -- seit ``Werkzeug.liefert`` (Scheibe A) -- greift jeder
    ``("aus", schritt, feld)``-Verweis ein Feld, das der Quell-Schritt auch WIRKLICH liefert,
    mit passendem Typ zum konsumierenden Parameter? Leere Liste = wohlgeformt. (Kein Aufruf,
    keine DB nötig -- reine Form; genau die Prüfung, auf der die Rückwärts-Plan-Suche und der
    spätere Verifikations-Trichter aufsetzen.)"""
    fehler: list[str] = []
    gesehen: dict[str, str] = {}   # Schritt-Ausgabe -> Werkzeug-Name (für die liefert-Prüfung)
    for s in plan.schritte:
        w = werkzeug.registriert(s.werkzeug)
        if w is None:
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
                    quell_werkzeug = werkzeug.registriert(gesehen[quelle[1]])
                    if quell_werkzeug is not None:
                        geliefert = quell_werkzeug.liefert
                        if quelle[2] not in geliefert:
                            fehler.append(
                                f"Schritt «{s.ausgabe}»: Eingabe «{param}» greift Feld "
                                f"«{quelle[2]}» aus «{quelle[1]}», aber "
                                f"«{quell_werkzeug.name}» liefert nur "
                                f"{sorted(geliefert) or '(nichts -- terminal)'}.")
                        elif (w is not None and param in w.parameter
                              and w.parameter[param].typ != geliefert[quelle[2]]):
                            fehler.append(
                                f"Schritt «{s.ausgabe}»: Eingabe «{param}» erwartet Typ "
                                f"«{w.parameter[param].typ}», aber «{quell_werkzeug.name}»."
                                f"{quelle[2]} liefert «{geliefert[quelle[2]]}».")
            else:
                fehler.append(f"Schritt «{s.ausgabe}»: Eingabe «{param}» hat unbekannte "
                              f"Quellen-Art «{quelle[0]}».")
        gesehen[s.ausgabe] = s.werkzeug
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


# --- die RÜCKWÄRTS-PLAN-SUCHE (③ Scheibe B): GENUS schließt sich seinen Plan selbst -------
#
# Die zweite Domäne der Deduktions-Idee (die erste: der Bauplan-Finder fürs Selbst-Codieren,
# genus/planer.py -- und exakt dessen KERNLEHRE gilt auch hier): der Plan wird DEDUZIERT,
# nicht vom Modell gewürfelt. Rückwärts vom Ziel-Werkzeug: jeder Parameter braucht eine
# Quelle -- eine Plan-Eingabe passenden Typs oder ein liefert-Feld eines anderen Werkzeugs
# (dessen Eingänge dann wieder geplant werden, bis alles in den Eingaben geerdet ist).
#
# Typen unterbestimmen die Semantik (zwei "Wort"-Eingänge lassen sich vertauschen; ein
# "Liste"-Bedarf griffe auch nach nullstellen.nullstellen) -- deshalb ist die Verifikation
# PFLICHT: jeder Kandidat wird gegen PLANFÄLLE (Graph + Eingaben + erwartete Ergebnis-Felder,
# das Abnahme-Vertrag-Muster) wirklich AUSGEFÜHRT; der einfachste Kandidat, der ALLE Fälle
# trägt, gewinnt; keiner -> ehrliches None (die präzise benannte Lücke). Synthese durch
# Aufzählung + Verifikation: sicher, weil der Beweis die Ground Truth ist, nicht der Vorschlag.
#
# Bewusste v1-Grenzen (Merkmal erst wenn nötig): jedes Werkzeug höchstens EINMAL je Plan
# (sein Schritt wird von allen Konsumenten geteilt; Schritt-Name = Werkzeug-Name), und die
# Suche ist durch max_werkzeuge/_MAX_KANDIDATEN gedeckelt (deterministisch, kein Zufall).

_MAX_KANDIDATEN = 2000    # Weglauf-Deckel der FUNDE je Tiefe, weit über jedem echten Plan
_MAX_ERKUNDUNG = 50_000   # ...und der ERKUNDUNG je Tiefe: tote Zweige kosten sonst unbegrenzt
                          # (ein Zweig, der nie etwas liefert, triggert den Fund-Deckel nie)


@dataclass(frozen=True)
class Planfall:
    """EIN Ground-Truth-Fall für die Plan-Suche (das Abnahmefall-Muster, auf Pläne gewandt):
    ``graph`` = die Kanten einer frischen In-Memory-Welt ((subjekt, prädikat, objekt, quelle)),
    ``eingaben`` = die Plan-Eingaben des Beispiels, ``erwartet`` = Feld->Wert, die das
    Ergebnis-dict exakt tragen muss (Teilmenge). Richtungs-empfindliche Ziele brauchen einen
    richtungs-empfindlichen Fall (sonst überlebt der vertauschte Plan die Prüfung)."""
    graph: tuple
    eingaben: dict = field(default_factory=dict)
    erwartet: dict = field(default_factory=dict)


def _quellen_fuer(typ: str, eingaben: dict, eigner: str) -> list[tuple]:
    """Alle Quellen, die ``typ`` liefern können -- Plan-Eingaben zuerst (Occam: geerdet ist
    einfacher als gerechnet), dann liefert-Felder aller Werkzeuge außer dem Eigner selbst
    (nichts konsumiert die eigene Ausgabe). Deterministisch sortiert; Zellen (liefert={})
    tauchen strukturell nie auf."""
    quellen: list[tuple] = [("in", n) for n in sorted(eingaben) if eingaben[n] == typ]
    for w in werkzeug.alle():
        if w.name == eigner:
            continue
        for feld in sorted(w.liefert):
            if w.liefert[feld] == typ:
                quellen.append(("aus", w.name, feld))
    return quellen


def _erreicht(start: str, ziel: str, kanten: dict) -> bool:
    """Hängt ``start`` (transitiv) von ``ziel`` ab? -- kleine BFS über die bisher gewählten
    Speise-Kanten, für den Zyklen-Schnitt am Entstehungspunkt."""
    stapel, gesehen = [start], set()
    while stapel:
        knoten = stapel.pop()
        if knoten == ziel:
            return True
        if knoten in gesehen:
            continue
        gesehen.add(knoten)
        stapel.extend(kanten.get(knoten, ()))
    return False


def _belegungen(ziel: str, eingaben: dict, max_werkzeuge: int):
    """Zählt alle vollständigen Belegungen auf: {werkzeug: {param: quelle}} -- rückwärts vom
    Ziel, Arbeitliste deterministisch, Werkzeug-einmal (geteilte Schritte). Generator.

    Zyklen werden am ENTSTEHUNGSPUNKT geschnitten (eine Wahl, die den Konsumenten transitiv
    zu seiner eigenen Quelle machte, wird sofort verworfen) -- nicht erst beim Topo-Sortieren:
    sonst spannt jeder Köder-Zyklus (extremstellen isst verbindung.verdict, verbindung isst
    extremstellen.punkte) einen riesigen toten Unterbaum auf, der die Aufzählung verhungern
    lässt, bevor der echte Plan drankommt (live so gefunden)."""
    budget = {"knoten": _MAX_ERKUNDUNG}
    # Die Quellen je (typ, eigner) sind während EINER Suche konstant (die Registry ändert
    # sich nicht mittendrin) -- einmal rechnen, dann nachschlagen. Ohne den Cache scannte
    # jeder Erkundungs-Knoten für jeden Parameter die ganze Registry: bei zehntausenden
    # toten Zweigen der eigentliche Zeitfresser (live so gefunden).
    quellen_cache: dict[tuple[str, str], list] = {}

    def quellen(typ: str, eigner: str) -> list:
        schluessel = (typ, eigner)
        if schluessel not in quellen_cache:
            quellen_cache[schluessel] = _quellen_fuer(typ, eingaben, eigner)
        return quellen_cache[schluessel]

    def erweitere(bindungen: dict, offen: list, kanten: dict):
        if not offen:
            yield dict(bindungen)
            return
        name, rest = offen[0], offen[1:]
        spec = werkzeug.registriert(name)
        if spec is None:
            return
        namen = list(spec.parameter)
        quellen_je = [quellen(spec.parameter[p].typ, name) for p in namen]
        if any(not q for q in quellen_je):
            return   # ein Bedarf ohne jede Quelle -> dieser Zweig ist tot
        for kombi in itertools.product(*quellen_je):
            # Erkundungs-Deckel auf die KOMBINATIONEN, nicht die Knoten: ein einzelner
            # Knoten mit vier Text-Bedarfen à ~23 Quellen spannt sonst 280.000 Kombis in
            # EINER Schleife auf, die ein Knoten-Deckel nie sieht (live so gefunden).
            if budget["knoten"] <= 0:
                return
            budget["knoten"] -= 1
            deps = {q[1] for q in kombi if q[0] == "aus"}
            if any(_erreicht(d, name, kanten) for d in deps):
                continue   # Zyklus entstünde -> sofort schneiden, kein toter Unterbaum
            neu = [t for t in dict.fromkeys(q[1] for q in kombi if q[0] == "aus")
                   if t not in bindungen and t not in rest and t != name]
            if len(bindungen) + 1 + len(rest) + len(neu) > max_werkzeuge:
                continue
            b2 = dict(bindungen)
            b2[name] = dict(zip(namen, kombi))
            k2 = dict(kanten)
            k2[name] = sorted(deps)
            yield from erweitere(b2, rest + neu, k2)

    yield from erweitere({}, [ziel], {})


def _als_plan(ziel: str, bindungen: dict, plan_eingaben: tuple) -> Werkplan | None:
    """Eine Belegung zum Werkplan: Schritte in Abhängigkeits-Reihenfolge (Kahn, deterministisch);
    ``None`` bei einem Zyklus (A speist B speist A -- die Belegung war dann kein Plan)."""
    braucht = {t: sorted({q[1] for q in b.values() if q[0] == "aus"})
               for t, b in bindungen.items()}
    reihenfolge: list[str] = []
    fertig: set[str] = set()
    while len(reihenfolge) < len(bindungen):
        frei = sorted(t for t in bindungen
                      if t not in fertig and all(d in fertig for d in braucht[t]))
        if not frei:
            return None   # Zyklus
        reihenfolge.extend(frei)
        fertig.update(frei)
    schritte = tuple(Schritt(t, t, tuple(bindungen[t].items())) for t in reihenfolge)
    return Werkplan(eingaben=plan_eingaben, schritte=schritte, ergebnis=ziel)


def _fall_welt(fall: Planfall):
    """Die In-Memory-Welt EINES Falls -- einmal gebaut, von allen Kandidaten read-only
    wiederverwendet (der Bau ist das Teure, nicht die Ausführung; live so gefunden)."""
    from genus import reactors
    from genus.db import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    for subjekt, praedikat, objekt, quelle in fall.graph:
        reactors.observe_relation(conn, subjekt, praedikat, objekt, quelle)
    return conn


def _besteht(plan: Werkplan, conn, fall: Planfall) -> bool:
    """Führt den Kandidaten in der (geteilten, read-only benutzten) Fall-Welt aus und prüft
    die erwarteten Ergebnis-Felder exakt. JEDE Ausnahme = durchgefallen (fail-safe: ein
    krachender Kandidat kann nie ein falsches „gefunden" erzeugen)."""
    try:
        ergebnis = fuehre_aus(conn, plan, **fall.eingaben)[plan.ergebnis]
        return all(ergebnis.get(k) == v for k, v in fall.erwartet.items())
    except Exception:
        return False


def finde_werkplan(ziel: str, eingaben: dict[str, str], faelle: tuple,
                   max_werkzeuge: int = 6) -> dict:
    """Schließt rückwärts einen Werkplan, der ``ziel`` aus den benannten Plan-Eingaben
    (name -> typ) berechnet UND alle ``faelle`` trägt. Gibt ``{"plan": Werkplan|None,
    "geprueft": n}`` zurück -- gläsern: der Plan selbst ist die Begründung (jeder Schritt
    sichtbar), ``geprueft`` sagt, wie viele Kandidaten die Fälle aussortiert haben.
    Mindestens EIN Fall ist Pflicht: ohne Ground Truth wäre der einfachste typ-gültige
    Kandidat ein Würfelwurf -- genau das, was dieser Planer nicht ist."""
    if not faelle:
        raise ValueError("finde_werkplan braucht mindestens einen Planfall -- "
                         "ohne Ground Truth ist ein typ-gültiger Plan nur geraten.")
    # ITERATIVE TIEFE: erst alle 1-Werkzeug-Pläne, dann 2, dann 3 ... -- Occam ist damit
    # STRUKTUR (kleinste Pläne werden vollständig geprüft, bevor ein größerer je entsteht),
    # und die kombinatorische Wildnis tiefer Ketten (Text-Echo-Werkzeuge füttern einander)
    # wird nie betreten, solange eine kleine Lösung existiert. Je Tiefe zählen nur
    # Belegungen EXAKT dieser Größe (kleinere hatten ihre Runde schon); der Deckel je
    # Tiefe hält den Kein-Plan-Fall endlich.
    welten = [(_fall_welt(fall), fall) for fall in faelle]   # einmal bauen, N-mal prüfen
    try:
        geprueft = 0
        for tiefe in range(1, max_werkzeuge + 1):
            for idx, bindungen in enumerate(_belegungen(ziel, eingaben, tiefe)):
                if idx >= _MAX_KANDIDATEN:
                    break
                if len(bindungen) != tiefe:
                    continue
                # SICHERHEIT + Fokus: die Suche PROBIERT Kandidaten wirklich aus -- ein
                # schreibendes Werkzeug darf dabei nie ausgeführt werden (v1 komponiert
                # ohnehin nur lesende Antworten). Und ein Plan, der nicht ALLE Plan-Eingaben
                # benutzt, beantwortet nicht die gestellte Frage -- billig vorab aussortiert.
                if any(werkzeug.registriert(t).schreibt for t in bindungen):
                    continue
                benutzt = {q[1] for b in bindungen.values() for q in b.values()
                           if q[0] == "in"}
                if benutzt != set(eingaben):
                    continue
                plan = _als_plan(ziel, bindungen, tuple(sorted(eingaben)))
                if plan is None or pruefe_plan(plan):
                    continue
                geprueft += 1
                if all(_besteht(plan, conn, fall) for conn, fall in welten):
                    return {"plan": plan, "geprueft": geprueft}
        return {"plan": None, "geprueft": geprueft}
    finally:
        for conn, _ in welten:
            conn.close()
