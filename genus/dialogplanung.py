"""Lokale Eskalationsplanung zwischen Sprachlesart, Wissensgraph und Antwortentwurf."""

from __future__ import annotations

import re

from genus import sources
from genus.auskunft import (
    _kausal_zwischen,
    answer,
    antizipation,
    direkte_beziehung,
    narrate_direkte_beziehung,
    narrate_kausal,
    narrate_relation,
    relate,
)

_DEFINITION = re.compile(
    r"^\s*(?:was\s+ist|was\s+bedeutet)\s+"
    r"(?:(?:denn|eigentlich|genau)\s+)*(?:(?:ein|eine|einen|der|die|das)\s+)?"
    r"([A-Za-zäöüÄÖÜß-]+)\s*[?!.]*\s*$", re.IGNORECASE,
)
_ZUSAMMENHANG = re.compile(
    r"^\s*wie\s+hängen\s+(?:ein(?:e[nmr]?)?|der|die|das)?\s*"
    r"([A-Za-zäöüÄÖÜß-]+)\s+und\s+(?:ein(?:e[nmr]?)?|der|die|das)?\s*"
    r"([A-Za-zäöüÄÖÜß-]+)\s+zusammen\s*[?!.]*\s*$", re.IGNORECASE,
)
_WARUM_THEMA = re.compile(
    r"^\s*(?:warum|wieso|weshalb)\s+(?:denn\s+)?(.+?)\s*[?!.]*\s*$", re.IGNORECASE,
)
_CHAT_TEST = re.compile(
    r"\b(?:chat|bot|dich|genus)\b.{0,24}\btest(?:en|e)?\b", re.IGNORECASE,
)
_NEU_REAKTION = re.compile(
    r"\b(?:kannte|kenne)\s+ich\s+(?:noch\s+)?(?:gar\s*nicht|nicht)\b", re.IGNORECASE,
)
_ANKER = re.compile(r"»([^»]+)«")


def definitionsbegriff(question: str) -> str | None:
    """Der sicher verankerte Einzelbegriff einer einfachen Definitionsfrage."""
    treffer = _DEFINITION.match(question)
    return treffer.group(1) if treffer else None


def zusammenhangsbegriffe(question: str) -> tuple[str, str] | None:
    """Die zwei Begriffe der engen lokalen Form „Wie hängen X und Y zusammen?“."""
    treffer = _ZUSAMMENHANG.match(question)
    return (treffer.group(1), treffer.group(2)) if treffer else None


def kurze_reaktion(question: str, last_answer: str | None = None) -> str | None:
    """Eindeutige Gesprächsreaktionen lokal beantworten, ohne sie als Fakten zu speichern."""
    if _CHAT_TEST.search(question):
        return "Klar — leg los. Ich bin bereit."
    if not _NEU_REAKTION.search(question):
        return None
    anker = _ANKER.search(last_answer or "")
    if last_answer and "noch nicht sauber erklären" in last_answer:
        name = f" »{anker.group(1)}«" if anker else " diesen Begriff"
        return (f"Ich kenne{name} bisher selbst nur grob. Deshalb hätte ich ihn dir nicht "
                "als Anschluss vorschlagen sollen.")
    return "Dann war das gerade wirklich neu für dich."


def beziehungs_antwort(conn, subject: str, object_: str, bel=None, *, allgemein=False):
    """Plant Sachkante, Taxonomie und Kausalität evidenztreu."""
    from genus import antwort, werkzeuge_auskunft

    taxonomie = werkzeuge_auskunft.relate_geplant(conn, subject, object_)
    if not allgemein and taxonomie["relational"] and taxonomie["verdict"] == "yes":
        text = narrate_relation(conn, taxonomie, bel)
        return antwort.AnswerText(text, antwort.entwurf_beziehung(taxonomie, text))
    direkt = direkte_beziehung(conn, subject, object_, beide_richtungen=allgemein)
    if direkt is not None:
        text = narrate_direkte_beziehung(direkt)
        draft = antwort.entwurf_beziehung(direkt, text, predicate=direkt["predicate"])
        return antwort.AnswerText(text, draft)
    if taxonomie["relational"] and taxonomie["verdict"] == "yes":
        text = narrate_relation(conn, taxonomie, bel)
        return antwort.AnswerText(text, antwort.entwurf_beziehung(taxonomie, text))
    kausal = _kausal_zwischen(conn, subject, object_)
    if kausal["kausal_q"] and kausal["art"] == "ja":
        return narrate_kausal(conn, kausal, bel)
    if not taxonomie["relational"]:
        return None
    if allgemein:
        text = (f"Zwischen »{taxonomie['subject']}« und »{taxonomie['object']}« finde ich "
                "derzeit keine belegte Verbindung. Das heißt: unbekannt, nicht widerlegt.")
        leer = {"relational": True, "verdict": "no_path",
                "subject": taxonomie["subject"], "object": taxonomie["object"]}
        return antwort.AnswerText(
            text, antwort.entwurf_beziehung(leer, text, predicate="related_to"),
        )
    text = narrate_relation(conn, taxonomie, bel)
    return antwort.AnswerText(text, antwort.entwurf_beziehung(taxonomie, text))


