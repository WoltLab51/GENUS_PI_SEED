"""Der BAUPLAN einer Gesprächszelle + das FÜGEWERK — Ronnys morphologische Zerlegung
(2026-07-04): „GENUS macht da seine morphologische Analyse: was brauchen wir, welche
Bestandteile. Dann werden Teile separat gebaut, und ein Durchgang fügt alles zusammen."

Der Schmied-Benchmark hatte gezeigt, WO kleine Code-Modelle scheitern: exakte deutsche
Anführungszeichen wegnormalisiert, KeyError-Schutz vergessen, Tabellen-Schemata erfunden.
Alles Dinge, die in der Zerlegung GAR NICHT MEHR beim Modell liegen: eine Zelle zerfällt
(Zwicky) in wenige unabhängige Bestandteile, fast alle deterministisch baubar --

  WÄCHTER       was muss in guess vorhanden sein?     (fester, geprüfter Baustein)
  BESCHAFFUNG   was wird aus dem Graphen gelesen?     (deklarativ: Art + Prädikat)
  ENTSCHEIDUNG  wann ehrlich None?                    (implizit: kein Treffer -> None)
  FORMULIERUNG  der exakte deutsche Satz              (ein Template als DATEN -- die
                                                       „ “ kann kein Modell mehr kaputt
                                                       normalisieren)

Das Modell schlägt nur noch den BAUPLAN vor (ein kleines JSON -- Daten, wie der Deuter
Zellen wählt statt Prosa zu schreiben); das FÜGEWERK (``fuege_zusammen``) setzt daraus
deterministisch den Handler-Code zusammen, aus geprüften Bausteinen: **vertragssicher
per Konstruktion.** Leitplanke und Sandbox-Probefahrt der Werkstatt laufen trotzdem
(Verteidigung in der Tiefe), aber sie müssen nichts mehr retten.

Bewusst klein begonnen (Merkmal erst wenn erkannt + notwendig): genau die Achsen-Werte,
die die drei Benchmark-Aufgaben brauchen. Neue Beschaffungs-Arten werden REGISTRIERT
(``BESCHAFFUNGEN``), nicht in eine if-Kette geschrieben.
"""
from __future__ import annotations

import re
import string

WAECHTER = ("subject", "keiner")

# Beschaffungs-Arten: Art -> (erlaubte Template-Slots, braucht Prädikat?)
BESCHAFFUNGEN: dict[str, dict] = {
    "keine": {"slots": {"subject"}, "praedikat": False},
    "anzahl_kanten": {"slots": {"subject", "anzahl"}, "praedikat": "optional"},
    "erstes_objekt": {"slots": {"subject", "wert"}, "praedikat": True},
}

_PRAEDIKAT = re.compile(r"^[a-z_]+$")
_ALLE_SLOTS = {"subject", "anzahl", "wert"}
_SPITZE_SLOTS = re.compile(r"<(" + "|".join(sorted(_ALLE_SLOTS)) + r")>")
_ASCII_PAAR = re.compile(r'"([^"]*)"')


def normalisiere(plan: dict) -> dict:
    """Der GLÄTTUNGS-Durchgang vor dem Fügen (Ronnys „ein Durchgang fügt alles
    zusammen") -- deterministische Korrekturen eindeutiger Notations-Varianten, live im
    A/B-Benchmark gefunden: (1) ein Modell kopiert die ``<subject>``-Notation einer
    Aufgabenstellung wörtlich statt ``{subject}`` zu schreiben -- eindeutig, wird
    umgeschrieben; (2) der WÄCHTER wird aus den Template-Slots ABGELEITET (nutzt die
    Formulierung ``{subject}``, muss der Wächter subject sein -- Zwickys
    Kreuz-Konsistenz, vom Kern erzwungen statt vom Modell erhofft). Niemals inhaltliche
    Reparatur -- nur Notation und ableitbare Konsistenz."""
    if not isinstance(plan, dict):
        return plan
    plan = dict(plan)
    template = plan.get("formulierung")
    if isinstance(template, str):
        template = _SPITZE_SLOTS.sub(r"{\1}", template)
        # Deutsche Typografie ist KERN-Sache (jede narrate-Ausgabe nutzt „ “) -- ein
        # Modell, das auf ASCII-Paare zurückfällt, wird deterministisch normalisiert
        # (Grenze-A/B-Fund: die 1.5B trafen Struktur und Semantik, aber nie die „ “)
        template = _ASCII_PAAR.sub("„\\1“", template)
        plan["formulierung"] = template
        slots = {feld for _, feld, _, _ in string.Formatter().parse(template) if feld}
        if "subject" in slots:
            plan["waechter"] = "subject"   # ableitbar -- das Modell muss es nicht wissen
        elif plan.get("waechter") is None:
            plan["waechter"] = "keiner"
    return plan


