"""The companion: ask GENUS about a word and it answers from its own knowledge graph.

Deterministic and model-free in this first slice -- it finds a word GENUS knows in the
question, looks up that word's prominent concept, and reports the concept's meaning (the German
gloss) and its is_a, straight from the graph. So "Was ist ein Hund?" is answered from recorded,
provenanced knowledge, not interpolation. Later slices sharpen it: the edge embedder picks
*which sense* the question means (WSD from context), and a generative voice makes the answer
fluent. Here the knowing + a clean template are enough -- and the whole thing stays glass-box.
"""
from __future__ import annotations

import json
import re

from genus import inference, sources
# Der WELT-SINN (Wetter/News/Uhr) lebt seit der Modularisierung (2026-07-09, Schritt ②)
# eigenständig in :mod:`genus.weltsinn`. Hier re-exportiert, damit ``companion.X`` unveraendert
# weiterlaeuft -- konsolidierung liest ``companion.wetter_kurz``/``news_top``, die Tests
# ``companion._ist_zeit_frage`` usw., und die Dispatch-Zelle ``_zelle_weltfrage`` unten ruft die
# Sinne bei bloßem Namen. Verhaltensgleich, nur woanders zuhause. (weltsinn hat keine
# Modul-Ebene-Importe aus genus -> kein Zyklus.)
from genus.weltsinn import (
    _NEWS_ANTWORT_MARKER,
    _ist_news_frage,
    _ist_zeit_frage,
    _news_bericht,
    _uhrzeit_bericht,
    _wetter_bericht,
    news_top,
    wetter_kurz,
)
# Ebenso die RECHEN-Werkzeuge (Abitur-Analysis) -- seit Schritt ② eigenständig in
# :mod:`genus.rechnen` (das „Ausführen", aus dem der Planer ③ komponiert). Re-exportiert, damit
# die Muster-Dispatch unten (_muster_antwort), werkzeuge_seed.formulierung und die Tests
# unveraendert ``companion.ableitung_frage``/``narrate_*`` lesen. rechnen hat keine
# Modul-Ebene-Importe aus genus -> kein Zyklus.
from genus.rechnen import (
    ableitung_frage,
    extremstellen_frage,
    integral_frage,
    kurvendiskussion_frage,
    narrate_ableitung,
    narrate_extremstellen,
    narrate_integral,
    narrate_kurvendiskussion,
    narrate_stammfunktion,
    stammfunktion_frage,
)
# Und die eigentliche Gesprächs-Schicht -- seit Schritt ③ getrennt: die LESE-GRUNDLAGE
# (:mod:`genus.wortgraph`) und die ANTWORT-WERKZEUGE (:mod:`genus.auskunft`). Hier
# re-exportiert, damit die Dispatch-Zellen/respond_with_deuter sie beim bloßen Namen rufen und
# externe Leser (Tests, werkzeuge_seed) unverändert ``companion.answer`` usw. sehen.
# companion = Orchestrierung, liest beides nach unten -> azyklisch.
from genus.wortgraph import _WORD, _label, _last_known_word, _prominent_concept
from genus.auskunft import (
    _common_terms,
    _erklaerbar_und_eindeutig,
    _gender_term,
    _kausal_zwischen,
    _relate_terms,
    _ursachen_von,
    answer,
    antizipation,
    common,
    gender_question,
    narrate,
    narrate_common,
    narrate_gender,
    narrate_kausal,
    narrate_ort,
    narrate_relation,
    narrate_verwandt,
    ort,
    relate,
    relate_kausal,
    verwandt_frage,
    vertiefung,
)

# Vokabel-bei-Begegnung (Ronny 2026-07-05): der gesprächsnahe Zwilling des Lücken-Detektors --
# statt einer Absicht, die fehlt, ein WORT, das fehlt. Der Kern SPÜRT das unbekannte Wort (rein
# lesend, kein HTTP -- das Erwerben ist Membran-Sache); die Membran (Bot) legt es in die
# Lern-Warteschlange, der Lerner-Daemon holt es beim nächsten Tick VOR den Frequenzlisten.
_BEGEGNETES_WORT = re.compile(r"[A-ZÄÖÜ][A-Za-zäöüß]{3,}")   # großgeschrieben = substantiv-artig
# Häufige großgeschriebene Funktionswörter (Satzanfang) sind keine Vokabeln -- nicht in die
# Schlange, um die Membran-Quelle nicht mit „Was/Wie/Der" zu behelligen. Ein echtes Substantiv
# am Satzanfang („Fernweh überkommt mich") ist NICHT hier und bleibt lernenswert.
_WORT_STOPP = frozenset({
    "was", "wie", "wo", "wann", "warum", "wieso", "weshalb", "wer", "wen", "wem", "wozu",
    "welche", "welcher", "welches", "welchen", "welchem",
    "ist", "sind", "war", "hat", "haben", "kann", "kannst", "kennst", "weißt", "weisst",
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer",
    "und", "oder", "aber", "auch", "noch", "nur", "schon", "nicht", "sehr", "mehr",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "mir", "mich", "dir", "dich",
    "hallo", "danke", "bitte", "übrigens", "also", "gibt",
    # häufige großgeschriebene Imperative am Satzanfang (auch keine Substantive); die
    # selteneren fängt der Lerner ohnehin gnädig ab (nicht auflösbar -> nichts gemerkt).
    "gib", "sag", "mach", "zeig", "erzähl", "erzaehl", "nenn", "hör", "hoer", "schau",
    "lass", "komm", "geh", "denk", "sieh", "guck", "warte", "erklär", "erklaer",
})


def unbekannte_woerter(conn, text: str) -> list[str]:
    """Die (substantiv-artigen) Wörter in ``text``, die GENUS noch nicht kennt -- rein lesend,
    kein HTTP. Großgeschrieben, weil ein Substantiv das ist, was GENUS heute lernt (die
    Vokabel-Listen sind Substantive); häufige Funktionswörter am Satzanfang sind ausgefiltert.
    Reihenerhaltend dedupliziert. Der gesprächsnahe Zwilling der Verstehens-Lücke: was hier
    zurückkommt, hat der Bot im Moment der Begegnung zu lernen -- nicht erst der Nacht-Cron."""
    from genus import sources

    gefunden: list[str] = []
    for tok in dict.fromkeys(_BEGEGNETES_WORT.findall(text)):
        if tok.casefold() in _WORT_STOPP:
            continue
        if not sources.bekanntes_wort(conn, tok):
            gefunden.append(tok)
    return gefunden


# knappe Zustimmung auf ein Anschluss-Angebot -- bewusst ein EXAKT-Satz aus sehr kurzen
# Wendungen (nie eine echte neue Frage als „ja" durchgehen lassen; nur wirksam, wenn ein
# Angebot aussteht, deshalb sind Fehlklassifikationen ohnehin billig)
_ZUSTIMMUNG = frozenset({
    "ja", "jo", "jap", "joa", "ja bitte", "ja gerne", "ja gern", "gerne", "gern",
    "klar", "na klar", "ja klar", "sicher", "unbedingt", "ok", "okay", "mach",
    "mach das", "ja mach", "ja mach das", "erzähl", "erzähl mehr", "erzähl mir mehr",
})


def _ist_zustimmung(text: str) -> bool:
    """Eine knappe Zustimmung auf ein Anschluss-Angebot -- reiner Exakt-Abgleich kurzer
    Wendungen, damit eine echte neue Frage nie als „ja" gilt."""
    return text.strip().casefold().rstrip(" !.") in _ZUSTIMMUNG


# --- Rechenfähigkeit (Abitur-Analysis) ist herausgelöst -> genus/rechnen.py --------------
# Ableitung/Extremstellen/Stammfunktion/Integral/Kurvendiskussion -- als Werkzeuge (das
# „Ausführen", aus dem der Planer ③ komponiert) leben sie seit Schritt ② in :mod:`genus.rechnen`
# und sind oben re-importiert. Die Muster-Dispatch (_muster_antwort) ruft sie beim bloßen Namen;
# werkzeuge_seed und die Tests lesen ``companion.ableitung_frage``/``narrate_*``. Verhaltensgleich.


# --- memory ("Merke dir: ...") -----------------------------------------------------------
#
# Slice 1 of Personen-Gedächtnis was named "person:ronny", but Ronny immediately used it to
# teach GENUS a fact about GENUS ITSELF ("Merk dir dass du GENUS heißt") -- filed under "facts
# about Ronny", read back nonsensically under "Was weißt du über mich?" (his own 😂 in the live
# log said it all). The fix wasn't a patch, it was a correct generalization: this is a general
# NOTEBOOK, not a "things about one person" store -- GENUS doesn't (and, honestly, mostly
# can't) know WHO or WHAT a free-text note is about; it only knows WHO TOLD it.
#
# Storage moved on from a flat, unnetworked relation (Punkt 1 von docs/design/MEMORY.md,
# 2026-07-03: Tulving 1972 -- episodic memory is dated and networked THROUGH shared knowledge,
# not a pile of disconnected strings) to real episodes in :mod:`genus.erinnerung` -- this module
# only does dispatch and phrasing now, the storage/retrieval contract lives there.
#
# Two trust tiers, not a formal Proposal/Review cycle -- reusing a mechanism that's already
# fully built and trusted, not inventing a new one:
#   - quelle="ronny" (explicit "Merke dir: ..."): a HUMAN source, full/uncapped trust, exactly
#     like the teacher-loop. Ronny SAID to remember it -- that IS "enorm wichtig".
#   - quelle="model:deuter" (an unprompted personal STATEMENT the Deuter noticed in ordinary
#     conversation, e.g. an offhand remark with no "merke dir" at all): capped at half the trust
#     seed, automatically, by the SAME model-source cap that already governs every other model
#     contribution (sources.MODEL_SOURCE_PREFIX) -- "GENUS schlägt vor" IS exactly what a
#     capped, unconfirmed source means elsewhere in this graph. Never silently promoted to full
#     trust; saying "Merke dir" for real about the same thing later adds a full-trust entry
#     alongside it (corroboration raises confidence, same as anywhere else in the graph).

_REMEMBER_CUE = re.compile(
    r"^\s*(?:merke?\s+dir|denk\s+dran|notier(?:e)?\s+dir)\s*[:,]?\s*(.+?)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_RECALL_CUES = {
    "was weißt du", "was weisst du",
    "was weißt du über mich", "was weisst du über mich",
    "was weißt du von mir", "was weisst du von mir",
    "was hast du dir gemerkt", "was hast du gemerkt",
    "erzähl mir was du über mich weißt", "erzähl mir was du über mich weisst",
    "kennst du mich",
}


def remember_command(question: str) -> str | None:
    """The fact to remember, if ``question`` is an explicit "merke dir: ..." instruction --
    ``None`` for an ordinary question. Only ever fires on this small, closed set of German cue
    phrases; everything else is left to the normal routing untouched."""
    m = _REMEMBER_CUE.match(question)
    fact = m.group(1).strip() if m else ""
    return fact or None


def is_recall_question(question: str) -> bool:
    """True for a "was weißt du (über mich)?"-style question. EXACT match after normalizing
    (not a substring check) -- a substring cue like "was weißt du" would otherwise also fire
    inside a real question like "was weißt du über Hunde?", hijacking an ordinary word lookup.
    Uses ``.lower()``, not ``.casefold()`` (matching ``is_why_followup``'s convention) --
    casefold would turn German "ß" into "ss" and silently break a "ß"-spelled cue phrase
    (caught live: the "ß" cue never matched its own casefolded question)."""
    q = question.strip().strip("?!.").lower()
    return q in _RECALL_CUES


def narrate_notes(confirmed: list[str], suggested: list[str]) -> str:
    """Tiered honesty, same principle as everywhere else in the companion (known fact > induced
    rule > silence): confirmed notes are stated plainly; suggested (model-noticed, unconfirmed)
    ones are named separately and marked as a guess -- never silently blended together."""
    if not confirmed and not suggested:
        return "Bisher weiß ich noch nichts über dich — sag mir „merke dir: …“, und ich behalte es."
    lines = []
    if confirmed:
        if len(confirmed) == 1:
            lines.append(f"Das Einzige, was ich sicher weiß: {confirmed[0]}")
        else:
            lines.append("Das weiß ich sicher:")
            lines += [f"• {f}" for f in confirmed]
    if suggested:
        lines.append("Das vermute ich außerdem (noch nicht bestätigt):")
        lines += [f"• {f}" for f in suggested]
    return "\n".join(lines)


# --- bestätigte Episoden beiläufig einweben -----------------------------------------------
# Der Graph findet semantische Nähe; die Oberfläche ist strenger: ungefragtes Beiwerk darf nur
# aus einer ausdrücklich menschlich bestätigten Episode stammen (docs/design/MEMORY.md).

