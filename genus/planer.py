"""Der PLANER — der Bauplan-Finder als Schluss (Ronny 2026-07-07: „mach den Bauplan-Finder
als Deduktion"). Das Filetstück der bewährten-Bausteine-Idee: GENUS lässt sich einen Bauplan
nicht mehr vom schwachen Schmied SCHREIBEN, sondern SCHLIESST ihn sich selbst — deterministisch,
gläsern, KEIN LLM.

Aus einem ABNAHME-VERTRAG (den Beispielfällen: guess + Graph-Zustand → erwarteter Satz ODER
None) schließt der Planer rückwärts: welcher bewährte Baustein (bauplan.BESCHAFFUNGEN) produziert
die Slot-Werte, die im erwarteten Satz stehen? Daraus leitet er die Formulierung ab (die
Slot-Werte im Satz durch {slotname} ersetzt) und VERIFIZIERT den Kandidaten gegen ALLE Fälle.
Der erste, der alle Fälle trägt (Treffer exakt, Passt-nicht → None), ist der Bauplan.

Zwei Invarianten:
- KEIN exec im Kern. GENUS führt nie generierten Code aus (das ist die Werkstatt-Sandbox). Der
  Planer KENNT seine Bausteine und rechnet ihr Verhalten (``_simuliere`` spiegelt exakt
  ``bauplan._beschaffungs_baustein``/``fuege_zusammen``). Der Simulator ist nur ein VORSCHLAGENDER
  Schluss; der endgültige Beweis bleibt der Abnahme-Vertrag am wirklich gefügten Code im
  Sandbox-Subprozess. Ist der Simulator je zu optimistisch, fängt der Vertrag es dort ab — nie
  ein falsches „bewährt".
- Ehrliche Decke: der Planer reicht nur so weit wie die Baustein-Vokabel. Was er nicht komponieren
  kann, gibt ``None`` zurück — nicht geraten. Wächst die Vokabel (bewährte Bausteine), wächst
  seine Reichweite.
"""
from __future__ import annotations

import string

from genus import bauplan, db, reactors


def _graph(kanten):
    conn = db.connect(":memory:")
    for subject, praedikat, objekt, quelle in kanten:
        reactors.observe_relation(conn, subject, praedikat, objekt, quelle)
    return conn


def _simuliere(conn, beschaffung: dict, waechter: str, subject) -> dict | None:
    """Was der gefügte Baustein zur Laufzeit produzieren WÜRDE — Slot-Werte oder None, exakt
    gespiegelt zu ``bauplan._beschaffungs_baustein`` + der Wächter-Klausel in ``fuege_zusammen``.
    Kein exec: der Kern rechnet das Verhalten seiner bekannten Bausteine selbst."""
    if waechter == "subject" and not (isinstance(subject, str) and subject):
        return None
    art = beschaffung["art"]
    praedikat = beschaffung.get("praedikat")
    if art == "keine":
        return {"subject": subject}
    if art == "anzahl_kanten":
        if praedikat:
            row = conn.execute(
                "SELECT COUNT(*) FROM relation_projection WHERE subject = ? AND predicate = ?",
                (subject, praedikat)).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM relation_projection WHERE subject = ?",
                (subject,)).fetchone()
        anzahl = int(row[0]) if row is not None else 0
        if anzahl == 0:
            return None
        return {"subject": subject, "anzahl": anzahl}
    if art == "erstes_objekt":
        row = conn.execute(
            "SELECT object FROM relation_projection WHERE subject = ? AND predicate = ? "
            "ORDER BY object LIMIT 1", (subject, praedikat)).fetchone()
        if row is None:
            return None
        return {"subject": subject, "wert": row[0]}
    return None


def _ausgabe(conn, bauplan_dict: dict, guess) -> str | None:
    """Was die Zelle zu diesem guess/Graph ausgäbe — der Satz oder None (ehrliches Passen)."""
    subject = (guess or {}).get("subject")
    slots = _simuliere(conn, bauplan_dict["beschaffung"], bauplan_dict["waechter"], subject)
    if slots is None:
        return None
    try:
        return bauplan_dict["formulierung"].format(**slots)
    except (KeyError, IndexError, ValueError):
        return None


def _leite_formulierung_ab(slots: dict, erwartet: str) -> str | None:
    """Aus einem TREFFER-Fall die Formulierung ableiten: ersetze jeden produzierten Slot-Wert
    im erwarteten Satz durch ``{slotname}``. Längste Werte zuerst (kein Teil-Treffer), je die
    erste Fundstelle. ``None``, wenn ein Slot-Wert nicht im Satz vorkommt — dann trägt dieser
    Baustein den Satz nicht (die Voll-Verifikation fängt den Rest)."""
    template = erwartet
    for slot, wert in sorted(slots.items(), key=lambda kv: -len(str(kv[1]))):
        s = str(wert)
        if not s or s not in template:
            return None
        template = template.replace(s, "{" + slot + "}", 1)
    # das abgeleitete Template muss ein GÜLTIGER Format-String sein: nur die bekannten Slots,
    # keine losen { } (die stünden als Literal im erwarteten Satz). Sonst würfe string.Formatter
    # später ein ValueError bis in die CLI -- hier ehrlich None statt Absturz, der Kandidat wird
    # übersprungen und der Loop fällt auf None (Review-Fund 2026-07-07).
    try:
        template.format(subject="", anzahl="", wert="")
    except (ValueError, KeyError, IndexError):
        return None
    return template