def pruefe_bauplan(plan: dict) -> list[str]:
    """Ist der Bauplan wohlgeformt? Liste von Fehlern (leer = fügbar). Dieselbe
    Prüf-Disziplin wie werkzeug.pruefen: nie stillschweigend etwas Halbgares fügen."""
    fehler: list[str] = []
    if not isinstance(plan, dict):
        return ["Bauplan ist kein Objekt."]
    waechter = plan.get("waechter")
    if waechter not in WAECHTER:
        fehler.append(f"waechter muss eines von {WAECHTER} sein, nicht {waechter!r}.")
    beschaffung = plan.get("beschaffung")
    if not isinstance(beschaffung, dict) or beschaffung.get("art") not in BESCHAFFUNGEN:
        fehler.append(
            f"beschaffung.art muss eine registrierte Art sein "
            f"({', '.join(sorted(BESCHAFFUNGEN))})."
        )
        return fehler   # ohne gültige Art sind Slot-/Prädikat-Prüfung sinnlos
    art = BESCHAFFUNGEN[beschaffung["art"]]
    praedikat = beschaffung.get("praedikat")
    if art["praedikat"] is True and not praedikat:
        fehler.append(f"beschaffung „{beschaffung['art']}“ braucht ein praedikat.")
    if praedikat is not None and not _PRAEDIKAT.match(str(praedikat)):
        fehler.append(f"praedikat {praedikat!r} ist nicht wohlgeformt (^[a-z_]+$).")
    if art["praedikat"] is False and praedikat:
        fehler.append(f"beschaffung „{beschaffung['art']}“ kennt kein praedikat.")
    template = plan.get("formulierung")
    if not isinstance(template, str) or not template.strip():
        fehler.append("formulierung fehlt (der exakte deutsche Antwortsatz als Template).")
        return fehler
    slots = {feld for _, feld, _, _ in string.Formatter().parse(template) if feld}
    fremde = slots - art["slots"]
    if fremde:
        fehler.append(
            f"formulierung nutzt Slots {sorted(fremde)}, die die Beschaffung "
            f"„{beschaffung['art']}“ nicht liefert (erlaubt: {sorted(art['slots'])})."
        )
    return fehler


def gbnf_grammatik() -> str:
    """Die GRENZE für den Bauplan-Finder (llama.cpp-GBNF) — die Konvergenz von Ronnys
    zwei Ideen: die Zerlegung schrumpfte den Suchraum auf drei JSON-Felder, die Grenze
    macht die verbliebenen Fehlerklassen strukturell unmöglich. Aus der
    ``BESCHAFFUNGEN``-Registry ABGELEITET (wächst die Registry, wächst die Grenze):

    - ``waechter``/``art`` sind Enums — eine unregistrierte Art ist nicht tippbar.
    - ``praedikat`` ist ``[a-z_]+`` — ``guess['subject']`` ist nicht tippbar.
    - Das Template erlaubt JE ART nur deren Slots (Zwickys Kreuz-Konsistenz IN der
      Grammatik: ``{anzahl}`` existiert nur bei anzahl_kanten), und literale ``{``/``}``
      sind ausgeschlossen — ein erfundener Slot wie ``{n}`` ist nicht tippbar.

    Garantiert wohlgeformt-im-Raum, nicht richtig (Naht 2 gilt weiter): den SINN des
    Satzes muss das Modell weiterhin treffen."""
    waechter_alt = " | ".join(f'"\\"{w}\\""' for w in WAECHTER)
    regeln = [
        'root ::= "{" ws waechter ws "," ws ('
        + " | ".join(f"bf-{art.replace('_', '-')}" for art in sorted(BESCHAFFUNGEN))
        + ') ws "}"',
        f'waechter ::= "\\"waechter\\"" ws ":" ws ({waechter_alt})',
        'praedikat ::= "\\"praedikat\\"" ws ":" ws "\\"" [a-z_]+ "\\""',
    ]
    for art in sorted(BESCHAFFUNGEN):
        spec = BESCHAFFUNGEN[art]
        sicher = art.replace("_", "-")
        kopf = f'"\\"beschaffung\\"" ws ":" ws "{{" ws "\\"art\\"" ws ":" ws "\\"{art}\\""'
        if spec["praedikat"] is True:
            kopf += ' ws "," ws praedikat'
        elif spec["praedikat"] == "optional":
            kopf += ' (ws "," ws praedikat)?'
        kopf += ' ws "}"'
        regeln.append(
            f'bf-{sicher} ::= {kopf} ws "," ws "\\"formulierung\\"" ws ":" ws '
            f"template-{sicher}"
        )
        slot_alt = " | ".join(f'"{{{s}}}"' for s in sorted(spec["slots"]))
        regeln.append(f'template-{sicher} ::= "\\"" (zeichen | {slot_alt})* "\\""')
    regeln += [
        'zeichen ::= [^"{}\\\\] | "\\\\" ["\\\\/bfnrt]',
        'ws ::= [ \\t\\n]*',
    ]
    return "\n".join(regeln)