def _notiz_bezug(conn, question: str) -> str | None:
    """Bestätigte Episode als kurzes Beiwerk; der Antwort-Würfel darf es unterdrücken."""
    from genus import antwort, erinnerung  # local: keeps companion's import-time surface a leaf otherwise

    if not antwort.belegung(conn, "plausch")["beiwerk_notiz"]:
        return None
    treffer = erinnerung.erwaehnter_bezug(conn, question)
    if treffer is None:
        return None
    return f" (Nebenbei: du hast mir erzählt „{treffer['inhalt']}“.)"


# --- a single shared answer, for any conversational channel -----------------------------
#
# `cli.ask_command` has its own routing (terminal-log formatting, [ASK]/[BLF]/... tags -- left
# untouched, well-tested). `respond` is the same underlying routing order, rendered as plain
# text for a channel where that log-tag style would look odd (e.g. a chat bridge like Telegram).
# Read-only except for one deliberate, explicit exception: "merke dir: ..." (personal memory) --
# every other branch is a pure read, identical data functions, a different voice for a room.
# The stages are factored so the Verstehens-Würfel (respond_with_deuter, below) can reuse them
# in a different order without duplicating their logic.

# Der Chat-Regler der Persönlichkeit -- EINE Implementierung, zwei Türen (Charta §2,
# „keine zweite Wahrheit", gelernt genau an dieser Stelle): die FÄHIGKEIT ist die
# Raster-Zelle „einstellung" (aufforderung-genus, registriertes Werkzeug, schreibt) --
# der Deuter erreicht sie für freie Formulierungen („könntest du dich kürzer fassen?").
# Die EXAKTEN Kommandos („sei knapper") bleiben als deterministische Ritual-Schnellspur,
# dieselbe Zwei-Türen-Logik wie „merke dir:" neben der merken-Zelle. Beide Türen rufen
# _regler_stellen -- eine Wahrheit, ein Bestätigungs-Wortlaut, eine Grenz-Ehrlichkeit.
_REGLER_CUES: dict[str, tuple[str, int]] = {
    "sei knapper": ("knappheit", -1),
    "sei ausführlicher": ("knappheit", +1),
    "sei ausfuehrlicher": ("knappheit", +1),
    "sei wärmer": ("waerme", +1),
    "sei waermer": ("waerme", +1),
    "sei nüchterner": ("waerme", -1),
    "sei nuechterner": ("waerme", -1),
    "mehr humor": ("humor", +1),
    "weniger humor": ("humor", -1),
    "sei neugieriger": ("neugier", +1),
    "sei weniger neugierig": ("neugier", -1),
}

# Freie Formulierungen INNERHALB eines einstellung-Segments (der Deuter hat die Absicht
# schon beurteilt -- hier wird nur noch Achse+Richtung aus der eigenen Klausel gelesen,
# dieselbe Segment-Disziplin wie bei den Sozialgesten). Humor/Neugier brauchen ein
# Richtungswort; mehrdeutige Wünsche fallen ehrlich durch statt zu raten.
_REGLER_WORTE: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("knappheit", -1, ("knapper", "kürzer", "kuerzer", "knapp")),
    ("knappheit", +1, ("ausführlicher", "ausfuehrlicher", "länger", "laenger")),
    ("waerme", +1, ("wärmer", "waermer", "herzlicher")),
    ("waerme", -1, ("nüchterner", "nuechterner", "sachlicher", "kühler", "kuehler")),
)
_REGLER_WENIGER = ("weniger", "keinen", "kein ", "nicht so", "ohne")


def _regler_deute(text: str) -> tuple[str, int] | None:
    """Achse+Richtung aus einer frei formulierten Einstellungs-Klausel -- ``None``, wenn
    nichts oder Mehrdeutiges erkannt wird (dann fragt die Zelle ehrlich nach)."""
    t = text.casefold()
    weniger = any(w in t for w in _REGLER_WENIGER)
    treffer: set[tuple[str, int]] = set()
    for merkmal, richtung, worte in _REGLER_WORTE:
        if any(w in t for w in worte):
            treffer.add((merkmal, richtung))
    if "humor" in t or "witzig" in t or "lustig" in t:
        treffer.add(("humor", -1 if weniger else +1))
    if "neugier" in t:   # deckt neugierig/neugieriger mit ab
        treffer.add(("neugier", -1 if weniger else +1))
    if len(treffer) != 1:
        return None
    return treffer.pop()


def _regler_stellen(conn, merkmal: str, richtung: int) -> str:
    """Die EINE Stell-Implementierung hinter beiden Türen: bewegt die Achse um eine Stufe
    (persoenlichkeit.stelle) und bestätigt nativ; an der Grenze passiert ehrlich nichts."""
    from genus import persoenlichkeit

    res = persoenlichkeit.stelle(conn, merkmal, richtung)
    name = persoenlichkeit.ANZEIGE[merkmal]
    wert = persoenlichkeit.WERT_ANZEIGE.get(res["wert"], res["wert"])
    if res["gestellt"]:
        return (f"Gern — {name} steht jetzt auf „{wert}“. "
                f"(Als Einstellung gemerkt — Quelle: du.)")
    return f"{name} steht schon auf „{wert}“ — weiter geht es in diese Richtung nicht."


def _regler_antwort(conn, question: str) -> str | None:
    """Die Ritual-Tür: erkennt ein EXAKTES Regler-Kommando (satzzeichen-tolerant) --
    ``None``, wenn die Frage kein exaktes Kommando ist (freie Formulierungen gehen den
    Deuter-Weg zur einstellung-Zelle)."""
    cue = _REGLER_CUES.get(question.strip().strip(".!?— ").casefold())
    if cue is None:
        return None
    return _regler_stellen(conn, *cue)


def _ritual_antwort(conn, question: str) -> str | None:
    """The unambiguous rituals -- explicit memory, recall, the personality dial, fixed state
    queries, GENUS's own open questions. Exact/cue matches, deterministic, never model-deuted
    (a clear command needs no interpretation). ``None`` when no ritual claims the question."""
    from genus import erinnerung, query  # local: keeps companion's import-time surface a leaf otherwise

    fact = remember_command(question)
    if fact is not None:
        erinnerung.merke(conn, fact, quelle=erinnerung.HUMAN_SOURCE)
        return f"Gemerkt: „{fact}“"
    if is_recall_question(question):
        return narrate_notes(erinnerung.bestaetigte_episoden(conn), erinnerung.vermutete_episoden(conn))
    regler = _regler_antwort(conn, question)
    if regler is not None:
        return regler
    state = query.ask(conn, question)
    if state.get("kind") != "unknown":
        return state["answer"]
    if inquiries_question(question):
        return narrate_inquiries(conn, open_questions(conn))
    if ziele_question(question):
        return narrate_ziele(conn)
    return None


def _muster_antwort(conn, question: str, bel: dict | None = None) -> tuple[str, str] | None:
    """The fixed-pattern cells (relation/kausal/comparative/gender/derivative) -- self-verifying: a
    pattern only claims the question when its terms actually resolve (in the graph, or -- for
    the derivative cell -- as a valid computable term). Returns ``(text, zelle)`` so a caller
    can record WHICH cell answered; ``None`` otherwise.

    ``bel`` (Antwort-Würfel-Belegung, optional): reicht die Wärme an die relationalen/kausalen
    Narrationen durch (Voice 1, Scheibe 1). Ohne Belegung -- der CLI-nahe :func:`respond` --
    bleibt der nüchterne Wortlaut; die Gesprächs-Einstiege reichen sie durch."""
    rel = relate(conn, question)
    if rel.get("relational"):
        return narrate_relation(conn, rel, bel), "beziehung"
    kau = relate_kausal(conn, question)
    if kau.get("kausal_q"):
        return narrate_kausal(conn, kau, bel), "beziehung"
    com = common(conn, question)
    if com.get("common"):
        return narrate_common(conn, com, bel), "vergleich"
    ort_r = ort(conn, question)
    if ort_r.get("relational"):
        return narrate_ort(conn, ort_r, bel), "ort"
    vw = verwandt_frage(conn, question)
    if vw.get("verwandt_q"):
        return narrate_verwandt(conn, vw, bel), "verwandt"
    gen = gender_question(conn, question)
    if gen.get("gender_q"):
        return narrate_gender(gen), "grammatik"
    ab = ableitung_frage(question)
    if ab.get("berechnung_q"):
        return narrate_ableitung(ab), "berechnen"
    ex = extremstellen_frage(question)
    if ex.get("berechnung_q"):
        return narrate_extremstellen(ex), "berechnen"
    integ = integral_frage(question)
    if integ.get("berechnung_q"):
        return narrate_integral(integ), "berechnen"
    kd = kurvendiskussion_frage(question)
    if kd.get("berechnung_q"):
        return narrate_kurvendiskussion(kd), "berechnen"
    stamm = stammfunktion_frage(question)
    if stamm.get("berechnung_q"):
        return narrate_stammfunktion(stamm), "berechnen"
    return None


def _wort_antwort(conn, question: str, waage=None) -> str | None:
    """The bare word reading -- any known word in the question, answered from its grounding.
    Deliberately the LAST reading in the Würfel order (it is greedy by nature and used to
    shadow better readings when it ran early -- the live bug class of 2026-07-02)."""
    a = answer(conn, question, waage=waage)
    if not a["found"]:
        return None
    text = narrate(a)
    # der Umfang-Verbraucher (Antwort-Würfel): bei „ausführlich" zieht die Antwort MEHR
    # Material aus dem Graphen -- Länge aus Inhalt, nie aus Worten
    from genus import antwort as _antwort

    if _antwort.belegung(conn, "plausch")["knappheit"] == "ausfuehrlich":
        text += "".join(f" {satz}" for satz in vertiefung(conn, a))
    if a.get("concept"):
        text += f" (Mehr Herkunft: „genus concept {a['concept']}\" oder „genus why answer …\".)"
    return text


def respond(conn, question: str, bel: dict | None = None, waage=None) -> str:
    """The full conversational answer to ``question``: remember -> recall -> state ->
    relational -> comparative -> gender -> word -> help, in that order (the personal-memory
    checks run first so they can never be shadowed by a fixed pattern or a known word; the rest
    matches ``cli.ask_command``). Plain text, no CLI tags. Pure deterministic half -- no model,
    and (except the explicit "merke dir") no writes: the Würfel's reading-records happen only
    in ``respond_with_deuter``, the conversational channel.

    ``bel`` (optional): die Antwort-Würfel-Belegung für die warme Stimme (Voice 1) der
    relationalen/kausalen Antworten. Der reine CLI-Weg (``genus ask``) ruft ``narrate_*``
    direkt und bleibt nüchtern; die Gesprächs-Einstiege reichen die Belegung durch.

    ``waage`` (optional, wie ``stimme``/``deuter`` von der Membran injiziert): das Wiege-Organ
    der Formwahl-Kette — es LIEST nur (kein Erzeugungskanal, ``respond`` bleibt schreibfrei);
    ohne Organ entscheiden Gegründetes + eigene Regel allein."""
    text = _ritual_antwort(conn, question)
    if text is not None:
        return text
    muster = _muster_antwort(conn, question, bel)
    if muster is not None:
        return muster[0]
    text = _wort_antwort(conn, question, waage=waage)
    if text is not None:
        return text
    return _UNKNOWN_FALLBACK  # the honest "nothing recognized" help, same fallback as the CLI


# --- GENUS's own open questions ("Was beschäftigt dich?") --------------------------------
#
# The companion is a Gegenüber, not only an Auskunftei: GENUS genuinely has open questions
# (inquiries -- contradictions it can't settle, stability surprises), and here they get a
# German voice. Deliberately PULL only: GENUS tells what it wonders about when *asked* -- an
# unprompted interjection (push) is a separate, conscious decision. Read-only: answering an
# inquiry is the teacher-loop, a WRITE, and stays at the terminal (the Telegram membrane is a
# Mundstück by design).

_INQUIRY_CUES = (
    "was beschäftigt dich", "was beschaeftigt dich",
    "hast du fragen", "hast du offene fragen", "hast du noch fragen",
    "welche fragen hast du", "was fragst du dich",
    "gibt es offene fragen", "was ist dir unklar",
    "worüber denkst du nach", "worueber denkst du nach",
)


def inquiries_question(question: str) -> bool:
    """True when the question asks about GENUS's OWN open questions."""
    q = question.casefold()
    return any(cue in q for cue in _INQUIRY_CUES)


# --- GENUS' eigene Ziele (Inversion ④ des Audits: Ziele sind Wissen im Graphen) -----------
#
# Seit dem Ziel-Graphen (genus/ziele.py, Ronnys sieben Punkte vom 2026-07-03 als provenancte
# Knoten) WEISS GENUS, was es werden soll -- und kann es erzählen, samt der ehrlichen Lücke
# ("dafür fehlt mir noch: ..."), direkt aus dem Graphen, deterministisch, kein Modell.