def _kante(conn, subject: str, predicate: str, object_: str, source: str) -> str:
    vertrauen = sources.source_trust(conn, source)
    return (f"{sources.display(conn, subject)} —{predicate}→ {sources.display(conn, object_)}"
            f"   ← {source} (Vertrauen {vertrauen:.2f})")


def kompakte_spur(conn, question: str) -> str:
    """Gesprächsfähige Herkunft der gewählten Bedeutung statt vollständigem Debug-Dump."""
    relation = relate(conn, question)
    if relation.get("relational"):
        if relation["verdict"] != "yes":
            return (f"Dazu finde ich keine belegte is_a-Verbindung von "
                    f"»{relation['subject']}« zu »{relation['object']}«.")
        zeilen = [f"Die Herleitung von »{relation['subject']}« zu »{relation['object']}«:"]
        zeilen.extend("  " + _kante(conn, p["subject"], p["predicate"], p["object"], p["source"])
                       for p in relation["chain"])
        return "\n".join(zeilen)
    material = answer(conn, question)
    if not material.get("found"):
        return "Dazu kann GENUS derzeit nichts belegen."
    key = f"{material['word']}@de"
    zeilen = [f"Woher GENUS »{material['word']}« kennt:"]
    ausdruecke = sources.relations(conn, subject=key, predicate=sources.EXPRESSES)
    passend = [r for r in ausdruecke if r["object"] == material.get("concept")]
    if passend:
        r = sorted(passend, key=lambda row: row["source"] != "wikidata")[0]
        zeilen.append("  " + _kante(conn, key, "expresses", r["object"], r["source"]))
    gloss = (material.get("meaning") or [None])[0]
    if gloss:
        for praedikat in ("primary_gloss", "defined_as"):
            kanten = sources.relations(conn, subject=key, predicate=praedikat, object=gloss)
            if kanten:
                r = kanten[0]
                zeilen.append(f"  Bedeutung »{gloss}«   ← {r['source']} "
                              f"(Vertrauen {sources.source_trust(conn, r['source']):.2f})")
                break
    if material.get("concept"):
        for r in sources.relations(conn, subject=material["concept"], predicate="is_a")[:2]:
            zeilen.append("  " + _kante(conn, r["subject"], "is_a", r["object"], r["source"]))
    return "\n".join(zeilen)


def nachfrage_antwort(conn, guess: dict, last_question: str | None) -> str | None:
    """Explizites Thema schlägt den vorigen Zug; bare Nachfrage bleibt am Anker."""
    subject = guess.get("subject")
    if subject:
        if last_question:
            basis = answer(conn, last_question)
            if basis.get("concept"):
                direkt = direkte_beziehung(conn, basis["word"], subject)
                if direkt is not None:
                    return ("Der Zusammenhang in meinem Wissensgraphen ist: "
                            + narrate_direkte_beziehung(direkt)
                            + " Als Anschluss an deine vorige Frage war dieser Sprung aber "
                              "zu weit — der Vorschlag war unpassend.")
        return kompakte_spur(conn, f"Was ist {subject}?")
    return kompakte_spur(conn, last_question) if last_question else None


def anschluss_begruendung(question: str, beleg: dict | None,
                          last_question: str | None) -> dict | None:
    """Begründet genau den gespeicherten Vorschlag, statt den vorigen Zug neu zu deuten."""
    treffer = _WARUM_THEMA.match(question)
    if not treffer or not beleg:
        return None
    if treffer.group(1).strip().casefold() != str(beleg.get("object") or "").casefold():
        return None
    direkt = {"subject": beleg["subject"], "object": beleg["object"],
              "predicate": beleg["predicate"]}
    text = ("Ich hatte das vorgeschlagen, weil mein Wissensgraph diese Verbindung enthält: "
            + narrate_direkte_beziehung(direkt)
            + " Für deine vorige Frage war der Anschluss offenbar zu weit gesprungen.")
    return {"text": text, "question": last_question or question,
            "gelesen": ["warum-herkunft"], "outcome": "answered"}


def anschluss_beiwerk(conn, question: str, aktiv: bool, *, outcome="answered") \
        -> tuple[str, str | None, dict | None]:
    """Genau ein beantwortbarer, relevanter Anschluss; nie nach unbekanntem Ergebnis."""
    if not aktiv or outcome != "answered":
        return "", None, None
    from genus import antwort

    if not antwort.belegung(conn, "plausch")["beiwerk_rueckfrage"]:
        return "", None, None
    material = answer(conn, question)
    if not material.get("found") or not material.get("concept"):
        return "", None, None
    angebot = antizipation(conn, material)
    if angebot is None:
        return "", None, None
    return " " + angebot["text"], angebot["frage"], angebot.get("beleg")
