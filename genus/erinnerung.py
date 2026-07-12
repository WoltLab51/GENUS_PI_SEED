"""Erinnerungen als echte Episoden -- siehe „Wie eine Episode entsteht“ und „Abruf“ in
``docs/design/MEMORY.md``.

Tulving (1972): episodisches Gedächtnis (an Zeit/Sprecher gebundene Ereignisse) ist etwas
anderes als semantisches Gedächtnis (zeitloses Allgemeinwissen, der Wissensgraph). Bisher
lagen alle Notizen flach unter einem einzigen Knoten (``genus:notizen -notiz-> "<Text>"``) --
ein Stern ohne Netz: zwei Notizen über dasselbe Thema (z.B. ein Konzert) wussten nichts
voneinander und nichts vom passenden Begriff im Graphen. Das war der Kernbefund, der das
Gespräch trotz allem "dumm" wirken ließ -- nicht die Vermittlung (Deuter/Stimme/Würfel),
sondern das Fehlen von echtem Abruf.

Eine Episode ist jetzt ein eigener Knoten mit genau VIER Kanten -- keine weitere auf Vorrat
(Merkmal-Disziplin: erst bei erkannter Notwendigkeit):

    erinnerung:<id>  -inhalt->    "<Wortlaut der Klausel>"
    erinnerung:<id>  -von->       "<Quelle>"          (ronny | model:deuter, wie überall)
    erinnerung:<id>  -am->        "<Datum>"           (Zeitanker, Tulving: Episoden sind datiert)
    erinnerung:<id>  -erwaehnt->  "<Konzept-Qid oder Begriff@de>"  (0..n Kanten, siehe unten)

Damit sind Episoden DURCH DAS WISSEN vernetzt, nicht direkt aneinander -- exakt wie beim
Menschen: zwei Erinnerungen über dasselbe Thema treffen sich am gemeinsamen Konzept-Knoten,
nicht an einer Episode-zu-Episode-Kante. ``erwaehnt`` verankert dabei bevorzugt am KONZEPT
(dem Wikidata-Qid, ``sources.prominentes_konzept``), nicht an der bloßen Wortform -- so
finden sich zwei Erwähnungen auch über Synonyme oder Flexionsformen hinweg ("Fahrrad" und
"Fahrräder" treffen sich am selben Konzept), nicht nur bei exakt gleicher Schreibung. Nur wenn
ein Wort keinem Konzept zugeordnet ist (bloß eine DBnary-Glosse ohne Wikidata-Anker), bleibt
die Lexem-Kante (``Begriff@de``) die Rückfalloption. Der Abruf (``verwandte_episoden``) ist
eine deterministische Graph-Traversierung nach dem Vorbild der Aktivierungsausbreitung
(Collins & Loftus 1975): Begriffe der Frage auflösen -> erwaehnt-Kanten rückwärts folgen ->
nach Aktualität ordnen. Kein Embedding-Index -- der wird erst gebaut, wenn das
Episoden-Volumen ihn rechtfertigt (self-calibration-no-presets).

Alle vier Kanten einer Episode teilen dieselbe Quelle: eine explizite "Merke dir: ..." ist
voll vertraut (``source="ronny"``), eine vom Deuter beiläufig bemerkte Aussage ist gedeckelt
(``source="model:deuter"``, automatisch durch den bestehenden Modell-Vertrauensdeckel) --
dieselbe zweistufige Tarierung wie in der vorigen (flachen) Fassung, jetzt nur netzwerkfähig.
"""
from __future__ import annotations

import re
import time
import uuid

from genus import sources

EPISODE_PREFIX = "erinnerung:"
INHALT = "inhalt"
VON = "von"
AM = "am"
ERWAEHNT = "erwaehnt"   # ASCII, wie jedes andere Prädikat in diesem Graphen (is_a, notiz, ...)

STATEMENT_SOURCE = "model:deuter"   # unverändert: eine unaufgefordert bemerkte Aussage
HUMAN_SOURCE = "ronny"              # heutiger persönliche Kern hat genau einen Owner
_WORD = re.compile(r"[\wäöüÄÖÜß]+", re.UNICODE)
_MIN_WORTLAENGE = 4   # kürzere Wörter sind zu generisch, um einen Begriff zu verankern
# Grobe, deterministische Endungs-Toleranz für deutsche Substantiv-Flexion (Plural/Kasus) --
# kein Morphologie-Analysator, nur ein paar Kandidaten-Stämme; ein Stamm zählt nur, wenn er
# selbst ein bekanntes Lexem ist (``_known`` entscheidet, nicht diese Liste). Ohne das trifft
# "Hunde" nie auf "Hund@de" -- live gefunden (2026-07-03), fehlgeschlagen an genau dem Beispiel,
# das den Anlass für diese Verschärfung gab.
_ENDUNGEN: tuple[str, ...] = ("nen", "en", "er", "es", "n", "e", "s")