_ZIELE_CUES = (
    "was sind deine ziele", "welche ziele hast du", "was willst du werden",
    "was ist deine mission", "was ist dein ziel", "wozu bist du da",
    "wofür bist du da", "wofuer bist du da", "was fehlt dir",
)


def ziele_question(question: str) -> bool:
    """True when the question asks about GENUS's OWN goals or what it still lacks for them."""
    q = question.casefold()
    return any(cue in q for cue in _ZIELE_CUES)


def narrate_ziele(conn) -> str:
    """Mission, Ziele und die ehrlich benannten fehlenden Fähigkeiten -- aus dem Graphen,
    mit Herkunft. Ein leerer Graph wird ehrlich benannt (vor dem Seed-Apply auf dem Pi)."""
    from genus import ziele as ziele_mod

    m = ziele_mod.mission(conn)
    alle = ziele_mod.ziele(conn)
    if m is None and not alle:
        return ("Meine Ziele sind noch nicht in meinem Graphen angekommen — bisher stehen sie "
                "nur in Dokumenten, und die kann ich nicht lesen.")
    lines = []
    if m:
        lines.append(f"Meine Mission: {m}")
    if alle:
        lines.append(f"Dafür verfolge ich {len(alle)} Ziele:")
        for z in alle:
            fehlt = [f["id"].removeprefix(ziele_mod.FAEHIGKEIT_PREFIX)
                     for f in z["braucht"] if f["status"] != "live"]
            zeile = f"• {z['inhalt']}"
            if fehlt:
                zeile += f" (dafür fehlt mir noch: {', '.join(fehlt)})"
            lines.append(zeile)
    lines.append("(Quelle: Ronny — meine Ziele sind Wissen mit Herkunft, wie alles andere.)")
    return "\n".join(lines)


def open_questions(conn) -> dict:
    """GENUS's open inquiries, grouped by (type, claim) so ten repeats of the same surprise
    become one speakable concern with a count -- the raw rows stay in ``genus inquiries``."""
    from genus import inquiries as inq

    groups: dict[tuple[str, str], dict] = {}
    for row in inq.list_inquiries(conn, include_all=False):
        key = (row["inquiry_type"], row["claim_key"])
        g = groups.setdefault(key, {
            "inquiry_type": row["inquiry_type"], "claim_key": row["claim_key"],
            "payload": json.loads(row["payload"] or "{}"), "count": 0,
        })
        g["count"] += 1
    return {"groups": list(groups.values())}


def _speak_inquiry(conn, g: dict) -> str:
    """One open concern as a German sentence -- type-specific, labels instead of Q-ids."""
    t, claim, p = g["inquiry_type"], g["claim_key"], g["payload"]
    times = f" ({g['count']}-mal aufgefallen)" if g["count"] > 1 else ""
    if t == "StabilityInquiry":
        return f"»{claim}« hat sich geändert, obwohl ich es für stabil hielt{times}."
    if t == "SourceContradiction" and p.get("kind") == "acyclicity_violation":
        parts = claim.split("|")
        subj = p.get("subject") or (parts[0] if parts else claim)
        obj = p.get("object") or (parts[2] if len(parts) > 2 else "")
        return (f"In meiner Begriffs-Hierarchie steckt ein Kreis: {_label(conn, subj)} und "
                f"{_label(conn, obj)} stehen gegenseitig als Oberbegriff da — eine Richtung "
                f"muss falsch sein, und ich weiß nicht, welche{times}.")
    if t == "SourceContradiction":
        return f"Zwei Quellen, denen ich vertraue, widersprechen sich bei »{claim}«{times}."
    if t == "CauseInquiry":
        return f"Mein Zustand hat sich geändert und ich kenne die Ursache nicht (»{claim}«){times}."
    if t == "ExpectationInquiry":
        return f"»{claim}« verhält sich anders, als mein gelernter Rhythmus erwartet{times}."
    if t == "AbstraktionInquiry":
        eltern = _label(conn, p["elternteil"]) if p.get("elternteil") else "einem Muster"
        if p.get("art") == "wachstum":
            kand = ", ".join(_label(conn, k) for k in (p.get("kandidaten") or [])[:5]) or "etwas"
            return (f"Sollte auch {kand} zu dem Begriff gehören, den ich selbst unter "
                    f"»{eltern}« gebildet habe?{times}")
        return (f"Der Begriff, den ich selbst unter »{eltern}« gebildet habe, trägt seine "
                f"Mitglieder nicht mehr zusammen{times}.")
    return f"»{claim}« ({t}){times}."


def narrate_inquiries(conn, oq: dict) -> str:
    """The open concerns as fluent German -- and the honest note that answering them happens
    at the terminal, because this channel deliberately cannot write. Zusätzlich der DRUCK
    (genus.druck): die drängendste ungestillte Verstehens-Lücke -- die PERSISTIERT jetzt,
    statt sich beim Aussprechen zu entladen, und wird als solche benannt, wenn sie seit dem
    Vorschlag weiter gewachsen ist (Ronny 2026-07-05, docs/research/INTELLIGENCE.md §9)."""
    from genus import druck

    # nach Wiederkehr-Druck geordnet: die am häufigsten aufgefallene Sorge zuerst (der
    # Frage-Druck sichtbar gemacht, ohne die Aufzählung zu doppeln -- genus.druck.frage_druck
    # trägt dieselbe Zahl für den strukturierten Blick / den künftigen inneren Loop).
    groups = sorted(oq["groups"], key=lambda g: -g["count"])
    druck_satz = druck.satz(conn)
    if not groups and not druck_satz:
        return "Gerade beschäftigt mich nichts Offenes — alle meine Fragen sind beantwortet."
    lines: list[str] = []
    if groups:
        header = ("Mich beschäftigt gerade eine Sache:" if len(groups) == 1
                  else f"Mich beschäftigen gerade {len(groups)} Dinge:")
        lines.append(header)
        lines += ["• " + _speak_inquiry(conn, g) for g in groups]
        lines.append("(Antworten kann ich hier nicht entgegennehmen — das geht am Terminal: "
                     "„genus inquiries\" und „genus teach\".)")
    if druck_satz:
        lines.append(druck_satz)
    return "\n".join(lines)


# --- a bare follow-up, read against the PREVIOUS turn ------------------------------------
#
# The gap Ronny hit live: asking "GENUS why answer that?" right after an answer fell through to
# a plain word-lookup, because every call to `respond` is stateless -- "that" means nothing on
# its own. Deliberately narrow: a small, closed set of German provenance cue phrases, not general
# coreference resolution (a genuinely harder problem; pronoun substitution like "und es?" is a
# natural next slice, not built here). `companion.py` stays pure -- a caller across multiple
# turns (the Telegram bridge) owns the actual per-chat state and threads it through.

_WHY_FOLLOWUP = {
    "warum", "wieso", "weshalb",
    "woher weißt du das", "woher weisst du das",
    "woher weißt du das denn", "woher weisst du das denn",
    "woher kommt das", "woher hast du das",
}


def is_why_followup(question: str) -> bool:
    """True for a bare provenance follow-up ("warum?", "woher weißt du das?", ...) -- it has no
    subject of its own, but makes sense read against the PREVIOUS turn's question."""
    return question.strip().strip("?!.").strip().lower() in _WHY_FOLLOWUP


# --- Mehr-Zug-Arbeitsgedächtnis (Punkt 4 von docs/design/MEMORY.md, Scheibe "das Tier von
# vorhin wird auflösbar") -- dieselbe Disziplin wie beim "warum?"-Nachfrage-Fix: ein kleiner,
# geschlossener Signalsatz statt allgemeiner Koreferenz-Auflösung (ein echt schwereres Problem).
# GENUS erfindet keine Wort-Ersetzung ("das Tier" -> "der Igel") -- es beantwortet ehrlich die
# FRÜHERE, konkrete Frage noch einmal, sichtbar als solche benannt, statt so zu tun, als hätte
# es die neue Formulierung wirklich verstanden. ``verlauf`` sind Züge VOR dem unmittelbar
# letzten (der schon über last_question/last_answer erreichbar ist) -- reines UX-Zustand in der
# Membran (Ledger != Memory), wie last_question/last_answer selbst.

_BACKREF_CUES = ("von vorhin", "von eben")
_BACKREF_TAG = " (Bezogen auf deine frühere Frage „{}“.)"


def is_backreference(question: str) -> bool:
    """True for a question that explicitly points back beyond the immediately previous turn
    ("... von vorhin", "... von eben") -- deliberately narrow, not general pronoun resolution."""
    q = question.lower()
    return any(cue in q for cue in _BACKREF_CUES)


def _fruehere_frage_mit_bekanntem_begriff(conn, verlauf: list[dict]) -> str | None:
    """The most recent EARLIER question (newest first) that GENUS could actually answer again
    (contains a word it knows) -- ``None`` if no turn in ``verlauf`` qualifies."""
    for zug in reversed(verlauf):
        frage = zug.get("question")
        if frage and _last_known_word(conn, frage) is not None:
            return frage
    return None


def respond_in_conversation(conn, question: str, last_question: str | None = None) -> dict:
    """Like ``respond``, but aware of the PREVIOUS turn's question. A bare "warum?"/"woher weißt
    du das?" reruns the exact same routing ``why`` would use for ``last_question`` -- correctly
    retracing a relational chain or a word's grounding, whichever the previous turn actually
    answered -- instead of falling through to "GENUS kennt kein Wort in ...". Returns
    ``{"text": ..., "question": ...}``; a caller threads ``question`` forward as the next call's
    ``last_question`` to keep the conversation anchored."""
    if last_question and is_why_followup(question):
        text = "\n".join(render_trace(conn, trace(conn, last_question)))
        return {"text": text, "question": last_question}  # still "about" the same thing
    from genus import antwort as _antwort
    return {"text": respond(conn, question, _antwort.belegung(conn, "plausch")),
            "question": question}


# --- der VERSTEHENS-WÜRFEL: erst einordnen, dann lösen -- als echte Zwicky-Box -----------
#
# Die Dispatch-Bug-KLASSE, live dreimal in einem Test gesehen (2026-07-02): Routing war eine
# first-match-wins-Kette verschmolzener Erkenner+Löser bis zu einem gierigen Wort-Lookup, so
# dass "zählt ein Apfel zu den Pflanzen?" einen Botanik-Vortrag über "Pflanzen" bekam, bevor
# eine bessere Lesart je gefragt wurde. Ronnys erster Fix (derselbe Tag) trennte EINORDNEN von
# LÖSEN strukturell. Eine zweite, echte Session ("wir machen noch grundsätzliche Dinge falsch")
# zeigte: das "Raster" war immer noch eine flache Liste mit is_a-Fallback-Leiter, kein
# morphologischer Kasten -- "Hallo"->kürzer, eine Wetterfrage->vergleich, eine Hilfe-Bitte->
# abschied waren alle Fehlgriffe auf Zellen, die als eigenständiges Ding gar nicht existierten.
#
# Jetzt: Zwickys General Morphological Analysis (1948/1969), alle vier Schritte. Drei
# unabhängige Parameter (Sprechakt, Gegenstand, Bezug -- genus.verstehen), ihre Kreuz-
# Konsistenz geprüft (nur die sinnvollen (Sprechakt,Gegenstand)-Kombinationen sind gesät), und
# -- Ronnys zweiter, schärferer Punkt -- eine Nachricht ist kein einzelnes Tripel: sie zerfällt
# in mehrere funktionale SEGMENTE (ISO 24617-2, Dialogue Act Markup Language; "Hallo! Was ist
# ein Hund? Danke!" sind drei, nicht eins). Der Deuter (deploy/deuter.py) liest jetzt eine
# LISTE von Segmenten, nicht ein Objekt; ``_deuter_antwort`` löst JEDES Segment einzeln über
# genau denselben (Blatt -> Zelle)-Mechanismus, und die Teil-Antworten werden komponiert
# (:func:`_komponiere`) -- der erste, bewusst einfache Auftritt des "Antwort-Würfels".
#
# Kein Freitext-Ausweg mehr: die alte "beschreibe frei, wenn unsicher"-Klausel hatte selbst
# Nebenwirkungen (live: "Danke" wich auf "erleben" aus). Die Kategorien sind jetzt Zwicky-
# geprüft und sollen erschöpfend sein; bei echter Unsicherheit ist "unklar" die sichere Antwort.
# Acting happens only from known cells; a known cell without a handler is named honestly
# ("das kann ich noch nicht"); a leaf whose own handler can't resolve climbs GENAU EINEN
# Schritt zu seiner Zelle (nie tiefer -- die Zelle ist schon die gröbste sinnvolle Einheit).
#
# The model at the edge stays on the same leash as ever: deploy/deuter.py, injected as a plain
# callable, WAEHLT/liest only -- every subject/object it names is graph-verified by the same
# resolution cores the regex path uses, every model-assisted answer is visibly marked, a wrong
# reading can only fail safe. Benchmarked choice (7 models/4 families on the Pi):
# Qwen2.5-1.5B-Instruct -- small models handle SMALL tasks well, and the Würfel keeps every
# model task small.