def _kandidaten(praedikate: list[str]):
    """Die zu prüfenden Beschaffungen, EINFACHSTE zuerst (Occam: der schlichteste Bauplan, der
    alle Fälle trägt, gewinnt). Prädikat-Bausteine nur mit Prädikaten, die im Graphen vorkommen."""
    yield {"art": "keine"}
    yield {"art": "anzahl_kanten"}
    for p in praedikate:
        yield {"art": "anzahl_kanten", "praedikat": p}
        yield {"art": "erstes_objekt", "praedikat": p}


def _besteht_alle(bauplan_dict: dict, graphen: list, faelle: list) -> bool:
    for conn, fall in zip(graphen, faelle):
        if _ausgabe(conn, bauplan_dict, fall.guess) != fall.erwartet:
            return False
    return True


def finde_bauplan(vertrag) -> dict | None:
    """SCHLIESST aus einem Abnahme-Vertrag einen Bauplan, der ALLE seine Fälle trägt — oder
    ``None``, wenn die Baustein-Vokabel den Satz nicht komponieren kann (ehrlich, nicht geraten).
    Rein deterministisch, kein LLM. Der zurückgegebene Bauplan ist ``pruefe_bauplan``-sauber und
    besteht den Vertrag in der Simulation; der endgültige Beweis ist der Abnahme-Vertrag am
    gefügten Code (Werkstatt-Probefahrt)."""
    faelle = list(vertrag.faelle)
    treffer = [f for f in faelle if f.erwartet is not None]
    if not treffer:
        return None
    graphen = [_graph(f.graph) for f in faelle]
    treffer_graph = _graph(treffer[0].graph)
    praedikate = sorted({k[1] for f in faelle for k in f.graph})
    for beschaffung in _kandidaten(praedikate):
        # 1. Slot-Werte des ersten Treffers roh produzieren (Wächter „keiner": der Treffer hat
        #    ohnehin ein subject; der echte Wächter wird gleich aus dem Template abgeleitet)
        slots = _simuliere(treffer_graph, beschaffung, "keiner",
                           (treffer[0].guess or {}).get("subject"))
        if not slots:
            continue
        formulierung = _leite_formulierung_ab(slots, treffer[0].erwartet)
        if formulierung is None:
            continue
        # 2. den Wächter DIREKT aus den Template-Slots ableiten -- NICHT bauplan.normalisiere:
        #    das ist für Modell-Notationsfehler gedacht und schriebe die Anführungszeichen des
        #    aus `erwartet` abgeleiteten Templates auf Guillemets um, sodass der Plan den
        #    Ground-Truth-Satz nicht mehr reproduziert (Review-Fund 2026-07-07). Die Formulierung
        #    bleibt Wort für Wort, wie der Autor sie im Abnahme-Vertrag festgelegt hat.
        try:
            im_template = {feld for _, feld, _, _ in string.Formatter().parse(formulierung) if feld}
        except ValueError:
            continue
        waechter = "subject" if "subject" in im_template else "keiner"
        plan = {"waechter": waechter, "beschaffung": beschaffung, "formulierung": formulierung}
        if bauplan.pruefe_bauplan(plan):
            continue
        # 3. gegen ALLE Fälle verifizieren (Treffer exakt, Passt-nicht -> None)
        if _besteht_alle(plan, graphen, faelle):
            return plan
    return None


def narrate(bauplan_dict: dict | None) -> str:
    """Gläserner Bericht, wie GENUS sich den Bauplan zusammengeschlossen hat (oder ehrlich, dass
    seine Bausteine nicht reichen) — im Ton von deduktion.narrate / recht.narrate_subsumtion."""
    if bauplan_dict is None:
        return ("Aus meinen bewährten Bausteinen kann ich diesen Fall nicht bauen — "
                "ehrlich: die Vokabel reicht (noch) nicht.")
    b = bauplan_dict["beschaffung"]
    art = b["art"]
    quelle = {
        "keine": "nichts aus dem Graphen (nur das Thema selbst)",
        "anzahl_kanten": "die Anzahl der Kanten"
                         + (f" über „{b['praedikat']}“" if b.get("praedikat") else ""),
        "erstes_objekt": f"das erste Objekt über „{b.get('praedikat')}“",
    }.get(art, art)
    return (f"Ich habe mir den Bauplan zusammengeschlossen: Wächter „{bauplan_dict['waechter']}“, "
            f"Beschaffung liest {quelle}, Formulierung: {bauplan_dict['formulierung']!r}. "
            f"Er trägt alle Fälle des Abnahme-Vertrags — der Beweis am gefügten Code folgt in der "
            f"Probefahrt.")