def _beschaffungs_baustein(beschaffung: dict) -> tuple[str, str]:
    """Der geprüfte Code-Baustein einer Beschaffungs-Art: (Rumpf-Zeilen, Format-Aufruf).
    Prädikate laufen IMMER als SQL-Parameter -- nie in den Query-Text gefügt."""
    art = beschaffung["art"]
    praedikat = beschaffung.get("praedikat")
    if art == "keine":
        return ("", "subject=subject")
    if art == "anzahl_kanten":
        if praedikat:
            rumpf = (
                "    zeile = conn.execute(\n"
                "        \"SELECT COUNT(*) AS n FROM relation_projection \"\n"
                "        \"WHERE subject = ? AND predicate = ?\",\n"
                f"        (subject, {praedikat!r}),\n"
                "    ).fetchone()\n"
            )
        else:
            rumpf = (
                "    zeile = conn.execute(\n"
                "        \"SELECT COUNT(*) AS n FROM relation_projection WHERE subject = ?\",\n"
                "        (subject,),\n"
                "    ).fetchone()\n"
            )
        rumpf += (
            "    anzahl = int(zeile[0]) if zeile is not None else 0\n"
            "    if anzahl == 0:\n"
            "        return None\n"
        )
        return (rumpf, "subject=subject, anzahl=anzahl")
    if art == "erstes_objekt":
        rumpf = (
            "    zeile = conn.execute(\n"
            "        \"SELECT object FROM relation_projection \"\n"
            "        \"WHERE subject = ? AND predicate = ? ORDER BY object LIMIT 1\",\n"
            f"        (subject, {praedikat!r}),\n"
            "    ).fetchone()\n"
            "    if zeile is None:\n"
            "        return None\n"
            "    wert = zeile[0]\n"
        )
        return (rumpf, "subject=subject, wert=wert")
    raise ValueError(f"unbekannte Beschaffungs-Art {art!r}")   # pruefe_bauplan verhindert das


def fuege_zusammen(blatt: str, plan: dict) -> str:
    """Das FÜGEWERK: ein geprüfter Bauplan wird deterministisch zum Handler-Code --
    jeder Bestandteil ein fester, getesteter Baustein; das Template landet als
    repr()-Literal im Code (nie interpretiert, keine Injektion). Wirft ValueError bei
    einem Bauplan, der die Prüfung nicht besteht -- nie stilles Fügen."""
    plan = normalisiere(plan)
    fehler = pruefe_bauplan(plan)
    if fehler:
        raise ValueError("Bauplan nicht fügbar:\n" + "\n".join(fehler))
    name = blatt.replace("-", "_")
    zeilen = [
        f'"""Gesprächszelle „{blatt}“ — gefügt aus einem morphologischen Bauplan\n'
        f"(genus/bauplan.py): Wächter, Beschaffung und Formulierung sind geprüfte\n"
        f"Bestandteile; das Modell hat nur den Plan vorgeschlagen, nie den Code.\n"
        f'"""\n',
        "\n",
        f"def zelle_{name}(conn, guess, question, last_question, last_answer, "
        f"stimme=None):\n",
    ]
    if plan["waechter"] == "subject":
        zeilen.append(
            "    subject = (guess or {}).get(\"subject\")\n"
            "    if not isinstance(subject, str) or not subject:\n"
            "        return None\n"
        )
    else:
        zeilen.append("    subject = (guess or {}).get(\"subject\")\n")
    rumpf, formatierung = _beschaffungs_baustein(plan["beschaffung"])
    zeilen.append(rumpf)
    zeilen.append(f"    return {plan['formulierung']!r}.format({formatierung})\n")
    return "".join(zeilen)