_UNKNOWN_FALLBACK = (   # query.ask's stable "nothing recognized" sentinel -- keep in sync
    "Das kann GENUS nicht einordnen — kein bekannter Befehl, kein gelerntes Wort."
)
# Live gefunden (2026-07-03): wenn der Deuter LIEF und ehrlich nichts fand (leere Liste --
# "OK prima" bekam wortwörtlich `[]` vom Modell zurück), fiel GENUS bisher auf den gierigen
# Wort-Lookup zurück -- der griff sich irgendein bekanntes Wort aus dem Satz ("prima" -> eine
# Schulstufe, "glaube ich" -> Theologie) und erklärte es, komplett am Thema vorbei. Das ist
# SCHLIMMER als ehrliches Nichtverstehen: es sieht wie eine Antwort aus, ist aber keine. Ein
# Deuter-Lauf, der explizit nichts findet, ist ein stärkeres Signal als "kein Deuter da" --
# nur DANN (deuter(question) gibt None, nicht bloß eine leere Liste) bleibt der Wort-Lookup
# ein legitimer letzter Versuch.
_NICHT_VERSTANDEN = "Das habe ich nicht verstanden — magst du es anders sagen?"
_DEUTED = " (Frage vom Sprachmodell gedeutet.)"

# German voice for cells GENUS can read but not yet act on -- honest capability naming. Nur
# noch Blätter, die tatsächlich bis zum ehrlichen Lücken-Satz durchfallen können (die anderen
# lösen sich entweder direkt oder klettern zu einer Zelle mit eigenem Fallback -- z.B.
# eigenschaft/menge landen bei frage-begriff und werden dort beantwortet; „ursache" hat seit
# P3.1 ein eigenes Kausal-Blatt und fällt bei Unauflösbarkeit dorthin, brauchen also gar keine
# eigene Lücken-Formulierung mehr).
_ZELLEN_LABELS = {
    "empfehlungsfrage": "eine Bitte um Empfehlung",
    "weltfrage": "eine Frage über die Welt draußen",
    "korrektur": "eine Korrektur an einer Tatsache",
    "meinung": "eine Meinungsäußerung",
    "lernen": "eine Aufforderung, etwas zu lernen",
    "tun": "eine Aufforderung, etwas in der Welt zu tun",
}


def _zelle_definition(conn, guess, question, last_question, last_answer, stimme=None,
                      waage=None):
    # ``waage``: die einzige Zelle mit dem reicheren Parameter -- der Dispatch verhandelt die
    # Signatur (wie ``_stimme_versucht``), die übrigen Zellen bleiben unberührt
    subject = guess.get("subject")
    if not subject:
        return None
    found = _last_known_word(conn, subject)
    if found is None:
        return None
    return respond(conn, f"Was ist {found}?", waage=waage)


def _anker_ok(question: str, *begriffe: str) -> bool:
    """Der ANKER-SENSOR des Planer-Pfads (③ Scheibe C): kommt jeder MODELL-extrahierte
    Begriff wortwörtlich (case-lenient, als ganzes Wort) in der Nachricht vor? Bewusst
    SENSOR, nicht Tor: die Deuter-Kernfähigkeit ist gerade, eine Paraphrase aufzulösen
    („wuffwuff" -> Hund -- testbewiesen), und die Beziehungs-Antwort ist selbst-offenlegend
    (sie NENNT beide Begriffe in »«, ein fremder wäre sichtbar, nicht still wie eine
    Stimme-Korruption). Nicht verankert wird also GEZÄHLT (Rohdaten fürs Thermometer ④),
    nie blockiert. Wo eine Antwort ihre Eingaben NICHT nennt, darf daraus ein Tor werden."""
    woerter = {w.casefold() for w in _WORD.findall(question or "")}
    return all((b or "").casefold() in woerter for b in begriffe)


def _zelle_beziehung(conn, guess, question, last_question, last_answer, stimme=None):
    if not (guess.get("subject") and guess.get("object")):
        return None
    if not _anker_ok(question, guess["subject"], guess["object"]):
        from genus import zaehlwerk
        zaehlwerk.zaehle("beziehung", "anker_frei")   # gedeutet statt zitiert -- messen, nicht blocken
    from genus import antwort as _antwort, werkzeuge_auskunft
    bel = _antwort.belegung(conn, "plausch")   # Voice 1 (Scheibe 1) -- Wärme aus dem Antwort-Würfel
    r = werkzeuge_auskunft.relate_geplant(conn, guess["subject"], guess["object"])
    if r["relational"] and r["verdict"] == "yes":
        return narrate_relation(conn, r, bel)   # eine echte is_a-Einordnung -- die stärkste Antwort
    # keine POSITIVE is_a-Beziehung? -> dieselbe Zelle trägt auch die GERICHTETE Kausal-Beziehung
    # („Verursacht X Y?", „Führt X zu Y?" -- Formulierungen, die die festen Muster von
    # _muster_antwort verfehlen, der Deuter aber als beziehung liest). Wichtig: „beide bekannt,
    # keine is_a-Kante" ist verdict=="no_path" (relational=True!) -- genau der Kausal-Fall; er darf
    # NICHT von der is_a-Zurückhaltung geschluckt werden. Reihenfolge: is_a-Ja > Kausal-Ja >
    # ehrliche is_a-Zurückhaltung. Die Kausal-Antwort ist selbst wortlautfest (Richtung = Wahrheit).
    k = _kausal_zwischen(conn, guess["subject"], guess["object"])
    if k["kausal_q"] and k["art"] == "ja":
        return narrate_kausal(conn, k, bel)
    return narrate_relation(conn, r, bel) if r["relational"] else None


def _zelle_ursache(conn, guess, question, last_question, last_answer, stimme=None):
    # „Was verursacht X?" / „Wodurch entsteht X?" -- das eigene Blatt der Kausal-FRAGE nach
    # Ursachen (früher ohne Handler: es kletterte zur Zelle frage-begriff und bekam die
    # DEFINITION von X statt seiner Ursachen -- eine andere Frage beantwortet, P3.1). Jetzt
    # führt es zur gebauten Kausal-Fähigkeit -- seit ③ Scheibe C Planer zuerst;
    # unauflösbar -> None (klettert ehrlich weiter).
    subject = guess.get("subject")
    if not subject:
        return None
    if not _anker_ok(question, subject):
        from genus import zaehlwerk
        zaehlwerk.zaehle("ursache", "anker_frei")
    from genus import antwort as _antwort, werkzeuge_auskunft
    r = werkzeuge_auskunft.ursachen_geplant(conn, subject)
    bel = _antwort.belegung(conn, "plausch")   # Voice 1 (Scheibe 1)
    return narrate_kausal(conn, r, bel) if r["kausal_q"] else None


def _zelle_vergleich(conn, guess, question, last_question, last_answer, stimme=None):
    if not (guess.get("subject") and guess.get("object")):
        return None
    if not _anker_ok(question, guess["subject"], guess["object"]):
        from genus import zaehlwerk
        zaehlwerk.zaehle("vergleich", "anker_frei")
    from genus import antwort as _antwort, werkzeuge_auskunft
    r = werkzeuge_auskunft.vergleich_geplant(conn, guess["subject"], guess["object"])
    bel = _antwort.belegung(conn, "plausch")   # Voice 1
    return narrate_common(conn, r, bel) if r["common"] else None


def _zelle_ort(conn, guess, question, last_question, last_answer, stimme=None):
    # Gerichtet (X liegt in Y, nicht umgekehrt), darum Verbatim-Insel.
    if not (guess.get("subject") and guess.get("object")):
        # Fehlender Pflichtslot wird im Werkzeugvertrag geklärt, nie per Begriffs-Fallback.
        return ("Ich habe eine Ortsfrage erkannt, aber mir fehlt der zweite konkrete Ort. "
                "Meine Ortsfähigkeit prüft derzeit Beziehungen wie „Liegt Kassel in Hessen?“. "
                "Welchen Ausgangsort und welchen Zielort soll ich prüfen?")
    if not _anker_ok(question, guess["subject"], guess["object"]):
        from genus import zaehlwerk
        zaehlwerk.zaehle("ort", "anker_frei")
    from genus import antwort as _antwort, werkzeuge_auskunft
    r = werkzeuge_auskunft.ort_geplant(conn, guess["subject"], guess["object"])
    bel = _antwort.belegung(conn, "plausch")   # Voice 1
    return narrate_ort(conn, r, bel) if r["relational"] else None


def _zelle_grammatik(conn, guess, question, last_question, last_answer, stimme=None):
    if not guess.get("subject"):
        return None
    r = _gender_term(conn, guess["subject"])
    return narrate_gender(r) if (r["known"] or r.get("prediction")) else None


def _zelle_nachfrage(conn, guess, question, last_question, last_answer, stimme=None):
    if not last_question:
        return None
    return "\n".join(render_trace(conn, trace(conn, last_question)))


def _zelle_tatsache(conn, guess, question, last_question, last_answer, stimme=None):
    # die eigene Klausel des Segments merken, nicht die ganze Nachricht -- sonst würde
    # "Hallo! Ich war auf einem Konzert. Danke!" den Gruß und den Dank mit in die Episode aufnehmen
    from genus import erinnerung  # local: keeps companion's import-time surface a leaf otherwise

    text = guess.get("text") or question
    erinnerung.merke(conn, text, quelle=erinnerung.STATEMENT_SOURCE)
    return (f"Das klingt nach einer Erinnerung — ich hab's mir notiert, aber noch unsicher "
            f"(sag „merke dir: {text}“, wenn's wichtig ist, dann bin ich mir sicher).")


def _zelle_merken(conn, guess, question, last_question, last_answer, stimme=None):
    # a MODEL-read "please remember" (the explicit ritual "merke dir: ..." never reaches the
    # Deuter) -- never granted human trust off a model reading: capped note + the honest hint
    return _zelle_tatsache(conn, guess, question, last_question, last_answer, stimme)


def _zelle_erinnerung(conn, guess, question, last_question, last_answer, stimme=None):
    from genus import erinnerung  # local: keeps companion's import-time surface a leaf otherwise

    return narrate_notes(erinnerung.bestaetigte_episoden(conn), erinnerung.vermutete_episoden(conn))


def _zelle_zustand(conn, guess, question, last_question, last_answer, stimme=None):
    from genus import query
    return query.ask(conn, "zustand")["answer"]


def _zelle_selbstbild(conn, guess, question, last_question, last_answer, stimme=None):
    from genus import selbstbild

    aspekt = " ".join(str(v) for v in (guess.get("subject"), guess.get("object")) if v)
    return selbstbild.bericht(conn, aspekt=aspekt or None)


def _zelle_offene_fragen(conn, guess, question, last_question, last_answer, stimme=None):
    return narrate_inquiries(conn, open_questions(conn))


def _zelle_ziele(conn, guess, question, last_question, last_answer, stimme=None):
    return narrate_ziele(conn)


# Reine SPRACHE (kein Fakt): wie eine Zwicky-Zelle im Fähigkeits-Satz heißt -- dieselbe Rolle
# wie antwort.FLOSKELN (Charta §2: eine Anzeige-Tabelle, keine zweite Wissens-Quelle; die
# WAHRHEIT, was GENUS kann, kommt aus der Registry via hat_handler).
_FAEHIGKEIT_ANZEIGE = (
    ("frage-begriff", "Fragen zu Begriffen"),
    ("frage-genus", "Fragen über mich"),
    ("frage-nutzer", "Fragen über dich"),
    ("frage-gespraech", "Rückfragen zum Gespräch"),
    ("frage-welt", "Fragen zur Welt draußen"),
    ("aussage-begriff", "Korrekturen an meinem Wissen"),
    ("aussage-nutzer", "was du mir über dich erzählst"),
    ("aufforderung-genus", "Bitten an mich"),
    ("aufforderung-gespraech", "Wünsche zur Antwort"),
    ("aufforderung-welt", "Handlungen in der Welt"),
    ("floskel", "die alltäglichen Gesten"),
)


