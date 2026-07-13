"""Der ANTWORT-WÜRFEL (Ronny, 2026-07-04: „bau den antwort-würfel mit der stimme-anweisung") --
die Zwicky-Symmetrie an der Membran: der Verstehens-Würfel zerlegt, was REINKOMMT, dieser
Würfel setzt zusammen, was RAUSGEHT.

Zwickys vier Schritte, auf die Antwort angewandt:
(1) unabhängige Parameter: der KERN (Fakten + Ehrlichkeits-Hinweise, unwählbar -- die
    Leitplanke in Kasten-Form), der WORTLAUT (wörtlich | Stimme-Umformung), die Achsen der
    Persönlichkeit (Wärme, Umfang, Humor, Neugier) und das BEIWERK (Notiz-Einwebung,
    Rückfrage, nichts);
(2) die Werte je Achse sind die geordneten Stufen aus ``persoenlichkeit.MERKMALE``;
(3) jede Antwort IST eine Belegung dieses Kastens;
(4) KREUZ-KONSISTENZ zentral statt verstreut: knapp ⇒ kein Beiwerk (hier); wortlautfest ⇒
    keine Stimme (lebt strukturell in der Werkzeug-Spec, ``werkzeug.stimme_geeignet`` --
    schon EIN Ort, bleibt dort); die Rollen-Pins (Wache ⇒ nüchtern) leben im Code der
    Persönlichkeit (Wesens-Schutz, nie Daten).

Die WAHL der Zelle ist immer deterministisch (Register aus dem Graphen + Pins) -- kein
Modell wählt je eine Achse. Das Modell (die Stimme) formuliert nur INNERHALB der gewählten
Zelle: die :func:`anweisung` ist reine DATEN über die Membran (derselbe Weg wie die
GBNF-Grenze des Deuters), die Anker-Prüfung der Stimme bleibt die Leine. Ohne Modell zeigt
sich die Persönlichkeit ehrlich nur an den deterministischen Stellen (Floskel-Varianten,
Beiwerk, Morgen) -- Umformulieren ohne Modell wäre Erfindung.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace

from genus import persoenlichkeit


_RESOLUTIONS = frozenset({"answered", "understood_unknown"})
_QID = re.compile(r"^Q(?:\d+|_[A-Za-z0-9_-]+)$")
_QID_MIT_LABEL = re.compile(r"^Q[^\s]*\s*\((.+)\)$")


@dataclass(frozen=True, slots=True)
class Evidence:
    """Eine konkrete, unveränderte Belegkante hinter einem :class:`Claim`.

    ``trust`` ist die beim Lesen wirksame Quellen-Verlässlichkeit. Sie bleibt ``None``, wenn
    der vorgelagerte Ergebnisvertrag nur die Quelle, aber keinen Einzelwert mitliefert.
    """

    subject: str
    predicate: str
    object: str
    source: str
    trust: float | None = None

    def __post_init__(self) -> None:
        if not all(isinstance(wert, str) and wert.strip() for wert in (
            self.subject, self.predicate, self.object, self.source,
        )):
            raise ValueError("Evidence braucht Subjekt, Prädikat, Objekt und Quelle.")
        if self.trust is not None and not 0.0 <= self.trust <= 1.0:
            raise ValueError("Evidence.trust muss zwischen 0 und 1 liegen.")


@dataclass(frozen=True, slots=True)
class Claim:
    """Eine sprechbare Tatsachenbehauptung samt Belegen und Lesekonfidenz."""

    subject: str
    predicate: str
    object: str
    confidence: float | None = None
    evidence: tuple[Evidence, ...] = ()
    derived: bool = False

    def __post_init__(self) -> None:
        if not all(isinstance(wert, str) and wert.strip() for wert in (
            self.subject, self.predicate, self.object,
        )):
            raise ValueError("Claim braucht Subjekt, Prädikat und Objekt.")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Claim.confidence muss zwischen 0 und 1 liegen.")


@dataclass(frozen=True, slots=True)
class AnswerDraft:
    """Strukturierter Antwortentwurf vor jeder sprachlichen Darstellung.

    ``fallback_text`` ist der bereits bewährte deterministische Satz. Der Renderer darf nur
    Claims neu ordnen und rahmen; verletzt sein Ergebnis einen Anker oder den gerichteten
    ``verbatim_core``, fällt es ohne Ausnahme auf diesen Text zurück.

    ``understood_unknown`` trägt absichtlich *keine* Claims: ein fehlender Graphpfad ist im
    offenen Wissensmodell kein negativer Fakt.
    """

    kind: str
    resolution: str
    focus: tuple[str, str, str] | None
    claims: tuple[Claim, ...]
    fallback_text: str
    anchors: tuple[str, ...] = ()
    verbatim_core: str | None = None
    reading_source: str = "deterministic"
    supplements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("AnswerDraft.kind darf nicht leer sein.")
        if self.resolution not in _RESOLUTIONS:
            raise ValueError(f"Unbekannte AnswerDraft.resolution: {self.resolution!r}")
        if not self.fallback_text.strip():
            raise ValueError("AnswerDraft.fallback_text darf nicht leer sein.")
        if not self.reading_source.strip():
            raise ValueError("AnswerDraft.reading_source darf nicht leer sein.")
        if self.resolution == "answered" and not self.claims:
            raise ValueError("Eine beantwortete Draft braucht mindestens einen Claim.")
        if self.resolution == "understood_unknown" and self.claims:
            raise ValueError("understood_unknown darf keinen negativen Claim vortäuschen.")
        if any(not isinstance(anker, str) or not anker.strip() for anker in self.anchors):
            raise ValueError("AnswerDraft.anchors dürfen nicht leer sein.")
        if any(not isinstance(text, str) or not text.strip() for text in self.supplements):
            raise ValueError("AnswerDraft.supplements dürfen nicht leer sein.")


@dataclass(frozen=True, slots=True)
class DialogueFrame:
    """Der kleine, datensparsame Gesprächsrahmen für genau eine Antwort.

    Persönlicher Rohtext und die vorige Antwort gehören nicht hinein. Meta-Zellen lösen diese
    vorher; der Renderer sieht nur Absicht, strukturelle Ankerkontinuität und die
    deterministische Würfel-Belegung.
    """

    intent: str
    waerme: str
    knappheit: str
    allow_note: bool
    allow_followup: bool
    is_followup: bool = False
    continues_anchor: bool = False
    previous_response_id: int | None = None

    def __post_init__(self) -> None:
        if not self.intent.strip():
            raise ValueError("DialogueFrame.intent darf nicht leer sein.")
        if (self.previous_response_id is not None
                and (isinstance(self.previous_response_id, bool)
                     or not isinstance(self.previous_response_id, int)
                     or self.previous_response_id <= 0)):
            raise ValueError("DialogueFrame.previous_response_id muss eine positive ID sein.")


class AnswerText(str):
    """Ein vollständig kompatibler ``str``, der optional seinen Entwurf mitträgt.

    Bestehende Aufrufer können vergleichen, suchen, verbinden und serialisieren wie bisher.
    Der neue Antwortpfad kann zusätzlich ``text.draft`` lesen, solange der Wert noch nicht von
    einem fremden String-Operator bewusst zu einem gewöhnlichen ``str`` verdichtet wurde.
    """

    draft: AnswerDraft | None

    def __new__(cls, text: str, draft: AnswerDraft | None = None):
        obj = super().__new__(cls, text)
        obj.draft = draft
        return obj


def dialograhmen(
    question: str,
    *,
    intent: str,
    belegung: Mapping[str, object],
    anchor_question: str | None = None,
    is_followup: bool = False,
    previous_response_id: int | None = None,
) -> DialogueFrame:
    """Verdichtet Rohfragen lokal; der zurückgegebene Renderer-Rahmen enthält keinen Text."""
    anchor = anchor_question or question
    if not question.strip() or not anchor.strip():
        raise ValueError("dialograhmen braucht Frage und Ankerfrage.")
    return DialogueFrame(
        intent=intent,
        waerme=str(belegung.get("waerme") or "neutral"),
        knappheit=str(belegung.get("knappheit") or "mittel"),
        allow_note=bool(belegung.get("beiwerk_notiz", False)),
        allow_followup=bool(belegung.get("beiwerk_rueckfrage", False)),
        is_followup=is_followup,
        continues_anchor=anchor != question,
        previous_response_id=previous_response_id,
    )


def _konfidenz(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    wert = float(value)
    return wert if 0.0 <= wert <= 1.0 else None


def _evidence(rows) -> tuple[Evidence, ...]:
    belege: list[Evidence] = []
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        source = str(row.get("source") or "").strip()
        subject = str(row.get("subject") or "").strip()
        predicate = str(row.get("predicate") or "").strip()
        object_ = str(row.get("object") or "").strip()
        if not all((source, subject, predicate, object_)):
            continue
        belege.append(Evidence(
            subject=subject,
            predicate=predicate,
            object=object_,
            source=source,
            trust=_konfidenz(row.get("trust")),
        ))
    return tuple(belege)


def _sprechbarer_begriff(value) -> str | None:
    text = str(value or "").strip()
    match = _QID_MIT_LABEL.match(text)
    if match:
        return match.group(1).strip() or None
    if not text or _QID.fullmatch(text):
        return None
    return text


def entwurf_definition(
    result: Mapping[str, object],
    fallback_text: str,
    *,
    reading_source: str = "deterministic",
) -> AnswerDraft:
    """Hebt das vorhandene Ergebnis von ``auskunft.answer`` verlustfrei in einen Draft.

    Die Fabrik fragt keine Datenbank ab. Sie verbraucht nur den Ergebnisvertrag; ältere
    Ergebnisdicts ohne die additiven Evidence-Felder bleiben gültig und tragen dann ehrlich
    Claims ohne behauptete Einzelprovenienz.
    """
    word = str(result.get("word") or result.get("label") or "").strip()
    if not result.get("found") or not word:
        raise ValueError("entwurf_definition braucht ein gefundenes Wort.")

    claims: list[Claim] = []
    meanings = result.get("spoken_meaning") or result.get("meaning") or ()
    if isinstance(meanings, str):
        meaning = meanings.strip()
    else:
        meaning = str(meanings[0]).strip() if meanings else ""
    if meaning:
        claims.append(Claim(
            subject=word,
            predicate="defined_as",
            object=meaning,
            confidence=_konfidenz(result.get("meaning_confidence")),
            evidence=_evidence(result.get("meaning_evidence")),
        ))

    pos_de = {"noun": "Substantiv", "verb": "Verb", "adjective": "Adjektiv",
              "adverb": "Adverb"}
    for pos in result.get("pos") or ():
        label = pos_de.get(str(pos), str(pos)).strip()
        if label:
            claims.append(Claim(subject=word, predicate="part_of_speech", object=label))

    for form in result.get("languages") or ():
        label = str(form).strip()
        if label:
            claims.append(Claim(subject=word, predicate="other_language_form", object=label))

    belegte_eltern: set[str] = set()
    for relation in result.get("is_a_evidence") or ():
        if not isinstance(relation, Mapping):
            continue
        label = _sprechbarer_begriff(relation.get("label") or relation.get("object"))
        if label is None or label in belegte_eltern:
            continue
        quellzeilen = []
        for source in relation.get("sources") or ():
            if not isinstance(source, Mapping):
                continue
            quellzeilen.append({
                "subject": relation.get("subject"),
                "predicate": relation.get("predicate") or "is_a",
                "object": relation.get("object"),
                "source": source.get("source"),
                "trust": source.get("trust"),
            })
        claims.append(Claim(
            subject=word,
            predicate="is_a",
            object=label,
            confidence=_konfidenz(relation.get("confidence")),
            evidence=_evidence(quellzeilen),
        ))
        belegte_eltern.add(label)

    for parent in result.get("is_a") or ():
        label = _sprechbarer_begriff(parent)
        if label is None or label in belegte_eltern:
            continue
        claims.append(Claim(subject=word, predicate="is_a", object=label))
        belegte_eltern.add(label)

    substantive = any(c.predicate in {"defined_as", "is_a"} for c in claims)
    if not substantive:
        claims.clear()  # POS allein ist keine beantwortete Definitionsfrage.
    resolution = "answered" if substantive else "understood_unknown"
    erster_elternclaim = next((c for c in claims if c.predicate == "is_a"), None)
    focus = ((word, "defined_as", meaning) if meaning else
             ((word, "is_a", erster_elternclaim.object) if erster_elternclaim else None))
    supplements: tuple[str, ...] = ()
    try:
        from genus.auskunft import narrate

        basis = narrate(dict(result))
        if fallback_text.startswith(basis):
            rest = fallback_text[len(basis):].strip()
            if rest:
                supplements = (rest,)
    except (KeyError, TypeError, ValueError):
        pass
    return AnswerDraft(
        kind="definition",
        resolution=resolution,
        focus=focus,
        claims=tuple(claims),
        fallback_text=fallback_text,
        anchors=(word,),
        reading_source=reading_source,
        supplements=supplements,
    )


def entwurf_beziehung(
    result: Mapping[str, object],
    fallback_text: str,
    *,
    predicate: str = "is_a",
    reading_source: str = "deterministic",
) -> AnswerDraft:
    """Hebt ein aufgelöstes Beziehungs-Ergebnis samt Herleitung in einen Draft."""
    subject = str(result.get("subject") or "").strip()
    object_ = str(result.get("object") or "").strip()
    if not result.get("relational") or not subject or not object_:
        raise ValueError("entwurf_beziehung braucht eine aufgelöste Beziehung.")
    if not predicate.strip():
        raise ValueError("entwurf_beziehung braucht ein Prädikat.")

    verdict = str(result.get("verdict") or "")
    claims: tuple[Claim, ...] = ()
    core = None
    if verdict == "yes":
        path = _evidence(result.get("chain"))
        claims = (Claim(
            subject=subject,
            predicate=predicate,
            object=object_,
            confidence=_konfidenz(result.get("trust")),
            evidence=path,
            derived=True,
        ),)
        if predicate == "is_a":
            core = f"»{subject}« zählt zu »{object_}«"

    return AnswerDraft(
        kind="beziehung",
        resolution="answered" if claims else "understood_unknown",
        focus=(subject, predicate, object_),
        claims=claims,
        fallback_text=fallback_text,
        anchors=(subject, object_),
        verbatim_core=core,
        reading_source=reading_source,
    )


def _join_de(teile: list[str]) -> str:
    if len(teile) <= 1:
        return "".join(teile)
    return ", ".join(teile[:-1]) + " und " + teile[-1]


def _quellen(claims: tuple[Claim, ...]) -> list[str]:
    return sorted({beleg.source for claim in claims for beleg in claim.evidence})


def _rendere_definition(draft: AnswerDraft, frame: DialogueFrame) -> str:
    if draft.resolution != "answered":
        return draft.fallback_text
    bedeutung = next((c for c in draft.claims if c.predicate == "defined_as"), None)
    if bedeutung is None:
        return draft.fallback_text
    eltern = [c for c in draft.claims if c.predicate == "is_a"]
    wortarten = [c.object for c in draft.claims if c.predicate == "part_of_speech"]
    sprachen = [c.object for c in draft.claims if c.predicate == "other_language_form"]
    subject = draft.anchors[0]
    kopf = f"»{subject}«"
    if wortarten:
        kopf += f" ({_join_de(wortarten)})"
    saetze: list[str] = []
    if bedeutung is not None:
        kern = bedeutung.object.strip().rstrip(".")
        saetze.append(f"{kopf} bedeutet hier: {kern}.")
    elif eltern:
        saetze.append(f"{kopf} zählt zu »{eltern[0].object}«.")

    if eltern:
        namen = _join_de([f"»{claim.object}«" for claim in eltern])
        saetze.append(f"Dabei zählt »{subject}« zu {namen}.")

    if bedeutung.confidence is not None and bedeutung.confidence < 0.5:
        saetze.append("Bei dieser Bedeutung bin ich noch vorsichtig: Sie ist erst schwach belegt.")
    elif len({e.source for e in bedeutung.evidence}) >= 2:
        saetze.append("Diese Bedeutung ist mehrfach unabhängig belegt.")

    quellen = _quellen(draft.claims)
    if frame.knappheit == "ausfuehrlich" and quellen:
        saetze.append(f"Die Belege stammen aus {_join_de(quellen)}.")
    if sprachen:
        saetze.append(f"In anderen Sprachen: {', '.join(f'»{form}«' for form in sprachen[:4])}.")
    saetze.extend(draft.supplements)
    return " ".join(saetze) or draft.fallback_text


def _rendere_beziehung(draft: AnswerDraft, frame: DialogueFrame) -> str:
    if draft.focus is None:
        return draft.fallback_text
    subject, predicate, object_ = draft.focus
    if draft.resolution == "understood_unknown":
        art = "is_a-Verbindung" if predicate == "is_a" else f"{predicate}-Verbindung"
        return (f"Eine {art} von »{subject}« zu »{object_}« finde ich derzeit nicht. "
                f"Das heißt: unbekannt, nicht widerlegt.")

    claim = draft.claims[0]
    if predicate != "is_a" or draft.verbatim_core is None:
        return draft.fallback_text
    if sum(evidence.predicate == "is_a" for evidence in claim.evidence) > 1:
        return draft.fallback_text
    einstieg = "Ja —" if frame.waerme in ("warm", "herzlich") else "Ja."
    saetze = [f"{einstieg} {draft.verbatim_core}."]
    if claim.confidence is not None and claim.confidence < 0.5:
        saetze.append(
            f"Da bin ich noch unsicher (Vertrauen {claim.confidence:.2f}): "
            "Mein Wissensnetz stützt diese Verbindung bisher nur schwach."
        )
    quellen = _quellen(draft.claims)
    if frame.knappheit == "ausfuehrlich" and quellen:
        saetze.append(f"Die Herleitung stützt sich auf {_join_de(quellen)}.")
    return " ".join(saetze)


def _anker_in_reihenfolge(text: str, anchors: tuple[str, ...]) -> bool:
    position = 0
    for anchor in anchors:
        fund = text.find(anchor, position)
        if fund < 0:
            return False
        position = fund + len(anchor)
    return True


def _render_treu(draft: AnswerDraft, text: str) -> bool:
    if not text.strip() or not _anker_in_reihenfolge(text, draft.anchors):
        return False
    if draft.verbatim_core is not None and draft.verbatim_core not in text:
        return False
    if draft.resolution == "understood_unknown" and "unbekannt" not in text.casefold():
        return False
    if any(claim.object not in text for claim in draft.claims):
        return False
    if any(supplement not in text for supplement in draft.supplements):
        return False
    for claim in draft.claims:
        if (draft.kind == "beziehung" and claim.confidence is not None
                and claim.confidence < 0.5):
            if ("unsicher" not in text and "schwach" not in text) or (
                    f"{claim.confidence:.2f}" not in text):
                return False
        if claim.predicate == "defined_as":
            quellen = {e.source for e in claim.evidence}
            if claim.confidence is not None and claim.confidence < 0.5:
                if "schwach belegt" not in text:
                    return False
            elif len(quellen) >= 2 and "mehrfach unabhängig belegt" not in text:
                return False
    return True


def rendere(draft: AnswerDraft, frame: DialogueFrame) -> AnswerText:
    """Rendert deterministisch und fällt bei jedem Treuebruch auf den bewährten Text zurück."""
    try:
        if draft.kind == "definition":
            text = _rendere_definition(draft, frame)
        elif draft.kind == "beziehung":
            text = _rendere_beziehung(draft, frame)
        else:
            text = draft.fallback_text
    except Exception:
        text = draft.fallback_text
    if not _render_treu(draft, text):
        text = draft.fallback_text
    return AnswerText(text, draft)


def wende_renderer_an(
    conn,
    text: str,
    *,
    question: str,
    anchor_question: str,
    intent: str,
    renderer=None,
    reading_source: str = "deterministic",
    previous_response_id: int | None = None,
    is_followup: bool = False,
) -> tuple[str, AnswerDraft | None]:
    """Rendert einen mitgeführten Draft; gewöhnliche Strings bleiben unverändert.

    Der Aufrufer liest den Draft damit vor jeder String-Komposition. Die Herkunft der
    aktuellen Lesart wird in die unveränderliche Kopie übernommen; Rohtext oder die vorige
    Antwort werden nicht in den Draft geschrieben.
    """
    draft = getattr(text, "draft", None)
    if not isinstance(draft, AnswerDraft):
        return text, None
    if draft.reading_source != reading_source:
        draft = replace(draft, reading_source=reading_source)
    if renderer is None:
        return AnswerText(text, draft), draft
    frame = dialograhmen(
        question,
        intent=intent,
        belegung=belegung(conn, "plausch"),
        anchor_question=anchor_question,
        is_followup=is_followup,
        previous_response_id=previous_response_id,
    )
    rendered = renderer(draft, frame)
    return AnswerText(str(rendered), draft), draft


def komponiere(teile: list[str], marker: tuple[str, ...] = ()) -> str:
    """Verbindet Teilantworten und dedupliziert reine Transparenzmarker."""
    text = " ".join(t for t in teile if t)
    for kennung in marker:
        anzahl = text.count(kennung)
        if anzahl > 1:
            text = text.replace(kennung, "", anzahl - 1)
    return text


def gesamt_outcome(outcomes: list[str]) -> str:
    """Verdichtet Segment-Outcomes konservativ zur Wirkung der ganzen Antwort."""
    for outcome in ("fallback", "invalid_slots", "understood_unknown"):
        if outcome in outcomes:
            return outcome
    return "answered"


def belegung(conn, rolle: str = "plausch", nutzer: str = persoenlichkeit.NUTZER) -> dict:
    """Die deterministische Belegung des Antwort-Würfels: das wirksame Register der Rolle,
    plus die Kreuz-Konsistenz-Folgen (Zwickys Schritt 4) als explizite Felder -- die eine
    Stelle, an der „knapp ⇒ kein Beiwerk" gilt, statt in jedem Verbraucher einzeln."""
    reg = persoenlichkeit.register(conn, rolle, nutzer)
    knapp = reg["knappheit"] == "knapp"
    reg["beiwerk_notiz"] = not knapp
    reg["beiwerk_rueckfrage"] = reg["neugier"] == "ja" and not knapp
    return reg


