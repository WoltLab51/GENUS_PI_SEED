"""Nacht-Konsolidierung + Morgen-Nachricht (docs/GENUS_GEDAECHTNIS.md, Punkt ④ — Ronnys
Entscheidungen 2026-07-03/04: Tagespuffer ja · nachts still merken, morgens berichten ·
genau EINE Morgen-Nachricht, 06:00, nie leer, warm und nativ formuliert).

Dem Gehirn nachempfunden (McClelland/McNaughton/O'Reilly 1995): tagsüber schreibt die
Membran mit (Tagespuffer, Rohtext NUR dort, verfällt — Ledger ≠ Memory), nachts liest die
Konsolidierung den Puffer EINMAL, destilliert Struktur und vergisst den Rest, morgens
berichtet GENUS in einem Satz, was hängengeblieben ist — der Lehrer-Loop am Frühstückstisch.

Alles hier ist DETERMINISTISCH (Ronny: „ich will nativen Text, keine kryptischen
Ausgaben" — der Text ist nativ, weil die Vorlagen es sind, nicht weil ein Modell rät).
Die Themen-Erkennung nutzt die vorhandene Text→Konzept-Auflösung (sources); die still
gemerkten Episoden tragen die Quelle ``model:nacht`` und sind damit automatisch gedeckelt
wie alles Modellhafte — korrigierbar am Morgen mit einem Wort."""
from __future__ import annotations

import json
import re

from genus import sources

NACHT_QUELLE = "model:nacht"   # gedeckelt über den bestehenden model:*-Vertrauensdeckel
_WORT = re.compile(r"[\wäöüÄÖÜß]{4,}", re.UNICODE)
_THEMA_AB = 2   # ein Konzept wird Thema, wenn es in mindestens 2 Zügen vorkam


def _konzepte_im_text(conn, text: str) -> set[str]:
    gefunden: set[str] = set()
    for tok in _WORT.findall(text):
        for form in (tok, tok[:1].upper() + tok[1:]):
            if sources.bekanntes_wort(conn, form):
                gefunden.add(sources.prominentes_konzept(conn, form) or f"{form}@de")
                break
    return gefunden


def _label(conn, konzept: str) -> str:
    anzeige = sources.display(conn, konzept)
    m = re.search(r"\(([^)]+)\)", anzeige)
    if m:
        return m.group(1)
    return konzept.split("@", 1)[0]


def konsolidiere(conn, zuege: list[dict]) -> dict:
    """Liest die Züge des Tages (Daten aus dem Tagespuffer der Membran) und destilliert:
    THEMEN (Konzepte, die in ≥2 Zügen vorkamen — über die Text→Konzept-Auflösung, kein
    Modell), still gemerkte EPISODEN pro Thema (Quelle ``model:nacht``, gedeckelt) und die
    Warum-Folgen-KENNZAHL (ein „warum?" direkt nach einer Antwort = Beleg fürs
    Antwort-Würfel-Lernen). Der Aufrufer leert den Puffer danach — Vergessen ist Funktion."""
    from genus import companion, erinnerung

    je_konzept: dict[str, int] = {}
    warum_folgen = 0
    for zug in zuege:
        frage = zug.get("question") or ""
        for konzept in _konzepte_im_text(conn, frage):
            je_konzept[konzept] = je_konzept.get(konzept, 0) + 1
        if companion.is_why_followup(frage):
            warum_folgen += 1

    themen = [
        {"konzept": konzept, "label": _label(conn, konzept), "anzahl": anzahl}
        for konzept, anzahl in sorted(je_konzept.items(), key=lambda kv: -kv[1])
        if anzahl >= _THEMA_AB
    ]
    episoden = []
    for thema in themen:
        eid = erinnerung.merke(
            conn,
            f"Gestern ging es mehrfach um „{thema['label']}“.",
            quelle=NACHT_QUELLE,
        )
        episoden.append(eid)
    return {"themen": themen, "warum_folgen": warum_folgen,
            "episoden": episoden, "zuege": len(zuege)}