def _zelle_faehigkeiten(conn, guess, question, last_question, last_answer, stimme=None):
    """„Was kannst du?" -- die Zelle, um die GENUS SELBST gebeten hat (Proposal #15, der
    VerstehensLuecke-Detector: 3x gelesen, nie beantwortbar; von Ronny 2026-07-11 freigegeben).
    Die Antwort wird GLASKLAR aus der lebenden Werkzeug-Registry gelesen (hat_handler je
    gesätem Raster-Blatt, gruppiert nach Zwicky-Zelle) -- keine hartcodierte Selbstbeschreibung,
    die driften könnte; wächst die Registry, wächst die Antwort. Ehrlich in beide Richtungen:
    nennt auch, was es liest, aber (frei formuliert) noch nicht kann. Zählt sich dabei selbst
    als beantwortbar -- die Zelle IST ihr eigener erster Beleg."""
    from genus import verstehen
    from genus.werkzeuge_auskunft import ABSICHT_SAAT

    koennen: dict[str, list[str]] = {}
    fehlt: list[str] = []
    for blatt in verstehen.leaf_kinds(conn):
        if blatt == "unklar":
            continue   # der blinde Fleck ist keine Fähigkeit und keine Lücke -- er ist der Sensor
        if hat_handler(conn, blatt):
            koennen.setdefault(verstehen.zelle_of(conn, blatt) or "?", []).append(blatt)
        else:
            fehlt.append(blatt)
    gesamt = sum(len(b) for b in koennen.values())
    gruppen = [f"{anzeige} ({', '.join(sorted(koennen[zelle]))})"
               for zelle, anzeige in _FAEHIGKEIT_ANZEIGE if koennen.get(zelle)]
    saat = sorted(ABSICHT_SAAT)
    text = (f"Das lese ich dir live aus meiner eigenen Werkzeug-Registry ab: "
            f"{gesamt} Lesarten kann ich beantworten — " + "; ".join(gruppen) + ". "
            f"{len(saat)} Absichten davon plant mein Werkzeug-Planer selbst "
            f"({', '.join(saat)}).")
    if fehlt:
        text += (f" Frei formuliert noch nicht handeln kann ich auf: {', '.join(sorted(fehlt))} "
                 f"— die lese ich und zähle sie ehrlich als Lücken.")
    return text + " Und was mir zu meinen Zielen fehlt, sage ich dir auf „Was fehlt dir?“."


def _zelle_frage_begriff(conn, guess, question, last_question, last_answer, stimme=None):
    # der weiche Landeplatz der Zelle "frage-begriff" selbst -- eigenschaft/ursache/menge
    # haben kein eigenes Blatt-Handler und klettern genau EINEN Schritt hierher (Blatt -> Zelle,
    # siehe verstehen.zelle_of): sag, was ÜBER DEN BEGRIFF bekannt ist, ehrlich benannt, was
    # GENAU noch nicht beantwortet werden kann.
    text = _zelle_definition(conn, guess, question, last_question, last_answer, stimme)
    if text is None:
        return None
    return text + " Genauer (das, wonach du eigentlich fragst) kann ich noch nicht antworten."


# --- der ANTWORT-WÜRFEL, erste Scheibe: die Meta-Zellen ----------------------------------
#
# Ronnys Weiterdenken vom Verstehens-Würfel aus: auch die ANTWORT wird komponiert, nicht nur
# die Frage eingeordnet. Erste, bewusst kleine Scheibe: die vier Meta-Ausprägungen
# (kuerzer/ausfuehrlicher/anders-erklaeren/wiederholen) standen im Raster schon seit der
# Würfel-Scheibe, hatten aber KEINEN Handler -- "na wie laeufts" wurde live sogar fälschlich
# als "kuerzer" gelesen und bekam nur "das kann ich noch nicht". Diese vier komponieren die
# LETZTE Antwort um (``last_answer``, jetzt in der Session neben ``last_question`` geführt),
# nie den Kern selbst -- deterministisch, wo möglich (Kürzen = erster Satz, Wiederholen =
# wörtlich), und nur bei "anders erklären" wird die Stimme ein zweites Mal versucht (das ist
# genau ihre Aufgabe: dieselben Fakten anders formulieren). Ohne ``last_answer`` (kein voriger
# Zug bekannt) ist ehrliches Nichtwissen die einzig korrekte Antwort -- nichts wird erfunden.

def _zelle_kuerzer(conn, guess, question, last_question, last_answer, stimme=None):
    if not last_answer:
        return None
    erster_satz = last_answer.split(". ", 1)[0].rstrip(".") + "."
    return erster_satz if erster_satz != last_answer else None   # war schon kurz -- nichts zu tun


def _zelle_ausfuehrlicher(conn, guess, question, last_question, last_answer, stimme=None):
    if not last_answer or not last_question:
        return None
    spur = "\n".join(render_trace(conn, trace(conn, last_question)))
    return last_answer + "\n" + spur


def _zelle_anders_erklaeren(conn, guess, question, last_question, last_answer, stimme=None):
    if not last_answer:
        return None
    anders = _stimme_versucht(conn, last_answer, stimme)   # ihre eigentliche Aufgabe: neu formulieren
    if anders != last_answer:   # ein echter zweiter Versuch ist gelungen (Anker-geprüft)
        return anders
    return f"Ich kann es nur so sagen, wie ich es weiß: {last_answer}"   # ehrlich wiederholt, nie erfunden


def _zelle_wiederholen(conn, guess, question, last_question, last_answer, stimme=None):
    if not last_answer:
        return None
    return f"Nochmal: {last_answer}"


# --- Sozialgesten: feste, höfliche Antworten -- kein Wissen behauptet, nichts erfunden --------
#
# Live gefunden (2026-07-03): ein bloßes "Hallo" landete beim ehrlichen "das kann ich noch
# nicht" -- korrekt im Sinne von "keine Zelle hat gehandelt", aber absurd für den simpelsten
# aller Gesprächseinstiege. Diese fünf sind reine Höflichkeitsfloskeln, kein Wissen -- ein
# fester Satz ist hier keine Einschränkung, sondern die richtige Antwort.
#
# ABER, gleich beim Nachverifizieren gefunden: ein echter Gruß/Dank/Abschied ist so gut wie
# immer KURZ. Ein langer, mehrteiliger Satz ("Ich möchte einen Familienausflug planen, kannst
# du mir helfen?"), den der Deuter trotzdem als "abschied" liest, ist mit an Sicherheit
# grenzender Wahrscheinlichkeit ein Fehlgriff -- und ein selbstsicheres "Bis bald!" darauf ist
# SCHLIMMER als die ehrliche Lücken-Meldung von vorher: die Lücken-Meldung verrät wenigstens,
# dass etwas schiefging, ein fester Höflichkeitssatz tut das nicht. Eine Wortzahl-Bremse ist
# hier keine Sprach-Analyse, nur eine harte, erklärbare Grenze -- lieber einmal zu oft ehrlich
# durchfallen als einem echten Anliegen ein munteres "Bis bald!" hinterherrufen.
#
# Live gefunden nach der Segmentierung: die Bremse muss das SEGMENT beurteilen (``guess["text"]``,
# die eigene Klausel), nicht die ganze Nachricht (``question``) -- sonst reißt eine lange
# Nachricht ("Hallo! Was ist ein Hund? Danke!") ihr eigenes kurzes "Danke!"-Segment mit in die
# Bremse und die Antwort verschwindet stillschweigend aus der komponierten Antwort.

_SOZIALGESTE_MAX_WOERTER = 6


def _ist_kurze_aeusserung(text: str) -> bool:
    return len(_WORD.findall(text)) <= _SOZIALGESTE_MAX_WOERTER


def _zelle_gruss(conn, guess, question, last_question, last_answer, stimme=None):
    if not _ist_kurze_aeusserung(guess.get("text") or question):
        return None
    # Persönlichkeit wirkt an der SPRACHE: Variante + Beiwerk wählt der Antwort-Würfel
    # (genus.antwort, EINE Stelle) -- Fakten/Ehrlichkeit bleiben unberührt.
    from genus import antwort

    return antwort.floskel(conn, "gruss")


def _zelle_dank(conn, guess, question, last_question, last_answer, stimme=None):
    if not _ist_kurze_aeusserung(guess.get("text") or question):
        return None
    from genus import antwort

    return antwort.floskel(conn, "dank")


def _zelle_lob(conn, guess, question, last_question, last_answer, stimme=None):
    if not _ist_kurze_aeusserung(guess.get("text") or question):
        return None
    return "Danke."


def _zelle_kritik(conn, guess, question, last_question, last_answer, stimme=None):
    if not _ist_kurze_aeusserung(guess.get("text") or question):
        return None
    return "Danke für die Rückmeldung — sag mir gern genauer, was nicht gepasst hat."


def _zelle_abschied(conn, guess, question, last_question, last_answer, stimme=None):
    if not _ist_kurze_aeusserung(guess.get("text") or question):
        return None
    return "Bis bald!"


def _zelle_einstellung(conn, guess, question, last_question, last_answer, stimme=None):
    """Die Regler-Zelle des Verstehens-Würfels: eine frei formulierte Bitte, GENUS' Art
    zu verstellen („könntest du dich kürzer fassen?") -- liest Achse+Richtung aus der
    eigenen Klausel und stellt über dieselbe Implementierung wie die exakten Kommandos."""
    from genus import persoenlichkeit

    deutung = _regler_deute(guess.get("text") or question)
    if deutung is None:
        achsen = ", ".join(persoenlichkeit.ANZEIGE[m] for m in persoenlichkeit.MERKMALE)
        return ("Ich lese das als Wunsch, meine Art zu verstellen — sag mir die Richtung, "
                "eine Achse auf einmal: z.B. „sei knapper“, „sei wärmer“, „mehr Humor“. "
                f"(Meine Achsen: {achsen}.)")
    return _regler_stellen(conn, *deutung)


# --- der erste SINN spricht (P4, Ronny 2026-07-08: „auf jeden fall p4" -> Wetter) ---------
#
# GENUS nimmt die Aussentemperatur schon stuendlich WAHR (deploy/observe_weather.sh reicht die
# nackte Zahl durch die Membran; der Kern greift NIE selbst ins Netz), aber bis hier konnte es
# sie nicht AUSSPRECHEN -- die Raster-Zelle „weltfrage" hatte keinen Handler. Dies ist der eine
# fehlende Lese-Draht: er liest den Wert rein aus dem Ledger (sources.resolve, mit Herkunft +
# Frische + Quellen-Konsens) und spricht ihn gLASERN aus. Ehrliche Teil-Antwort: was der Sinn
# ERREICHT (aktuelle Temperatur) wird gesagt, was er NICHT erreicht (Vorhersage, Regen, andere
# Orte) wird ehrlich benannt statt erfunden. Reines Lesen -> nicht schreibend; wortlautfest ->
# die Stimme formt die Sensor-Zahl nie um (sie ist Fakt, kein Ausdruck).
# --- die DISPATCH-Zelle „weltfrage" -------------------------------------------------------
# Die drei Welt-Sinne selbst (Wetter, Nachrichten, Uhr + ihre Frische-Helfer und Tabellen)
# leben seit der Modularisierung (2026-07-09, Schritt ②) in :mod:`genus.weltsinn` und sind oben
# re-importiert. Hier bleibt nur die Dispatch-Zelle, die sie ruft -- sie gehoert zum Register
# der Gespraechszellen (_HANDELBAR), nicht zum Sinn.
def _zelle_weltfrage(conn, guess, question, last_question, last_answer, stimme=None):
    """Der Welt-Sinn (P4): Zeit-Frage -> Uhr, Nachrichten-Frage -> News, sonst -> Wetter (der
    Deuter fasst all das als „weltfrage"). Alle drei rein lesend -- die Sinne selbst leben in
    :mod:`genus.weltsinn`."""
    text = (guess.get("text") if isinstance(guess, dict) else "") or question or ""
    if _ist_zeit_frage(text):
        return _uhrzeit_bericht(conn)
    if _ist_news_frage(text):
        return _news_bericht(conn)
    return _wetter_bericht(conn)