_TON = {
    "nuechtern": "sachlich und nüchtern",
    "warm": "freundlich und warm",
    "herzlich": "herzlich und zugewandt",
}


def anweisung(bel: dict) -> str | None:
    """Die Stil-Anweisung an die Stimme, aus der Belegung abgeleitet -- reine Daten für
    die Membran; ``None`` bei neutraler Belegung (die Stimme läuft dann wie bisher).

    EHRLICH BEGRENZT: nur Ton (Wärme) und Straffen (knapp). „ausführlich" kann die Stimme
    strukturell nie leisten -- sie fügt NIE hinzu (Anker-Leine), und mehr Worte ohne mehr
    Fakten wären Füllstoff oder Erfindung; mehr Umfang muss aus der ZELLE kommen (mehr
    Inhalt), nicht aus der Stimme. Humor bleibt bewusst draußen (heutiger Verbraucher:
    der Morgen-Schluss) -- ein Witz gehört nie in eine Wissens-Umformulierung."""
    teile = []
    ton = _TON.get(bel.get("waerme", ""))
    if ton:
        teile.append(f"Ton: {ton}.")
    if bel.get("knappheit") == "knapp":
        teile.append("Fasse dich so knapp wie möglich.")
    return " ".join(teile) or None


# Die Floskel-Varianten: reine SPRACHE (kein Fakt), deshalb hier an EINER Stelle statt in
# jedem Handler (Charta §2: keine zweite Wahrheit darüber, wie die Wärme wirkt). Der
# jeweilige Standard (test-verankerter Wortlaut) liegt auf der Saat-Stufe „warm".
FLOSKELN: dict[str, dict[str, str]] = {
    "gruss": {
        "nuechtern": "Hallo.",
        "neutral": "Hallo!",
        "warm": "Hallo! Schön, dass du da bist.",
        "herzlich": "Hallo! Wie schön, dass du da bist!",
    },
    "dank": {
        "nuechtern": "Gern.",
        "neutral": "Gern geschehen.",
        "warm": "Gern geschehen!",
        "herzlich": "Gern geschehen — jederzeit!",
    },
}
_GRUSS_RUECKFRAGE = " Was beschäftigt dich gerade?"
_GRUSS_HINWEIS = " Frag mich etwas, oder sag „was weißt du?“."