def _neue_id() -> str:
    """Ein zufälliger, kollisionsfreier Bezeichner -- live gefunden (2026-07-03):
    ``time.time_ns()`` hat auf diesem System eine viel gröbere tatsächliche Auflösung als
    Nanosekunden (fünf Aufrufe hintereinander gaben denselben Wert zurück), zwei schnell
    hintereinander erzeugte Episoden hätten also kollidiert. Die Reihenfolge (für den Abruf)
    kommt NICHT aus der Id, sondern aus der ohnehin vorhandenen, echten Einfüge-Reihenfolge
    der Projektion (``relation_projection.id`` -- siehe ``_episode``/``verwandte_episoden``)."""
    return f"{EPISODE_PREFIX}{uuid.uuid4().hex}"


def _kandidaten(tok: str) -> list[str]:
    """Alle Wortformen, die für ``tok`` als bekanntes Lexem infrage kommen: as-is,
    großgeschrieben, und (nur falls beides nicht bekannt ist) mit gängigen deutschen
    Flexionsendungen abgeschnitten, je wieder in beiden Schreibweisen."""
    formen = [tok, tok[:1].upper() + tok[1:]]
    for ende in _ENDUNGEN:
        if tok.endswith(ende) and len(tok) - len(ende) >= _MIN_WORTLAENGE:
            stamm = tok[: -len(ende)]
            formen.append(stamm)
            formen.append(stamm[:1].upper() + stamm[1:])
    return formen


def _erwaehnte_anker(conn, text: str) -> list[str]:
    """Welche Graph-Knoten verankern ``text``? Stärker als reiner Wortabgleich: jedes
    erkannte Lexem wird, wenn möglich, bis zu seinem KONZEPT aufgelöst
    (``sources.prominentes_konzept``, die geteilte grounded-zuerst-Regel) -- so treffen
    sich zwei Erwähnungen desselben Begriffs am Konzept-Knoten (z.B. der Wikidata-Qid),
    auch wenn ein Synonym oder eine andere Flexionsform verwendet wurde, statt nur an
    einer exakten Wortform. Ist kein Konzept bekannt (nur eine DBnary-Glosse ohne
    Wikidata-Anker), bleibt die Lexem-Kante (``Form@de``) die Rückfalloption -- exakt
    das bisherige Verhalten. (Phase 0 der Ziel-Architektur: die frühere Kopplung an
    Companion-Interna ist aufgelöst, das Geteilte wohnt jetzt in ``sources``.)"""
    anker: list[str] = []
    gesehen: set[str] = set()
    for tok in _WORD.findall(text):
        if len(tok) < _MIN_WORTLAENGE:
            continue
        for form in _kandidaten(tok):
            if not sources.bekanntes_wort(conn, form):
                continue
            ziel = sources.prominentes_konzept(conn, form) or f"{form}@de"
            if ziel not in gesehen:
                anker.append(ziel)
                gesehen.add(ziel)
            break
    return anker


def merke(conn, inhalt: str, quelle: str = "ronny", datum: str | None = None) -> str:
    """Eine neue Episode -- vier Kanten, dieselbe Quelle auf allen. ``erwaehnt`` wird
    automatisch aus dem Inhalt aufgelöst (bekannte Begriffe im Text). Gibt die neue Episode-Id
    zurück."""
    from genus import reactors

    eid = _neue_id()
    heute = datum or time.strftime("%Y-%m-%d")
    reactors.observe_relation(conn, eid, INHALT, inhalt, quelle)
    reactors.observe_relation(conn, eid, VON, quelle, quelle)
    reactors.observe_relation(conn, eid, AM, heute, quelle)
    for anker in _erwaehnte_anker(conn, inhalt):
        reactors.observe_relation(conn, eid, ERWAEHNT, anker, quelle)
    return eid


def _alle_episode_ids(conn) -> list[str]:
    """Jede Episode-Id, älteste zuerst -- über die eigene ``id``-Spalte der Projektion
    sortiert (Einfüge-Reihenfolge), nicht alphabetisch (``sources.relations`` würde nach
    Objekt sortieren und die zeitliche Reihenfolge stillschweigend durcheinanderwürfeln --
    derselbe Fund, der schon die alten Notizen betraf)."""
    rows = conn.execute(
        "SELECT DISTINCT subject FROM relation_projection WHERE subject LIKE ? AND predicate = ? ORDER BY id",
        (f"{EPISODE_PREFIX}%", INHALT),
    ).fetchall()
    return [r["subject"] for r in rows]