# Können ist Code, Wissen über Absichten ist Graph: a cell acts iff a handler exists HERE;
# which cells exist and how they relate lives in the ledger (genus.verstehen.RASTER_SEED +
# ZELLEN). Die Schlüssel sind jetzt teils Feinblätter (definition, gruss, ...), teils die
# Kreuzprodukt-Zelle selbst ("frage-begriff") -- der EINE weiche Landeplatz für Blätter ohne
# eigenen Handler (verstehen.zelle_of macht daraus nie mehr als einen Klettersprung).
# Der CODE-SEITIGE SEED der Gesprächszellen (Phase 3 der Ziel-Architektur): dieses Dict ist
# nicht mehr die Dispatch-Tabelle, sondern das Rohmaterial, aus dem registriere_zellen()
# geprüfte Werkzeug-Einträge baut -- derselbe Bootstrap-Boden wie RASTER_SEED/ZIEL_SEED.
# Alle Laufzeit-Verbraucher (Dispatch, Stimme-Eignung, hat_handler, atlas-facts) lesen die
# REGISTRY (via _handelbare_werkzeuge), nie mehr dieses Dict direkt.
_HANDELBAR = {
    "frage-begriff": _zelle_frage_begriff,
    "definition": _zelle_definition,
    "beziehung": _zelle_beziehung,
    "ursache": _zelle_ursache,
    "vergleich": _zelle_vergleich,
    "ort": _zelle_ort,
    "grammatik": _zelle_grammatik,
    "warum-herkunft": _zelle_nachfrage,
    "vertiefung": _zelle_nachfrage,
    "anschlussfrage": _zelle_nachfrage,
    "tatsache": _zelle_tatsache,
    "merken": _zelle_merken,
    "erinnerungs-abruf": _zelle_erinnerung,
    "zustand": _zelle_zustand,
    "selbstbild": _zelle_selbstbild,
    "offene-fragen": _zelle_offene_fragen,
    "ziele": _zelle_ziele,
    "faehigkeiten": _zelle_faehigkeiten,
    "kuerzer": _zelle_kuerzer,
    "ausfuehrlicher": _zelle_ausfuehrlicher,
    "anders-erklaeren": _zelle_anders_erklaeren,
    "wiederholen": _zelle_wiederholen,
    "gruss": _zelle_gruss,
    "dank": _zelle_dank,
    "lob": _zelle_lob,
    "kritik": _zelle_kritik,
    "abschied": _zelle_abschied,
    "einstellung": _zelle_einstellung,
    "weltfrage": _zelle_weltfrage,
}

ZELLE_PREFIX = "zelle:"

# Die zwei Pflicht-Entscheidungen der Werkzeug-Spec, pro Zelle ausdrücklich getroffen:
# WELCHE Zellen schreiben (alles andere liest nur), und welche NICHT wortlautfest sind
# (nur diese dürfen der Stimme angeboten werden -- die frühere zweite, handgepflegte
# Menge _STIMME_GEEIGNET ist damit weg; die Eignung folgt strukturell aus der Spec,
# genau die Bug-Klasse, für die werkzeug.wortlautfest gebaut wurde).
_ZELLEN_SCHREIBEND = frozenset({"tatsache", "merken", "einstellung"})
# beziehung/ursache DÜRFEN jetzt der Stimme angeboten werden (Antwort-Seele Scheibe 2). Sie sind
# GERICHTET („A zählt zu B", „A verursacht B"), und genau das war der Grund, sie bisher wortlautfest
# zu halten: die Substantiv-Leine prüfte nur Vorkommen, nicht Reihenfolge (live 2026-07-06:
# „Staubsauger verursacht Sog" -> „Sog verursacht Staubsauger"). Seit die Anker-Prüfung
# REIHENFOLGE-bewusst ist (deploy.stimme._reihenfolge_haelt) wird eine Umkehr erkannt und
# verworfen -> Rückfall auf den deterministischen Voice-1-Satz. Der Grund ist damit weg; der
# Kern (Begriffe, Richtung, Zahl) bleibt fest, die Stimme rahmt nur wärmer.
_ZELLEN_FREI_FORMULIERBAR = frozenset({
    "definition", "beziehung", "ursache", "vergleich", "ort", "grammatik", "frage-begriff",
})
_ZELLEN_PRUEFBAR = {
    "definition": "graph", "beziehung": "graph", "ursache": "graph", "vergleich": "graph",
    "ort": "graph", "grammatik": "graph", "frage-begriff": "graph", "zustand": "graph",
    "selbstbild": "graph", "offene-fragen": "graph", "ziele": "graph",
    "warum-herkunft": "sitzung", "vertiefung": "sitzung", "anschlussfrage": "sitzung",
    "kuerzer": "sitzung", "ausfuehrlicher": "sitzung", "anders-erklaeren": "sitzung",
    "wiederholen": "sitzung",
    "faehigkeiten": "graph",
    "tatsache": "erinnerung", "merken": "erinnerung", "erinnerungs-abruf": "erinnerung",
    "gruss": "fest", "dank": "fest", "lob": "fest", "kritik": "fest", "abschied": "fest",
    "einstellung": "graph",
    "weltfrage": "sinn",   # der erste Sinn (P4): der Wert kommt aus einem Sensor durch die Membran
}


def registriere_zellen() -> None:
    """Verdrahtet jede Gesprächszelle als geprüftes Werkzeug (Name ``zelle:<blatt>``) --
    idempotent (Verdrahten ersetzt per Name). Damit laufen die Zellen durch denselben
    Vertrag wie die Mathe-Werkzeuge: Signatur-Abgleich, Pflicht-Entscheidung wortlautfest,
    explizites schreibt."""
    from genus import werkzeug

    parameter = {
        "guess": werkzeug.Parameter(typ="Text", pflicht=True),
        "question": werkzeug.Parameter(typ="Text", pflicht=True),
        "last_question": werkzeug.Parameter(typ="Text"),
        "last_answer": werkzeug.Parameter(typ="Text"),
        "stimme": werkzeug.Parameter(typ="Text"),
    }
    for name, handler in _HANDELBAR.items():
        beschreibung = (handler.__doc__ or "").strip().split("\n")[0].strip() \
            or f"Gesprächszelle „{name}“ des Verstehens-Würfels"
        werkzeug.verdrahten(werkzeug.Werkzeug(
            name=f"{ZELLE_PREFIX}{name}",
            beschreibung=beschreibung,
            parameter=parameter,
            schreibt=name in _ZELLEN_SCHREIBEND,
            wortlautfest=name not in _ZELLEN_FREI_FORMULIERBAR,
            pruefbar_als=_ZELLEN_PRUEFBAR[name],
            # bewusst leer = TERMINAL: eine Zelle liefert einen fertigen Satz (str), keine
            # Nutzlast-Felder -- sie ist Antwort-Endpunkt, kein komponierbarer Zwischenschritt
            # (und als sterbliches Netz ohnehin auf dem Weg, sich in Pläne aufzulösen).
            liefert={},
            implementierung=handler,
        ))


def _handelbare_werkzeuge() -> dict:
    """Die lebende Dispatch-Sicht: Blattname -> Werkzeug, aus der Registry gelesen
    (Registrierung idempotent sichergestellt). Die eine Quelle der Wahrheit für den
    Dispatch, die Stimme-Eignung und die Fähigkeits-Auskunft."""
    from genus import werkzeug

    registriere_zellen()
    return {
        w.name[len(ZELLE_PREFIX):]: w
        for w in werkzeug.alle()
        if w.name.startswith(ZELLE_PREFIX)
    }


def hat_handler(conn, kind: str) -> bool:
    """Kann GENUS auf diese Lesart handeln? Wahr, wenn das Blatt selbst oder seine
    Zwicky-Zelle (ein is_a-Schritt hoch, wie im Dispatch) ein registriertes Zellen-
    Werkzeug trägt. Die öffentliche Fähigkeits-Auskunft für andere Schichten (z.B. den
    VerstehensLuecke-Detector) -- liest die Werkzeug-Registry (Phase 3)."""
    from genus import verstehen  # local: companion<->verstehen bleibt zyklenfrei

    zellen = _handelbare_werkzeuge()
    return (kind in zellen
            or (verstehen.zelle_of(conn, kind) or "") in zellen)


def _record_still(fn, *args) -> None:
    """Reading-records are Kennzahl bookkeeping -- they must never cost an answer (the bridge
    stays up even if a write fails, e.g. a read-only replica)."""
    try:
        fn(*args)
    except Exception:
        pass


# --- die STIMME: einen bereits verifizierten Satz natürlicher formulieren, nie erfinden -------
#
# Der letzte offene Plausch-Kurs-Schritt. Sitzt bewusst NACH dem Kern, anders als der Deuter
# (der VOR jeder Antwort liest): der Satz, den sie bekommt, ist bereits aus dem Graphen gebaut
# und geprüft (narrate/narrate_relation/…) -- ihre einzige Aufgabe ist FORMULIEREN, nie
# HINZUFÜGEN. Die Leine ist eine Anker-Prüfung im Modell selbst (deploy.stimme.formuliere prüft
# jedes zitierte Wort + jede Zahl), nicht Vertrauen -- ein fehlender Anker gibt hier ``None``,
# und der bewährte Template-Satz bleibt unverändert stehen. Live gefunden (2026-07-03): eine
# einfache "Was ist ein Hund?"-Frage läuft über den DEUTER-Pfad (er sitzt jetzt vor dem reinen
# Wort-Lookup), nicht über die reine Wort-Zelle -- die Stimme muss also auch dort greifen, wo
# eine narrate-artige Zelle antwortet (definition/beziehung/vergleich/grammatik/frage-begriff),
# nicht nur bei Muster/Wort. Ungeeignet sind mehrzeilige/strukturierte Antworten (Nachfrage-
# Herleitung, Erinnerungs-Liste, offene Fragen) -- dort bleibt das Risiko einer verlorenen
# Zeile größer als der Stil-Gewinn.

_STIMME_TAG = " (Sprachlich vom Modell geglättet — Fakten unverändert.)"

# Die GERICHTETEN Zellen: bei ihnen trägt die Struktur die Wahrheit (»A« zählt zu »B«, »A«
# hat als Ursache »B«). Damit die Stimme die Richtung nie umkehren kann, wird ihr gerichteter
# Kern-Satz als VERBATIM-INSEL geschützt (Antwort-Seele Scheibe 2, „Rahmen frei, Kern fest").
_GERICHTETE_ZELLEN = frozenset({"beziehung", "ursache", "ort"})


def _kern_span(text: str) -> str | None:
    """Die Verbatim-Insel eines gerichteten Satzes: die Spanne vom ERSTEN bis zum LETZTEN in
    Guillemets genannten Begriff (inklusive). Die narrate-Sätze der gerichteten Zellen sind so
    gebaut, dass die RICHTUNG genau zwischen diesen Begriffen steht (»Hund« zählt zu »Haustier«;
    »Infektion« hat als bekannte Ursache »Krankheitserreger«) -- diese Spanne wortgleich zu
    halten macht eine Umkehr unmöglich. Der Rahmen davor/dahinter (Anrede, Vertrauens-Satz)
    bleibt der Stimme frei. ``None``, wenn kein Begriffspaar vorkommt (nichts zu schützen)."""
    a = text.find("»")
    b = text.rfind("«")
    if a < 0 or b <= a:
        return None
    return text[a:b + 1]
# Die frühere Menge _STIMME_GEEIGNET ist weg (Phase 3): welche Zellen der Stimme angeboten
# werden dürfen, folgt strukturell aus der wortlautfest-Pflichtentscheidung ihrer
# Werkzeug-Spec (registriere_zellen / werkzeug.stimme_geeignet) -- eine Quelle, kein Paar.


def _stimme_versucht(conn, text: str, stimme, kern: str | None = None) -> str:
    """``text``, natürlicher formuliert via ``stimme`` (dependency-injected wie ``deuter``,
    z.B. ``deploy.stimme.formuliere``) -- unverändert, wenn ``stimme`` fehlt oder sein Versuch
    die Faktentreue-Prüfung nicht besteht (``None``). Nie stillschweigend: eine geglättete
    Antwort trägt sichtbar :data:`_STIMME_TAG`.

    Die STIL-ANWEISUNG des Antwort-Würfels (``antwort.anweisung``, deterministisch aus der
    Belegung) reist als reine Daten mit über die Membran -- das Modell formuliert INNERHALB
    der gewählten Zelle, die Anker-Prüfung bleibt die Leine. Eine Stimme ohne
    ``anweisung``-Parameter (ältere Membran, Test-Fakes) wird kompatibel ohne sie gerufen.

    FREMDTEXT-SCHUTZ (Prompt-Injektions-Grenze, Review-Fund 2026-07-08): ein News-Antwort-Block
    enthält fremde, ungeprüfte Schlagzeilen. Er wird NIE ans Modell gereicht -- weder direkt
    (weltfrage ist ohnehin wortlautfest) noch später, wenn eine Meta-Zelle (kuerzer/
    anders-erklaeren/...) ``last_answer`` umformulieren will. Erkennbar am EIGENEN Kopf, den
    GENUS schreibt (nicht der Fremdtext). So kann eine manipulative Schlagzeile die Stimme nie
    steuern -- der eine Ort, an dem Antwort-Text je ein Modell erreicht."""
    if _NEWS_ANTWORT_MARKER in text:
        return text
    if stimme is None:
        return text
    from genus import antwort

    anw = antwort.anweisung(antwort.belegung(conn, "plausch"))
    geglaettet = _stimme_ruf(stimme, text, anw, kern)
    return text if geglaettet is None else geglaettet + _STIMME_TAG


def _stimme_ruf(stimme, text: str, anw: str | None, kern: str | None):
    """Ruft die Stimme mit der reichsten Signatur, auf die sie passt (kern+anweisung ->
    anweisung -> nur text) -- kompatibel zu älteren Membranen und Test-Fakes ohne kern-/
    anweisung-Parameter. Ein TypeError heißt „diese Signatur passt nicht", nie ein Fehler in
    der Umformung (die echte Stimme fängt eigene Fehler selbst ab und gibt None zurück)."""
    for extra in ({"anweisung": anw, "kern": kern}, {"anweisung": anw}, {}):
        try:
            return stimme(text, **extra)
        except TypeError:
            continue
    return None


