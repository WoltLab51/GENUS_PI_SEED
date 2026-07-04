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


def morgen_nachricht(conn, bericht: dict | None) -> str:
    """Die EINE Morgen-Nachricht — warm, nativ, deterministisch komponiert (Ronnys
    Entscheidungen: nie leer; Zusammenfassung; nett). Reihenfolge: Gruß → gestern
    (falls konsolidiert) → Wartendes (Freigaben/Fragen) → falls sonst nichts: das
    frisch Gelernte der Nacht → warmer Schluss. Der TON kommt aus dem Antwort-Würfel
    (Belegung der Rolle „morgen": hebt die Wärme um eine Stufe; Kreuz-Konsistenz zentral,
    z.B. entfällt die Rückfrage bei „knapp") — die Persönlichkeit wählt Formulierungen,
    nie Inhalte."""
    from genus import antwort, inquiries, proposals

    reg = antwort.belegung(conn, "morgen")
    warm = reg["waerme"] in ("warm", "herzlich")
    teile: list[str] = ["Guten Morgen, Ronny!" if warm else "Guten Morgen, Ronny."]
    inhalt = False

    themen = (bericht or {}).get("themen") or []
    if themen:
        namen = " und ".join(f"„{t['label']}“" for t in themen[:2])
        teile.append(f"Gestern haben dich vor allem {namen} beschäftigt — "
                     f"ich habe es mir still gemerkt. Wenn etwas davon nicht stimmt, "
                     f"sag einfach Bescheid.")
        if reg["beiwerk_rueckfrage"]:
            teile.append("Magst du mir heute mehr davon erzählen?")
        inhalt = True

    offene_proposals = [p for p in proposals.list_proposals(conn)]
    if offene_proposals:
        erster = offene_proposals[0]
        teile.append(f"Es warten {len(offene_proposals)} Vorschläge auf deine Freigabe — "
                     f"der älteste: Proposal #{erster['id']}.")
        inhalt = True

    offene_fragen = inquiries.list_inquiries(conn, include_all=False)
    if offene_fragen and not offene_proposals:
        teile.append(f"Mich beschäftigen gerade {len(offene_fragen)} offene Fragen — "
                     f"frag mich im Chat „Was beschäftigt dich?“, wenn du magst.")
        inhalt = True

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