def floskel(conn, zelle: str, rolle: str = "plausch", *, mit_beiwerk: bool = True) -> str:
    """Die passende Floskel-Variante zur aktuellen Belegung; der Gruß trägt sein Beiwerk
    (die neugierige Rückfrage bzw. den Einstiegs-Hinweis) gemäß Kreuz-Konsistenz."""
    bel = belegung(conn, rolle)
    text = FLOSKELN[zelle].get(bel["waerme"], FLOSKELN[zelle]["neutral"])
    if zelle == "gruss" and mit_beiwerk:
        text += _GRUSS_RUECKFRAGE if bel["beiwerk_rueckfrage"] else _GRUSS_HINWEIS
    return text


def klaerung_fuer_slots(kind: str, guess: Mapping[str, object]) -> str | None:
    """Eine konkrete Rueckfrage fuer sicher erkannte, aber unvollstaendige Lesarten."""
    if kind != "beziehung":
        return None
    subject = str(guess.get("subject") or "").strip()
    object_ = str(guess.get("object") or "").strip()
    if subject and not object_:
        return (f"Ich habe verstanden, dass es um eine Beziehung mit »{subject}« geht, "
                f"aber mir fehlt das Ziel. Wozu möchtest du »{subject}« in Beziehung setzen?")
    if object_ and not subject:
        return (f"Ich habe das Ziel »{object_}« verstanden, aber mir fehlt der Ausgangspunkt. "
                "Wovon möchtest du die Beziehung prüfen?")
    if not subject and not object_:
        return "Welche beiden Dinge möchtest du miteinander in Beziehung setzen?"
    return None