def _personalisiert(conn, question: str, text: str, stimme, marker: str = "",
                    kern: str | None = None) -> str:
    """Stimme-Versuch, dann ``marker`` (z.B. der Deuter-Hinweis), dann die Notiz-Einwebung
    (Personen-Gedächtnis Scheibe 2) -- in dieser Reihenfolge: die Notiz ist eine reine,
    deterministische Ergänzung ganz am Ende und darf die Anker-Prüfung der Stimme (die nur den
    narrate-Kern beurteilen soll) nicht verwirren. ``kern`` (Scheibe 2): die Verbatim-Insel des
    gerichteten Fakt-Satzes, an die Stimme durchgereicht."""
    text = _stimme_versucht(conn, text, stimme, kern=kern)
    return text + marker + (_notiz_bezug(conn, question) or "")


_ANCHOR_BLEIBT = {   # cells that reformat/retrace the EXISTING topic, never introduce a new one
    "warum-herkunft", "vertiefung", "anschlussfrage",
    "kuerzer", "ausfuehrlicher", "anders-erklaeren", "wiederholen",
}


def _segmente_loesen(conn, segmente, question: str, last_question: str | None,
                     last_answer: str | None, stimme, quelle: str, waage=None):
    """Löst eine Liste von Segment-Lesarten (aus dem Deuter ODER der Gebärden-Schnellspur) über
    :func:`_deuter_antwort` und sammelt die Teil-Antworten. Rückgabe ``(teile, gelesen, anchor)``
    -- ``teile`` sind die Segment-Antworten (für :func:`_komponiere`), ``gelesen`` die erkannten
    Blätter (Belegung/Korrektur-Kanal), ``anchor`` die für die Rückbezüge maßgebliche Frage.
    ``quelle`` wird für die ehrliche Herkunft der Belegung durchgereicht."""
    teile: list[str] = []
    gelesen: list[str] = []
    anchor = question
    for segment in segmente:
        gedeutet = _deuter_antwort(conn, segment, question, last_question, last_answer,
                                   stimme=stimme, quelle=quelle, waage=waage)
        if gedeutet is not None:
            teile.append(gedeutet["text"])
            anchor = gedeutet["question"]
            if gedeutet.get("kind"):
                gelesen.append(gedeutet["kind"])
    return teile, gelesen, anchor


def _deuter_antwort(conn, guess: dict, question: str, last_question: str | None,
                     last_answer: str | None = None, stimme=None,
                     quelle: str = "model:deuter", waage=None) -> dict | None:
    """Map an OPEN reading onto the Absichts-Raster and act from the known cell -- or
    climb ONE step to its Zwicky-Zelle (Blatt -> Zelle, nie tiefer -- eine Zelle ist schon die
    gröbste sinnvolle Einheit) -- or name honestly what GENUS read but cannot do yet. ``None``
    only when the reading is unklar/unbekannt or empty (then the caller falls through to the
    last word reading and the honest fallback).

    ``quelle`` ist die Herkunft der Lesart für die Belegungs-Kennzahl (record_reading) --
    normalerweise "model:deuter", aber die deterministische Gebärden-Schnellspur reicht
    "gebaerde" durch, damit die Statistik ehrlich bleibt (eine glasklar gelesene 👍 ist keine
    Modell-Vermutung)."""
    from genus import verstehen

    kind = (guess.get("absicht") or "").strip().lower()
    if not kind:
        return None
    # the graph is authoritative once sown; before the one clean seed-apply, the code-side
    # seed table keeps the mapping sane (same content, Quelle folgt mit der Saat)
    known = verstehen.kinds(conn) or {leaf for leaf, _ in verstehen.RASTER_SEED}
    if kind == "unklar" or kind not in known:
        # kein Freitext-Fallback mehr (Zwickys Kategorien sollen erschöpfend sein) -- ein
        # unbekanntes/unklares Blatt ändert ehrlich nichts, statt etwas zu erfinden. Aber es
        # wird GEZÄHLT (nur Struktur, nie Nutzer-Text): "unklar" ist ein blinder Fleck des
        # Rasters, und genau diese Zählung ist das Material für den VerstehensLuecke-Detector
        # (Selbst-Codieren Stufe 0 -- GENUS spürt selbst, wo sein Verstehen nicht hinreicht)
        _record_still(verstehen.record_reading, conn, "unklar", quelle)
        return None
    zellen = _handelbare_werkzeuge()
    zelle = verstehen.zelle_of(conn, kind)
    # Ein eigenes Blatt-Werkzeug ist die semantische Grenze; nur werkzeuglose Blätter landen weich.
    attempted = [kind] if kind in zellen else ([zelle] if zelle else [])
    hatte_handler = False
    for step in attempted:
        zellen_werkzeug = zellen.get(step)
        if zellen_werkzeug is None:
            continue
        hatte_handler = True
        # Signatur-Verhandlung wie bei :func:`_stimme_versucht`: nur Zellen, die das reichere
        # ``waage``-Organ annehmen (heute: definition), bekommen es -- die übrigen behalten
        # ihre schlanke, feste Signatur
        try:
            text = zellen_werkzeug.implementierung(conn, guess, question, last_question,
                                                   last_answer, stimme, waage=waage)
        except TypeError:
            text = zellen_werkzeug.implementierung(conn, guess, question, last_question,
                                                   last_answer, stimme)
        if text is not None:
            _record_still(verstehen.record_reading, conn, kind, quelle)
            # der Transparenz-Hinweis gilt NUR für eine echte Modell-Deutung -- eine
            # deterministisch gelesene Gebärde (quelle="gebaerde") bekommt keinen "vom
            # Sprachmodell gedeutet"-Zusatz, das wäre schlicht falsch
            marker = _DEUTED if (quelle == "model:deuter"
                                 and step not in ("tatsache", "merken")) else ""
            anchor = last_question if step in _ANCHOR_BLEIBT else question
            if not zellen_werkzeug.wortlautfest:
                # Stimme-Eignung folgt strukturell aus der Spec (Phase 3) -- keine zweite,
                # separat zu pflegende Menge mehr. Gerichtete Zelle -> Verbatim-Insel (Scheibe 2).
                insel = _kern_span(text) if kind in _GERICHTETE_ZELLEN else None
                text = _personalisiert(conn, question, text, stimme, marker, kern=insel)
            elif marker and marker not in text:
                # die Meta-Zellen bauen auf last_answer auf, das oft schon einen Hinweis trägt
                # (Nochmal/Ausführlicher wiederholen ihn wörtlich mit) -- nie doppelt anhängen
                text = text + marker
            return {"text": text, "question": anchor, "kind": kind}
    if hatte_handler:
        return None   # capability exists but nothing resolved here -- fail safe, never claim inability
    # known cell, no capability anywhere up the chain: say so, honestly -- and count it,
    # because exactly these counts prioritise what gets built next
    _record_still(verstehen.record_reading, conn, kind, quelle)
    label = _ZELLEN_LABELS.get(kind, f"„{kind}“")
    return {"text": f"Ich lese das als {label} — das kann ich noch nicht. Ich habe es mir "
                    f"als Lücke gemerkt." + _luecken_vorschlag_hinweis(conn),
            "question": question, "kind": kind}


def _luecken_vorschlag_hinweis(conn) -> str:
    """Die gesprächsnahe Regung (Ronny, 2026-07-04/05): läuft genau dann, wenn ein
    gesprächsnaher Detektor sein Signal reif werden lässt (heute der Lücken-Detektor) --
    reißt die selbst-kalibrierte Schwelle, entsteht das Proposal SOFORT und das „Darf ich?"
    steht im selben Atemzug in der Antwort, statt bis zum Nacht-Scan zu warten. Darf nie
    eine Antwort kosten (still bei jedem Fehler); die Freigabe bleibt am Terminal (die
    Membran redet nur)."""
    try:
        from genus import experience
        ergebnis = experience.spontane_regung(conn)
    except Exception:
        return ""
    if not ergebnis or not ergebnis.get("proposal_id"):
        return ""
    return (f" Das kam jetzt so oft vor, dass ich daraus einen Vorschlag gemacht habe "
            f"(Proposal #{ergebnis['proposal_id']}) — Freigabe wie immer über "
            f"genus governance.")


def _komponiere(teile: list[str]) -> str:
    """Mehrere Segment-Antworten zu EINER Antwort -- der erste, bewusst einfache Auftritt des
    Antwort-Würfels (Ronnys Weiterdenken vom Verstehens-Würfel aus). Heute nur aneinandergereiht,
    keine stilistische Verschmelzung -- ein kleiner, ehrlicher erster Schritt, kein Anspruch auf
    das letzte Wort in Sachen Formulierung. Ein Transparenz-Hinweis (Deuter/Stimme), den JEDES
    Segment einzeln trägt, muss in der zusammengesetzten Antwort nicht mehrfach auftauchen --
    einmal am Ende genügt, um "nie stillschweigend" einzulösen, ohne redundant zu wirken."""
    text = " ".join(t for t in teile if t)
    for marker in (_DEUTED, _STIMME_TAG):
        n = text.count(marker)
        if n > 1:
            text = text.replace(marker, "", n - 1)
    return text


def _anschluss_beiwerk(conn, question: str, aktiv: bool) -> tuple[str, str | None]:
    """Die Antizipation als Beiwerk der Antwort (Antwort-Komposition, Achse Nutzer&Service):
    nach einer beantwortbaren Konzept-Antwort EIN graph-verifiziertes Anschluss-Angebot.
    Kreuz-Konsistenz an EINER Stelle (``antwort.belegung``): nur auf dem Gesprächspfad
    (``aktiv``) und nur, wenn die Belegung Rückfragen zulässt (neugier · nicht knapp,
    Rollen-gepinnt -- Wache/knapp ⇒ keins). Gibt ``(" " + Angebot, Anschluss-Frage)`` oder
    ``("", None)``, wenn nichts Anknüpfbares vorliegt (nichts erfunden)."""
    if not aktiv:
        return "", None
    from genus import antwort as _antwort

    if not _antwort.belegung(conn, "plausch")["beiwerk_rueckfrage"]:
        return "", None
    a = answer(conn, question)
    if not a.get("found") or not a.get("concept"):
        return "", None
    ang = antizipation(conn, a)
    if ang is None:
        return "", None
    return " " + ang["text"], ang["frage"]


_KORREKTUR_CUE = re.compile(
    r"^\s*falsch\s+(?:verstanden|gedeutet)\s*(?::\s*([\wäöüß-]+))?\s*[.!?]*\s*$",
    re.IGNORECASE | re.UNICODE,
)


def korrektur_cue(question: str) -> tuple[bool, str | None]:
    """Der ENGE Korrektur-Kanal (Phase 3 Scheibe 3, Naht 1): exakt „falsch verstanden"
    oder „falsch gedeutet", optional mit „: <blatt>" (dem exakten Blattnamen dessen, was
    gemeint war). Bewusst fast deutungsfrei -- eine Freitext-Korrektur müsste durch
    genau den Klassifikator, der eben danebengegriffen hat (zirkulär); die exakte
    Kurzform braucht kein Modell. Ein längerer Satz („das hast du falsch verstanden,
    glaube ich") ist KEIN Cue -- er läuft den normalen Weg."""
    m = _KORREKTUR_CUE.match(question)
    if not m:
        return (False, None)
    richtig = m.group(1)
    return (True, richtig.lower() if richtig else None)


def _korrektur_antwort(conn, letzte_lesarten: list[str], richtig: str | None) -> str:
    """Nimmt die Korrektur an: jede Lesart des letzten Zugs wird als Fehlgriff festgehalten
    (nur Struktur, nie Text), mit ``richtig`` zusätzlich die gerichtete Verwechslung.
    Die Antwort benennt ehrlich, was korrigiert wurde."""
    from genus import verstehen

    bekannt = verstehen.kinds(conn) or {leaf for leaf, _ in verstehen.RASTER_SEED}
    ziel = richtig if richtig in bekannt else None
    for kind in letzte_lesarten:
        _record_still(verstehen.record_fehlgriff, conn, kind, ziel, "ronny")
    gelesen = " und ".join(f"„{k}“" for k in letzte_lesarten)
    text = (f"Danke für die Korrektur — ich hatte das als {gelesen} gelesen. "
            f"Den Fehlgriff habe ich mir gemerkt.")
    if ziel:
        text += f" Gemeint war „{ziel}“ — auch das habe ich festgehalten."
    elif richtig:
        text += f" („{richtig}“ kenne ich allerdings nicht als Lesart.)"
    return text