def _episode(conn, eid: str) -> dict:
    # die echte Einfüge-Reihenfolge kommt aus der Projektion selbst (``id``-Spalte), nicht
    # aus der Episode-Id (ein zufälliger Bezeichner, siehe _neue_id) -- so bleibt "neueste
    # zuerst" korrekt, egal wie die Uhr des Systems tickt
    reihe = conn.execute(
        "SELECT id FROM relation_projection WHERE subject = ? AND predicate = ? LIMIT 1",
        (eid, INHALT),
    ).fetchone()
    inhalt = sources.relations(conn, subject=eid, predicate=INHALT)
    von = sources.relations(conn, subject=eid, predicate=VON)
    am = sources.relations(conn, subject=eid, predicate=AM)
    erwaehnt = sources.relations(conn, subject=eid, predicate=ERWAEHNT)
    return {
        "id": eid,
        "_reihenfolge": reihe["id"] if reihe else 0,
        "inhalt": inhalt[0]["object"] if inhalt else "",
        "quelle": von[0]["object"] if von else (inhalt[0]["source"] if inhalt else ""),
        "am": am[0]["object"] if am else "",
        "erwaehnt": [r["object"] for r in erwaehnt],
    }


def episoden(conn) -> list[dict]:
    """Alle Episoden, älteste zuerst, jede als volles Dict (id/inhalt/quelle/am/erwaehnt)."""
    return [_episode(conn, eid) for eid in _alle_episode_ids(conn)]


def bestaetigte_episoden(conn) -> list[str]:
    """Inhalte der Episoden mit menschlicher Quelle (voll vertraut), älteste zuerst."""
    return [e["inhalt"] for e in episoden(conn) if e["quelle"] == HUMAN_SOURCE]


def vermutete_episoden(conn) -> list[str]:
    """Vom Deuter beiläufig bemerkte Episoden, älteste zuerst.

    Historische ``model:nacht``-Verdichtungen sind Tagesmuster, keine Aussagen der Person und
    deshalb kein persönliches Erinnerungswissen. Sie bleiben im unveränderlichen Ledger
    auditierbar, werden aber weder hier noch ungefragt als Nutzererinnerung ausgegeben.
    """
    return [e["inhalt"] for e in episoden(conn)
            if e["quelle"].startswith(sources.MODEL_SOURCE_PREFIX)
            and e["quelle"] != "model:nacht"]


def verwandte_episoden(conn, frage: str, begrenzt: int = 3) -> list[dict]:
    """Welche Episoden erwähnen einen Begriff, der auch in ``frage``
    vorkommt? Deterministische Aktivierungsausbreitung (Collins & Loftus 1975) -- kein
    Embedding, keine Ähnlichkeit, nur echte gemeinsame Graph-Knoten. Neueste zuerst, auf
    ``begrenzt`` Treffer gekappt, damit eine Antwort nicht mit Vergangenem überladen wird."""
    ziel_objekte = set(_erwaehnte_anker(conn, frage))
    if not ziel_objekte:
        return []
    treffer: dict[str, dict] = {}
    for obj in ziel_objekte:
        for r in sources.relations(conn, predicate=ERWAEHNT, object=obj):
            eid = r["subject"]
            if eid not in treffer:
                treffer[eid] = _episode(conn, eid)
    geordnet = sorted(treffer.values(), key=lambda e: e["_reihenfolge"], reverse=True)
    return geordnet[:begrenzt]


def erwaehnter_bezug(conn, frage: str) -> dict | None:
    """Der EINE Nebenbei-würdige, *menschlich bestätigte* Treffer zu ``frage``.

    Unaufgefordertes Erinnern ist eine Oberflächen- und Vertrauensentscheidung, nicht bloß
    semantische Nähe: Modellbeobachtungen und Nacht-Aggregate dürfen bei explizitem Abruf
    prüfbar bleiben, aber nie eine unabhängige Antwort kapern. ``None`` ohne bestätigten Treffer.
    """
    treffer = verwandte_episoden(conn, frage, begrenzt=10)
    bestaetigt = [e for e in treffer if e["quelle"] == HUMAN_SOURCE]
    if not bestaetigt:
        return None
    return {"inhalt": bestaetigt[0]["inhalt"], "bestaetigt": True}


def migriere_notizen(conn) -> int:
    """Einmalige, sauber nachvollziehbare Migration: die alten flachen Notizen
    (``genus:notizen -notiz-> "<Text>"``) werden in echte, vernetzte Episoden überführt und
    danach zurückgenommen (kein Duplikat, kein stiller Doppel-Stand). Nutzt den ECHTEN
    Zeitstempel aus der Projektion (``created_at``), nicht ein Migrations-Datum -- eine
    migrierte Episode bleibt ehrlich auf ihrem ursprünglichen Tag datiert. Idempotent: ein
    zweiter Lauf findet keine ``genus:notizen``-Kanten mehr und tut nichts."""
    from genus import reactors

    rows = conn.execute(
        "SELECT object, source, created_at FROM relation_projection "
        "WHERE subject = 'genus:notizen' AND predicate = 'notiz' ORDER BY id"
    ).fetchall()
    for row in rows:
        datum = (row["created_at"] or "")[:10] or None
        merke(conn, row["object"], quelle=row["source"], datum=datum)
        reactors.retract_relation(
            conn, "genus:notizen", "notiz", row["object"], source=row["source"],
            reason="Migration auf Episoden (docs/design/MEMORY.md: Wie eine Episode entsteht)",
        )
    return len(rows)