def _neustes_gelerntes_wort(conn) -> dict | None:
    """Das jüngste vom Nacht-Lerner erworbene Wort samt Bedeutung — der warme Füllstoff
    für einen Morgen ohne Neuigkeiten (der Lerner lernt wirklich jede Nacht)."""
    row = conn.execute(
        "SELECT subject FROM relation_projection "
        "WHERE predicate = 'expresses' AND subject LIKE '%@de' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    wort = row["subject"].split("@", 1)[0]
    gloss_row = conn.execute(
        "SELECT object FROM relation_projection "
        "WHERE subject = ? AND predicate IN ('primary_gloss', 'defined_as') "
        "ORDER BY id LIMIT 1",
        (row["subject"],),
    ).fetchone()
    return {"wort": wort, "bedeutung": gloss_row["object"] if gloss_row else None}


# --- Morgen-Triage der Proposals (Ronny 2026-07-08: „mach die Morgen-Triage") ------------
#
# Die Morgen-Nachricht zählte bisher ALLE offenen Vorschläge flach („Es warten 8 Vorschläge,
# ältester #6") und zeigte damit auf einen abgestandenen Betriebs-Hinweis, während der EINE,
# der Ronny wirklich braucht (ein Selbst-Codier-Vorschlag mit ``action_required``), im
# Monitoring-Rauschen unterging. Ein guter „digitaler Mitarbeiter" triagiert: was dein OK
# braucht ZUERST und einzeln, wiederkehrende Betriebs-Meldungen zu EINER FYI-Zeile gebündelt.
# Die Unterscheidung ist keine Heuristik, sondern liegt schon im Proposal-Payload: der
# Erzeuger setzt ``action_required`` (True nur beim ExperienceProposal/Selbst-Codieren; die
# Operation/Resource-Wächter setzen es bewusst False -- reines Monitoring).
_BETRIEB_PHRASE = {
    "system.network": "das Netzwerk war {mal} instabil",
    "system.load": "die Systemlast war {mal} hoch",
    "system.clock": "die Uhr war {mal} nicht synchron",
}
_MAL = {1: "einmal", 2: "zweimal", 3: "dreimal"}


def _mal(n: int) -> str:
    return _MAL.get(n, f"{n}-mal")


def _proposal_payload(p: dict) -> dict:
    """Der Inhalts-Payload eines Proposals als Dict -- robust gegen kaputtes JSON UND gegen
    gültiges Nicht-Objekt-JSON (``null``/``5``/``[...]`` decodieren fehlerfrei, sind aber kein
    Dict): beides wird zu ``{}`` (also automatisch Betrieb/nicht-dringend), nie ein Absturz der
    Morgen-Nachricht."""
    roh = p.get("payload")
    if isinstance(roh, dict):
        return roh
    try:
        wert = json.loads(roh) if roh else {}
    except (ValueError, TypeError):
        return {}
    return wert if isinstance(wert, dict) else {}


def triagiere_proposals(offene: list[dict]) -> tuple[list[dict], list[dict]]:
    """Teilt offene Vorschläge in DRINGEND (``action_required`` -- braucht Ronnys Entscheidung)
    und BETRIEB (Monitoring, gebündelt gemeldet). Reine Lese-Sicht, kein Schreiben."""
    dringend, betrieb = [], []
    for p in offene:
        (dringend if _proposal_payload(p).get("action_required") else betrieb).append(p)
    return dringend, betrieb


def betrieb_zeile(betrieb: list[dict]) -> str:
    """Die EINE FYI-Zeile für die wiederkehrenden Betriebs-Meldungen, nach Claim gebündelt und
    gezählt (5 Netz-Episoden werden „das Netzwerk war 5-mal instabil", nicht fünf Vorschläge).
    Ein unbekannter Claim wird NICHT als roher Knoten-Name ausgegeben (nie kryptisch) und nie
    durch ``.format`` geschickt (Format-String-Injektion aus daten-kontrolliertem Key) -- er
    zählt generisch als „weiterer Betriebs-Hinweis". ``.format`` trifft so nur die eigenen,
    festen Vorlagen."""
    anzahl: dict[str, int] = {}
    for p in betrieb:
        schluessel = p.get("claim_key") or ""
        anzahl[schluessel] = anzahl.get(schluessel, 0) + 1
    stuecke: list[str] = []
    sonstige = 0
    for k, n in anzahl.items():
        if k in _BETRIEB_PHRASE:
            stuecke.append(_BETRIEB_PHRASE[k].format(mal=_mal(n)))
        else:
            sonstige += n
    if sonstige == 1:
        stuecke.append("es gab einen weiteren Betriebs-Hinweis")
    elif sonstige:
        stuecke.append(f"es gab {sonstige} weitere Betriebs-Hinweise")
    return ("Fürs Protokoll (nichts, was du tun musst): "
            + " und ".join(stuecke) + ".")


def morgen_nachricht(conn, bericht: dict | None, jetzt_iso: str | None = None) -> str:
    """Die EINE Morgen-Nachricht — warm, nativ, deterministisch komponiert (Ronnys
    Entscheidungen: nie leer; Zusammenfassung; nett). Reihenfolge: Gruß → gestern
    (falls konsolidiert) → Wartendes (Freigaben/Fragen) → falls sonst nichts: das
    frisch Gelernte der Nacht → warmer Schluss. Der TON kommt aus dem Antwort-Würfel
    (Belegung der Rolle „morgen": hebt die Wärme um eine Stufe; Kreuz-Konsistenz zentral,
    z.B. entfällt die Rückfrage bei „knapp") — die Persönlichkeit wählt Formulierungen,
    nie Inhalte."""
    from genus import antwort

    reg = antwort.belegung(conn, "morgen")
    warm = reg["waerme"] in ("warm", "herzlich")
    teile: list[str] = ["Guten Morgen, Ronny!" if warm else "Guten Morgen, Ronny."]
    inhalt = False

    # Ein kurzes Morgen-Briefing aus den Sinnen (P4): Wetter + oberste Schlagzeile, beide nur bei
    # frischem Material (companion schweigt sonst). Der Morgen-Gruss wird wortgetreu gesendet
    # (kein Modell), also bleibt die fremde Schlagzeile unangetastet.
    from genus import companion

    wetter = companion.wetter_kurz(conn)
    if wetter:
        teile.append(f"Draußen ist es {wetter}.")
        inhalt = True
    schlagzeile = companion.news_top(conn)
    if schlagzeile:
        teile.append(f"In den Nachrichten: „{schlagzeile}“.")
        inhalt = True

    # Herzschlag-Wächter der ersten Hand (P4): steht der Membran-Sende-Tick still, bleiben
    # freigegebene, fällige Erinnerungen ungesendet liegen. Die Morgen-Nachricht läuft über EINEN
    # ANDEREN Weg (morgen_push.sh) als der Sender — also erreicht diese Warnung Ronny selbst dann,
    # wenn genau der Sende-Dienst kaputt ist. Der Jetzt-Zeitpunkt ist eine reine Anzeige-Entscheidung.
    import datetime as _dt

    from genus import hand

    jetzt = jetzt_iso or _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    spaet = hand.ueberfaellige(conn, jetzt)
    if spaet:
        was = "eine Erinnerung ist" if len(spaet) == 1 else f"{len(spaet)} Erinnerungen sind"
        teile.append(f"Achtung: {was} überfällig und noch nicht gesendet — bitte sieh nach dem "
                     f"Sende-Dienst (deploy/hand_ausfuehren.sh).")
        inhalt = True

    themen = (bericht or {}).get("themen") or []
    if themen:
        namen = " und ".join(f"„{t['label']}“" for t in themen[:2])
        teile.append(f"Gestern haben dich vor allem {namen} beschäftigt — "
                     f"ich habe es mir still gemerkt. Wenn etwas davon nicht stimmt, "
                     f"sag einfach Bescheid.")
        if reg["beiwerk_rueckfrage"]:
            teile.append("Magst du mir heute mehr davon erzählen?")
        inhalt = True

    # Vorschläge und offene Fragen wandern NICHT mehr in den Morgengruß (Ronny 2026-07-08: „der
    # Morgengruß soll ein schöner Gruß sein"): das WICHTIGE (Entscheidungs-Vorschläge + selbst
    # gebildete Begriffs-Fragen) schickt GENUS proaktiv, sobald es das hat (genus/gedanke.py),
    # nicht aufgestaut bis zum nächsten Morgen. Der Gruß bleibt warm. (Die Überfälligkeits-Warnung
    # oben BLEIBT hier: sie meldet gerade, wenn der proaktive Sende-Weg selbst steht.)
    if not inhalt:
        gelernt = _neustes_gelerntes_wort(conn)
        if gelernt and gelernt["bedeutung"]:
            teile.append(f"Heute Nacht habe ich „{gelernt['wort']}“ gelernt: "
                         f"{gelernt['bedeutung']}")
        elif gelernt:
            teile.append(f"Heute Nacht habe ich das Wort „{gelernt['wort']}“ gelernt.")
        else:
            teile.append("Die Nacht war ruhig — ich habe gelesen und gelernt.")

    schluss = ("Ich wünsche dir einen richtig guten Start in den Tag!"
               if reg["waerme"] == "herzlich"
               else "Ich wünsche dir einen guten Start in den Tag!")
    if reg["humor"] == "dezent":
        schluss += " (Ich übe derweil weiter Vokabeln — einer muss es ja tun.)"
    teile.append(schluss)
    return " ".join(teile)