def respond_with_deuter(conn, question: str, last_question: str | None = None,
                         deuter=None, stimme=None, last_answer: str | None = None,
                         verlauf: list[dict] | None = None,
                         letzte_lesarten: list[str] | None = None,
                         letzter_anschluss: str | None = None, waage=None) -> dict:
    """The full Verstehens-Würfel for the conversational channel: Rituale -> Muster-Zellen ->
    offene Deuter-SEGMENTIERUNG (eine Nachricht kann mehrere Sprechhandlungen enthalten, ISO
    24617-2 -- jedes Segment aufs Raster abgebildet, is_a-Fallback GENAU einen Schritt,
    ehrliche Benennung) -> letzte Wort-Lesart -> ehrlicher Rest. The Deuter now runs BEFORE the
    greedy word reading (the 2026-07-02 bug class); the word reading remains as the final
    reading when the model is absent or reads nothing actionable. Known-cell readings are
    recorded as pure structure (Belegungs-Kennzahl); the user's words are never stored.

    ``deuter(question)`` gibt eine LISTE von Segment-Lesarten zurück (ein bare dict wird
    grosszügig als Ein-Segment-Liste behandelt, für Aufrufer/Tests, die noch die alte Form
    nutzen). Jedes Segment wird einzeln über :func:`_deuter_antwort` gelöst; die Teil-Antworten
    werden über :func:`_komponiere` zu einer zusammengefügt.

    When a ``stimme`` callable is given, every narrate-style factual answer -- Muster/Wort AND
    the Deuter-driven cells whose Werkzeug-Spec says ``wortlautfest=False`` (definition/
    beziehung/vergleich/grammatik/frage-begriff; a plain "Was ist ein Hund?" reaches the Deuter
    now that it runs before the word reading, so it must be covered too) -- is offered to it
    for a more natural rephrase (:func:`_stimme_versucht`), always safe to fall back, never
    required. The SAME
    answers, on the conversational path only (``deuter is not None``), are also offered a
    Notiz-Bezug (:func:`_notiz_bezug`, Personen-Gedächtnis Scheibe 2) -- a personal note woven
    in beiläufig when its text shares a word with the question. Multi-line/structured answers
    (Nachfrage-Herleitung, Erinnerungen, offene Fragen) are deliberately left alone by both.

    ``last_answer`` (optional, the EXACT text ``respond_with_deuter`` returned last turn) feeds
    the Antwort-Würfel's Meta-Zellen (kuerzer/ausfuehrlicher/anders-erklaeren/wiederholen) --
    a caller threads ``result["text"]`` forward the same way it threads ``result["question"]``
    forward as the next call's ``last_question``.

    ``deuter=None``/``stimme=None`` degrades to the deterministic Würfel half and behaves
    exactly like ``respond_in_conversation`` (as long as ``verlauf`` is also omitted).

    ``verlauf`` (optional, Mehr-Zug-Arbeitsgedächtnis): turns BEFORE the immediately previous
    one (that one stays reachable via ``last_question``/``last_answer`` as always). A question
    containing „von vorhin"/„von eben" (:func:`is_backreference`) re-answers the most recent
    earlier question GENUS can still answer, named honestly as a retrace -- never a guessed
    word-substitution.

    ``letzte_lesarten`` (optional, der Korrektur-Kanal): die Raster-Lesarten, auf die der
    LETZTE Zug gehandelt hat (der Aufrufer fädelt ``result["gelesen"]`` genauso weiter wie
    question/answer). Ein exaktes „falsch verstanden" hält sie als Fehlgriff fest --
    deterministisch, VOR jeder Deutung, damit die Korrektur nie selbst durch den
    Klassifikator muss, der eben danebengriff (Naht 1).

    ``letzter_anschluss`` (optional, die Antizipation): die im LETZTEN Zug angebotene, schon
    verifizierte Anschlussfrage (der Aufrufer fädelt ``result["anschluss"]`` genauso weiter
    wie question/gelesen). Kommt jetzt eine knappe Zustimmung (:func:`_ist_zustimmung`), wird
    genau diese Frage beantwortet -- VOR jeder Deutung, damit ein „ja" nie durch den
    Klassifikator muss. Eine Konzept-Antwort trägt umgekehrt ihr eigenes Angebot in
    ``result["anschluss"]`` (:func:`_anschluss_beiwerk`, kalibriert über ``antwort.belegung``)."""
    from genus import verstehen

    ist_korrektur, richtig = korrektur_cue(question)
    if ist_korrektur:
        if letzte_lesarten:
            text = _korrektur_antwort(conn, letzte_lesarten, richtig)
            anchor = last_question or question
            return {"text": text, "question": anchor, "gelesen": []}
        return {"text": "Da war keine letzte Deutung, die ich korrigieren könnte — "
                        "die Korrektur bezieht sich immer auf meine vorige Antwort.",
                "question": question, "gelesen": []}
    # Die ANTIZIPATION eingelöst: stand im letzten Zug ein Anschluss-Angebot aus und kommt
    # jetzt eine knappe Zustimmung, wird GENAU diese verifizierte Frage beantwortet -- vor
    # jeder Deutung, damit ein „ja" nie durch den Klassifikator muss (und nie ins Leere läuft).
    # Kein neues Angebot aus der Einlösung (keine endlose Angebots-Kette; ein Blick, kein Sog).
    if letzter_anschluss and _ist_zustimmung(question):
        text = _stimme_versucht(conn, respond(conn, letzter_anschluss, waage=waage), stimme)
        return {"text": text, "question": letzter_anschluss, "gelesen": []}
    if last_question and is_why_followup(question):
        text = "\n".join(render_trace(conn, trace(conn, last_question)))
        return {"text": text, "question": last_question}
    if verlauf and is_backreference(question):
        frueher = _fruehere_frage_mit_bekanntem_begriff(conn, verlauf)
        if frueher is not None:
            text = respond(conn, frueher, waage=waage) + _BACKREF_TAG.format(frueher)
            return {"text": text, "question": frueher}
    text = _ritual_antwort(conn, question)
    if text is not None:
        return {"text": text, "question": question}
    from genus import antwort as _antwort
    muster = _muster_antwort(conn, question, _antwort.belegung(conn, "plausch"))
    if muster is not None:
        if deuter is not None:   # recording/notes only on the conversational (bot) path, not
            # for the CLI -- Stimme itself stays independent of deuter (always offered when given)
            _record_still(verstehen.record_reading, conn, muster[1], "muster")
        # dieselbe Eignungs-Prüfung wie beim Deuter-Pfad, jetzt strukturell aus der
        # Werkzeug-Spec (Phase 3): eine Zelle ohne Registry-Eintrag (z.B. "berechnen",
        # exakte Formel) ist automatisch wortlautfest -- stimme_geeignet ist dann False,
        # niemand kann die Eignung mehr an einer zweiten Stelle vergessen
        registriere_zellen()
        from genus import werkzeug as _werkzeug
        if _werkzeug.stimme_geeignet(f"{ZELLE_PREFIX}{muster[1]}"):
            # gerichtete Zelle -> ihr Fakt-Satz ist eine Verbatim-Insel (Richtung kann nicht kippen)
            kern = _kern_span(muster[0]) if muster[1] in _GERICHTETE_ZELLEN else None
            text = _stimme_versucht(conn, muster[0], stimme, kern=kern)
        else:
            text = muster[0]
        if deuter is not None:
            text += _notiz_bezug(conn, question) or ""
        return {"text": text, "question": question, "gelesen": [muster[1]]}
    if deuter is not None:
        # DIE GEBÄRDEN-SCHNELLSPUR (Proposal #14): eine reine Emoji-Nachricht wird gläsern und
        # modellfrei gelesen, VOR dem Deuter -- ein 👍 ist eindeutiger als jeder Modell-Tipp.
        # Ehrliche Herkunft "gebaerde"; keine Anschlussfrage (eine warme Floskel braucht keinen
        # Sog). Nicht als Gebärde erkannt -> None -> der Deuter läuft wie bisher.
        from genus import gebaerde
        gesten = gebaerde.lies(question)
        if gesten is not None:
            teile, gelesen, anchor = _segmente_loesen(
                conn, gesten, question, last_question, last_answer, stimme, "gebaerde",
                waage=waage)
            if teile:
                return {"text": _komponiere(teile), "question": anchor, "gelesen": gelesen}
        segmente = deuter(question)
        if isinstance(segmente, dict):
            segmente = [segmente]
        if segmente is not None:   # der Deuter LIEF -- auch eine leere Liste zählt als Lauf
            teile, gelesen, anchor = _segmente_loesen(
                conn, segmente, question, last_question, last_answer, stimme, "model:deuter",
                waage=waage)
            if teile:
                bei, anschluss = _anschluss_beiwerk(conn, question, deuter is not None)
                res = {"text": _komponiere(teile) + bei, "question": anchor, "gelesen": gelesen}
                if anschluss:   # der Schlüssel erscheint nur, wenn es wirklich ein Angebot gibt
                    res["anschluss"] = anschluss
                return res
            # der Deuter lief und fand ehrlich nichts -- kein Rückfall auf den gierigen
            # Wort-Lookup mehr (siehe _NICHT_VERSTANDEN-Kommentar oben). Gezählt wird der
            # Fall trotzdem (Struktur, nie Text): auch ein leerer Lauf ist ein blinder Fleck
            if not segmente:
                _record_still(verstehen.record_reading, conn, "unklar", "model:deuter")
            return {"text": _NICHT_VERSTANDEN + _luecken_vorschlag_hinweis(conn),
                    "question": question}
    text = _wort_antwort(conn, question, waage=waage)
    if text is not None:
        text = _stimme_versucht(conn, text, stimme)
        if deuter is not None:
            text += _notiz_bezug(conn, question) or ""
        bei, anschluss = _anschluss_beiwerk(conn, question, deuter is not None)
        res = {"text": text + bei, "question": question}
        if anschluss:
            res["anschluss"] = anschluss
        return res
    return {"text": _UNKNOWN_FALLBACK, "question": question}


# --- the provenance trace ("genus why") ------------------------------------------------
#
# The thesis made tangible: every answer is rückführbar auf seine Herkunft. `trace` runs the
# same routing as `ask` (relational, then word), but instead of the fluent voice it lays open
# the *derivation* -- each edge with its source and read-time trust, and (for a chain) the
# composed trust = the weakest premise. Nothing is a black box; the reasoning can be inspected.

def trace(conn, question: str) -> dict:
    """The full provenance behind what ``ask`` would answer -- a relation's premise chain, or
    a word's grounding (expresses · meaning · is_a). ``{kind: "none"}`` if there's nothing to show."""
    rel = relate(conn, question)
    if rel.get("relational"):
        return {"kind": "relation", **rel}
    a = answer(conn, question)
    if a.get("found"):
        return {"kind": "word", "answer": a}
    return {"kind": "none", "question": question}


def _edge(conn, subject: str, predicate: str, object_: str, source: str) -> str:
    t = sources.source_trust(conn, source)
    return (f"{sources.display(conn, subject)} —{predicate}→ {sources.display(conn, object_)}"
            f"   ← {source} (Vertrauen {t:.2f})")


def render_trace(conn, t: dict) -> list[str]:
    """The trace as human-readable lines -- glass-box, straight from the recorded graph."""
    if t["kind"] == "relation":
        if t["verdict"] != "yes":
            return [f"Nichts zu belegen: GENUS findet keine is_a-Verbindung von »{t['subject']}« "
                    f"zu »{t['object']}«."]
        lines = [f"Warum »{t['subject']}« zu »{t['object']}« zählt — die Herleitung:"]
        lines += ["  " + _edge(conn, p["subject"], p["predicate"], p["object"], p["source"])
                  for p in t["chain"]]
        lines.append(f"  ⇒ Vertrauen {t['trust']:.2f} — die schwächste Prämisse der Kette.")
        return lines
    if t["kind"] == "word":
        a = t["answer"]
        key = f"{a['word']}@de"
        lines = [f"Woher GENUS »{a['word']}« kennt — die Herkunft:"]
        for r in sources.relations(conn, subject=key, predicate=sources.EXPRESSES):
            lines.append("  " + _edge(conn, key, "expresses", r["object"], r["source"]))
        for pred in ("primary_gloss", "defined_as"):
            for r in sources.relations(conn, subject=key, predicate=pred):
                trust = sources.source_trust(conn, r["source"])
                lines.append(f"  Bedeutung »{r['object']}«   ← {r['source']} (Vertrauen {trust:.2f})")
        if a.get("concept"):
            for r in sources.relations(conn, subject=a["concept"], predicate="is_a"):
                lines.append("  " + _edge(conn, a["concept"], "is_a", r["object"], r["source"]))
        return lines
    return [f"Dazu kann GENUS nichts belegen — es kennt kein Wort in »{t['question']}«."]
