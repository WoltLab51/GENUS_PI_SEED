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

_WORD = re.compile(r"[\wäöüÄÖÜß]+", re.UNICODE)


def _objects(conn, form: str, predicate: str) -> list[str]:
    return [r["object"] for r in sources.relations(conn, subject=f"{form}@de", predicate=predicate)]


def _prominent_concept(conn, form: str) -> str | None:
    """The concept a word most prominently expresses -- lives in ``sources`` now
    (Phase 0 der Ziel-Architektur: das Geteilte wandert nach unten); thin delegation
    kept for the internal callers."""
    return sources.prominentes_konzept(conn, form)


def _known(conn, form: str) -> bool:
    return sources.bekanntes_wort(conn, form)


def _last_known_word(conn, question: str) -> str | None:
    """The last word in ``question`` GENUS has anything recorded about (as written or
    capitalised) -- in "Was ist ein X?" the asked-about word comes last."""
    found: str | None = None
    for tok in _WORD.findall(question):
        for form in (tok, tok[:1].upper() + tok[1:]):
            if _known(conn, form):
                found = form
                break
    return found


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


def answer(conn, question: str) -> dict:
    """Answer a question about a word GENUS knows; ``{found: False}`` if it knows no word in it.

    Picks the *last* known content word (in "Was ist ein X?" the asked-about word comes last),
    each tried as written and capitalised (German nouns). A noun usually resolves to a CONCEPT
    (meaning + is_a + other languages); a verb/adjective often has no concept node but still
    carries its glosses + part of speech -- answered word-level so the companion reaches beyond
    nouns. A real parse of the question is the LLM's job at the edge later.
    """
    found = _last_known_word(conn, question)
    if found is None:
        return {"found": False, "question": question}

    base = {"found": True, "word": found, "languages": [],
            "pos": sorted(set(_objects(conn, found, "pos")))}
    qid = _prominent_concept(conn, found)
    if qid is not None:
        c = sources.concept_meaning(conn, qid)
        langs = list(dict.fromkeys(  # other-language forms, order-preserving dedup
            w.rsplit("@", 1)[0] for w in c["words"] if not w.endswith("@de")))
        return {**base, "concept": qid, "label": c["label"], "meaning": c["meaning"],
                "is_a": [sources.display(conn, p) for p in c["is_a"]], "languages": langs[:6],
                **_meaning_grounding(conn, found, qid, c["meaning"])}
    # word-level (e.g. a verb): its own glosses + part of speech, no concept node yet
    meaning = _objects(conn, found, "primary_gloss") or _objects(conn, found, "defined_as")
    return {**base, "concept": None, "label": found, "meaning": meaning, "is_a": [],
            **_meaning_grounding(conn, found, None, meaning)}


def _meaning_grounding(conn, word: str, qid: str | None, meaning) -> dict:
    """How well the SHOWN meaning is backed: its read-time relation-confidence and how many
    independent sources carry it. Tiers are structural, relative to the trust seed -- no new
    constant: below seed = a weak lone witness (e.g. only the capped model bridge), above seed
    = independent corroboration. Empty when no edge matches (then the voice stays neutral --
    missing metadata is not evidence of weakness)."""
    gloss = meaning[0] if meaning else None
    if not gloss:
        return {}
    best: dict | None = None
    candidates = [(f"{word}@de", "primary_gloss"), (f"{word}@de", "defined_as")]
    if qid:
        candidates.append((qid, "defined_as"))
    for subject, predicate in candidates:
        c = sources.relation_confidence(conn, subject, predicate, gloss)
        if c["n_sources"] and (best is None or c["confidence"] > best["confidence"]):
            best = c
    if best is None:
        return {}
    return {"meaning_confidence": best["confidence"], "meaning_sources": best["n_sources"]}


_POS_DE = {"noun": "Substantiv", "verb": "Verb", "adjective": "Adjektiv", "adverb": "Adverb"}
_LABEL = re.compile(r"^Q\d+\s*\((.*)\)$")
_BARE_QID = re.compile(r"^Q\d+$")   # a concept with no label in any shown language


def _join_de(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " und " + items[-1]


def narrate(a: dict) -> str:
    """A fluent, deterministic German answer composed from the verified facts -- a glass-box
    voice (no generative model, nothing invented). The structure stays queryable behind it."""
    if not a.get("found"):
        return "Dazu kennt GENUS noch kein Wort."
    pos = a.get("pos") or []
    tag = f" ({_join_de([_POS_DE.get(p, p) for p in pos])})" if pos else ""
    if a["meaning"]:
        sentence = f"Unter »{a['word']}«{tag} versteht GENUS: {a['meaning'][0].rstrip('.')}"
    else:
        sentence = f"»{a['word']}«{tag} kennt GENUS, aber eine Bedeutung ist noch nicht erschlossen"
    named = [_LABEL.sub(r"\1", x) for x in a["is_a"] if not _BARE_QID.match(x)]
    if named:   # only human-nameable parents in the voice; a bare Q-id says nothing to a person
        # in Guillemets -- jeder benannte Begriff ist ein ANKER für die Stimme (Anführungs-
        # zeichen-Wörter müssen wortwörtlich überleben). Live gefunden (2026-07-03): ungeschützt
        # wurde "Kernobst" beim Umformulieren zu "Kernaubere" -- eine echte, unbemerkte
        # Faktenverfälschung, weil nur der Kopf-Begriff geschützt war.
        sentence += f"; es zählt zu {_join_de([f'»{parent}«' for parent in named])}"
    sentence += "."
    # Tiered honesty, relative to the trust seed (no new constant): a meaning carried only by
    # a below-seed witness (e.g. the capped model bridge) is said WITH the doubt; independent
    # corroboration may say so; the ordinary single-source case stays neutral -- hedging
    # everything at seed would be crying wolf, not honesty.
    conf, n = a.get("meaning_confidence"), a.get("meaning_sources", 0)
    if conf is not None and conf < sources.SOURCE_TRUST_SEED:
        sentence += " Bei dieser Bedeutung bin ich noch unsicher — sie ist erst schwach belegt."
    elif n >= 2:
        sentence += " Diese Bedeutung ist mehrfach unabhängig belegt."
    if a["languages"]:
        sentence += f" In anderen Sprachen: {', '.join(f'»{w}«' for w in a['languages'][:4])}."
    return sentence


def _konzept_name(conn, node: str) -> str | None:
    """Der menschliche Name eines Graph-Knotens für die Vertiefung -- ``None``, wenn es
    keinen gibt (ein blanker Q-Knoten sagt einem Menschen nichts; nie kryptisch)."""
    anzeige = sources.display(conn, node)
    m = re.search(r"\(([^)]+)\)$", anzeige)
    if m:
        return m.group(1)
    if "@" in anzeige:
        return anzeige.rsplit("@", 1)[0]
    return None


# Die verbindenden (dynamischen) Prädikate → nativer Satz. Dieselben Prädikatnamen, die der
# Konzept-Ernter (deploy/observe_konzept.sh) aus Wikidata zieht und die inference.py als
# transitiv kennt (is_a, part_of). Merkmal erst wenn erkannt + notwendig: genau die, die eine
# Denkweise füttern (Teil-Ganzes / Kausal / Zweck / Stoff).
_DYNAMISCHE_KANTEN: tuple[tuple[str, str], ...] = (
    ("part_of", "»{w}« ist Teil von {o}."),
    ("has_part", "Zu »{w}« gehören: {o}."),
    ("made_of", "»{w}« besteht aus {o}."),
    ("used_for", "»{w}« wird verwendet für {o}."),
    ("causes", "»{w}« verursacht {o}."),
    ("caused_by", "»{w}« wird verursacht von {o}."),
)


def vertiefung(conn, a: dict) -> list[str]:
    """Die VERTIEFUNGS-KOMPOSITION (Antwort-Würfel, Umfang „ausführlich" -- Ronnys Frage
    2026-07-05: „wie schreibt GENUS so richtig schön lange Texte?"): Länge kommt aus
    INHALT, nie aus Worten. Jeder Satz hier existiert nur, wenn das Material im Graphen
    liegt -- eine weitere Bedeutung, die Geschwister unter demselben Elternteil, die
    Leiter eine Stufe hinauf, die Quellen namentlich. Rein deterministisch, nichts
    erfunden; jeder benannte Begriff steht in »« (Anker für die Stimme-Leine)."""
    saetze: list[str] = []
    if len(a.get("meaning") or []) > 1:
        saetze.append(f"Daneben kenne ich eine weitere Bedeutung von »{a['word']}«: "
                      f"{a['meaning'][1].rstrip('.')}.")
    qid = a.get("concept")
    if not qid:
        return saetze
    for eltern_kante in sources.relations(conn, subject=qid, predicate="is_a"):
        eltern = eltern_kante["object"]
        eltern_name = _konzept_name(conn, eltern)
        if eltern_name is None:
            continue
        geschwister: list[str] = []
        for r in sources.relations(conn, predicate="is_a", object=eltern):
            if r["subject"] == qid:
                continue
            name = _konzept_name(conn, r["subject"])
            if name and name not in geschwister:
                geschwister.append(name)
            if len(geschwister) == 3:
                break
        if geschwister:
            saetze.append(f"Unter »{eltern_name}« kenne ich außerdem: "
                          + _join_de([f"»{g}«" for g in geschwister]) + ".")
        gross = [n for n in (_konzept_name(conn, r["object"]) for r in
                             sources.relations(conn, subject=eltern, predicate="is_a")) if n]
        if gross:
            saetze.append(f"»{eltern_name}« zählt wiederum zu "
                          + _join_de([f"»{g}«" for g in gross[:2]]) + ".")
        break   # EIN Elternteil vertieft -- die Vertiefung ist ein Blick, kein Katalog
    # Die DYNAMISCHE Schicht (2026-07-05, Methoden-Landkarte + Material-Wende): neben dem
    # statischen is_a jetzt die VERBINDENDEN Relationen -- Teil-Ganzes, Kausal, Zweck. Sie
    # sagen, was ein Ding HAT, WOFÜR es ist, was es BEWIRKT -- der Rohstoff, auf dem die
    # nächsten Denkweisen laufen (Deduktion chained part_of schon). Nur benannte Ziele
    # (nie kryptisch); jeder Begriff ein Stimme-Anker in »«.
    for praedikat, vorlage in _DYNAMISCHE_KANTEN:
        ziele: list[str] = []
        for r in sources.relations(conn, subject=qid, predicate=praedikat):
            name = _konzept_name(conn, r["object"])
            if name and name not in ziele:
                ziele.append(name)
            if len(ziele) == 3:
                break
        if ziele:
            saetze.append(vorlage.format(w=a["word"],
                                         o=_join_de([f"»{z}«" for z in ziele])))
    # Ein konkretes BEISPIEL macht die abstrakte Definition greifbar (Antwort-Komposition
    # 2026-07-07, Substanz-Achse): die stärkste noch fehlende Zutat. Rückwärts gelesen -- ein
    # benanntes X mit X -instance_of-> qid; nur wenn echt vorhanden, in »« als Stimme-Anker.
    beispiel = _beispiel(conn, qid)
    if beispiel:
        saetze.append(f"Ein Beispiel dafür ist »{beispiel}«.")
    lexem = f"{a['word']}@de"
    quellen = sorted(
        {r["source"] for r in sources.relations(conn, subject=lexem, predicate="expresses")}
        | {r["source"] for r in sources.relations(conn, subject=lexem, predicate="primary_gloss")}
    )
    if len(quellen) >= 2:
        saetze.append(f"Meine Quellen zu »{a['word']}«: {', '.join(quellen)}.")
    return saetze


def _beispiel(conn, qid: str) -> str | None:
    """Ein konkretes Beispiel für ein Konzept -- das erste benennbare X mit
    ``X -instance_of-> qid`` (die RÜCKWÄRTS-Richtung von Wikidata P31, geerntet von
    observe_konzept.sh / backfill_konzepte.py). ``instance_of`` ist ein EIGENES,
    nicht-transitives Prädikat: die Instanz ist KEIN Unterbegriff, es läuft nie in die
    is_a-Inferenz (kein transitives Prädikat), es wird nur hier gelesen. Nur benannte
    Instanzen, nie ein blanker Q-Knoten -- ehrlich None, wenn keine Instanz bekannt ist."""
    for r in sources.relations(conn, predicate="instance_of", object=qid):
        name = _konzept_name(conn, r["subject"])
        if name:
            return name
    return None


# --- die ANTIZIPATION: das proaktive Anschluss-Angebot ---------------------------------
#
# Die zuvorkommende Zutat der Antwort-Komposition (Ronny 2026-07-08, „mach die Antizipation"):
# nach einer Konzept-Antwort bietet GENUS die WAHRSCHEINLICHE Anschlussfrage an -- aber die
# eiserne Disziplin ist Treue VOR Freundlichkeit: es wird NUR angeboten, was GENUS auch
# wirklich beantworten kann. Das Angebot entsteht aus einer echten dynamischen Kante (nichts
# erfunden) UND wird vor dem Anbieten verifiziert (:func:`_erklaerbar_und_eindeutig` löst die
# Anschlussfrage probehalber auf -- gegen die exakte Kanten-Ziel-Qid, damit das spätere „ja"
# genau das angebotene Konzept trifft). Genau EIN Angebot, das schwächste-relevanteste zuerst.
# Sagt der Nutzer im nächsten Zug „ja", löst :func:`respond_with_deuter` es ein -- sonst
# bricht das Service-Gefühl (ein „ja" ins Leere wäre schlimmer als kein Angebot).
_ANTIZIPATION_KANTEN = ("causes", "used_for", "has_part", "part_of", "made_of", "caused_by")


def _erklaerbar_und_eindeutig(conn, frage: str, ziel_qid: str) -> bool:
    """Kann GENUS diese Anschlussfrage substantiell UND eindeutig beantworten? -- zwei Leinen
    in einer: (1) EINDEUTIG: die Frage muss sich beim Auflösen GENAU auf das gemeinte Konzept
    ``ziel_qid`` zurückführen; sonst zerfiele ein Mehrwort-Label auf sein letztes Wort oder ein
    Homonym wechselte die Bedeutung -- und das spätere „ja" beantwortete ein ANDERES Konzept als
    angeboten. (2) SUBSTANTIELL: es muss eine echte Definition herauskommen -- eine Bedeutung
    ODER ein BENANNTER is_a-Platz; ein bloßer Q-Eltern-Knoten zählt NICHT, denn ``narrate``
    spricht ihn gar nicht aus (sonst liefe das Angebot in „eine Bedeutung ist noch nicht
    erschlossen"). Geprüft wird genau der String, den das spätere ``respond(frage)`` bekommt --
    dieselbe Auflösung, also hier schon die Wahrheit von dort. Treue vor Freundlichkeit."""
    a = answer(conn, frage)
    if a.get("concept") != ziel_qid:
        return False
    return bool(a.get("meaning") or any(not _BARE_QID.match(x) for x in a.get("is_a") or []))


def antizipation(conn, a: dict) -> dict | None:
    """Die wahrscheinliche Anschlussfrage zu einer schon gegebenen Konzept-Antwort ``a`` --
    das erste über eine dynamische Kante verbundene, benannte Konzept, das GENUS auch
    ERKLÄREN kann (verifiziert gegen die exakte Kanten-Ziel-Qid, nicht gegen das nachgeparste
    Label). Rückgabe ``{"text", "frage"}`` (das Angebot + die konkrete Frage, die ein „ja"
    einlöst) oder ``None`` -- nichts Anknüpfbares, nichts erfunden."""
    qid = a.get("concept")
    wort = a.get("word")
    if not qid:
        return None
    for praedikat in _ANTIZIPATION_KANTEN:
        for r in sources.relations(conn, subject=qid, predicate=praedikat):
            y_name = _konzept_name(conn, r["object"])
            if not y_name or y_name == wort:
                continue
            frage = f"Was ist {y_name}?"
            if _erklaerbar_und_eindeutig(conn, frage, r["object"]):
                return {"text": f"Wenn du magst, erkläre ich dir noch, was »{y_name}« ist.",
                        "frage": frage}
    return None


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


# --- relational questions ("Ist ein X ein Y?") -----------------------------------------
#
# A yes/no is_a question, answered by the *existing* inference primitive: map X to its
# concept(s), walk the concept-level is_a hierarchy (sense-coherent by construction), and
# check whether Y is among the ancestors. The answer is a derived edge, so it carries its
# whole premise chain -- glass-box: GENUS shows *the way* from X to Y, and the trust is the
# weakest premise. No model, nothing invented; the reasoning is the answer.

_ART = r"(?:einen|einer|eine|ein|der|die|das|den|dem)"
_FILL = r"(?:(?:eigentlich|denn|jetzt|nochmal|noch|so|überhaupt|gerade|wirklich)\s+)*"
_TERM = r"([A-Za-zäöüÄÖÜß]+)"
_REL_PATTERNS = [
    re.compile(r"\bist\s+" + _FILL + _ART + r"?\s*" + _TERM + r"\s+" + _FILL + _ART + r"?\s*art(?:\s+von)?\s+" + _TERM, re.I),
    re.compile(r"\bist\s+" + _FILL + _ART + r"?\s*" + _TERM + r"\s+" + _FILL + _ART + r"\s+" + _TERM, re.I),
    re.compile(r"\bsind\s+" + _FILL + _TERM + r"\s+" + _FILL + _ART + r"?\s*" + _TERM, re.I),
    re.compile(r"\bz(?:ä|ae|a)hlt\s+" + _FILL + _ART + r"?\s*" + _TERM + r"\s+" + _FILL + r"zu\s+(?:den|der|die|das)?\s*" + _TERM, re.I),
]
_LABEL_IN = re.compile(r"^Q\d+\s*\((.*)\)$")


def _forms(tok: str):
    """The token as written and capitalised -- German nouns are stored capitalised."""
    return (tok, tok[:1].upper() + tok[1:])


def _concept_form(conn, tok: str) -> str | None:
    """The written/capitalised form of ``tok`` that GENUS knows as a concept, if any."""
    for form in _forms(tok):
        if _prominent_concept(conn, form) is not None:
            return form
    return None


def _concepts_of(conn, tok: str) -> tuple[set[str], str | None]:
    """All concepts a word expresses, and the known form -- for the object side of the question."""
    for form in _forms(tok):
        qids = {r["object"] for r in sources.relations(conn, subject=f"{form}@de", predicate=sources.EXPRESSES)}
        if qids:
            return qids, form
    return set(), None


def _label(conn, node: str) -> str:
    """A concept rendered as a plain German word (not a Q-id) for a readable path -- the
    canonical label if the graph has one, else any German word expressing it, else the node."""
    shown = sources.display(conn, node)
    m = _LABEL_IN.match(shown)
    if m:
        return m.group(1)
    if shown != node:              # display appended something in another form
        return shown
    words = sources.lexicalize(conn, node, "de")   # a bare concept id -> lexicalize it
    return words[0] if words else node


def _collapse(path: list[str]) -> list[str]:
    out: list[str] = []
    for p in path:
        if not out or out[-1] != p:
            out.append(p)
    return out


def _relate_terms(conn, x_tok: str, y_tok: str) -> dict:
    """The core of a yes/no is_a question once the two terms are already known -- shared by the
    regex-triggered :func:`relate` and the Deuter's free-form ``relation`` guess (see
    :func:`respond_with_deuter`). ``{relational: False}`` if either term doesn't resolve."""
    x_form = _concept_form(conn, x_tok)
    y_concepts, y_form = _concepts_of(conn, y_tok)
    if x_form is None or not y_concepts:
        return {"relational": False}
    ancestors = inference.infer_lexeme(conn, x_form, "is_a", "de")
    hits = [a for a in ancestors if a["object"] in y_concepts]
    if hits:
        best = min(hits, key=lambda a: len(a["chain"]))
        return {"relational": True, "verdict": "yes", "subject": x_form, "object": y_form,
                "target": best["object"], "trust": best["trust"], "chain": best["chain"]}
    return {"relational": True, "verdict": "no_path", "subject": x_form, "object": y_form}


def relate(conn, question: str) -> dict:
    """Answer a yes/no is_a question from the graph via a fixed German phrasing;
    ``{relational: False}`` if the text doesn't match one (or names something GENUS can't
    resolve, so a plain word-lookup should try instead)."""
    for pattern in _REL_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        r = _relate_terms(conn, m.group(1), m.group(2))
        if r["relational"]:
            return r
    return {"relational": False}


def narrate_relation(conn, r: dict) -> str:
    """Fluent, deterministic German for a relational answer -- glass-box: the path is shown."""
    x, y = r["subject"], r["object"]
    if r["verdict"] == "yes":
        path = _collapse([x] + [_label(conn, p["object"]) for p in r["chain"]])
        s = f"Ja. »{x}« zählt zu »{y}«."
        if len(path) > 2:
            # jedes Zwischenglied in Guillemets -- derselbe Stimme-Anker-Schutz wie in narrate()
            s += f" Der Weg: {' → '.join(f'»{p}«' for p in path)}."
        return s + f" (Vertrauen {r['trust']:.2f} — aus dem Wissensgraphen hergeleitet, nicht behauptet.)"
    return (f"Nach allem, was GENUS weiß, nicht: es findet keine is_a-Verbindung von »{x}« zu "
            f"»{y}«. (Das heißt: unbekannt, nicht widerlegt.)")


# --- comparative questions ("Was haben X und Y gemeinsam?") ----------------------------
#
# The mirror of "ist ein X ein Y?": instead of asking whether one lies above the other, it
# finds where their is_a lines *meet* -- the shared ancestors, closest first. Pure reuse of
# infer_lexeme (both terms singular nouns, so no plural morphology), sense-coherent by
# construction, glass-box (the shared category is a real graph node).

_COMMON_PATTERNS = [
    re.compile(r"\bwas\s+haben\s+" + _ART + r"?\s*" + _TERM + r"\s+und\s+" + _ART + r"?\s*" + _TERM + r"\s+" + _FILL + r"gemeinsam", re.I),
    re.compile(r"\bwas\s+ist\s+" + _ART + r"?\s*" + _TERM + r"\s+und\s+" + _ART + r"?\s*" + _TERM + r"\s+" + _FILL + r"gemeinsam", re.I),
    re.compile(r"\bgemeinsam(?:keit(?:en)?)?\s+(?:von|zwischen)\s+" + _ART + r"?\s*" + _TERM + r"\s+und\s+" + _ART + r"?\s*" + _TERM, re.I),
    re.compile(r"\bwas\s+verbindet\s+" + _ART + r"?\s*" + _TERM + r"\s+und\s+" + _ART + r"?\s*" + _TERM, re.I),
]


def _ancestor_depths(conn, form: str) -> dict[str, int]:
    """{concept: closest chain-depth} — the word's own concept(s) (depth 0) plus every is_a
    ancestor, so two words' sets can be intersected to find where their lines meet."""
    depths: dict[str, int] = {}
    for expr in sources.relations(conn, subject=f"{form}@de", predicate=sources.EXPRESSES):
        depths.setdefault(expr["object"], 0)
    for a in inference.infer_lexeme(conn, form, "is_a", "de"):
        d = len(a["chain"])
        if depths.get(a["object"], 1 << 30) > d:
            depths[a["object"]] = d
    return depths


def _common_terms(conn, x_tok: str, y_tok: str) -> dict:
    """The core of a comparative question once the two terms are already known -- shared by the
    regex-triggered :func:`common` and the Deuter's free-form ``comparative`` guess.
    ``{common: False}`` if either term doesn't resolve to a concept."""
    x, y = _concept_form(conn, x_tok), _concept_form(conn, y_tok)
    if x is None or y is None:
        return {"common": False}
    dx, dy = _ancestor_depths(conn, x), _ancestor_depths(conn, y)
    ordered = sorted(set(dx) & set(dy), key=lambda c: dx[c] + dy[c])
    shared = [c for c in ordered if _label(conn, c) != c]   # only human-nameable categories
    return {"common": True, "found": bool(shared), "x": x, "y": y, "shared": shared}


def common(conn, question: str) -> dict:
    """The shared is_a ancestors of two words, closest first; ``{common: False}`` if not asked."""
    for pattern in _COMMON_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        r = _common_terms(conn, m.group(1), m.group(2))
        if r["common"]:
            return r
    return {"common": False}


def narrate_common(conn, r: dict) -> str:
    if not r["found"]:
        return f"GENUS findet keine gemeinsame Oberkategorie von »{r['x']}« und »{r['y']}«."
    labels = _collapse([_label(conn, c) for c in r["shared"]])[:3]
    # in Guillemets -- derselbe Stimme-Anker-Schutz wie in narrate()/narrate_relation()
    s = f"»{r['x']}« und »{r['y']}« haben gemeinsam: beide zählen zu »{labels[0]}«"
    if len(labels) > 1:
        s += f" (und weiter zu {_join_de([f'»{lbl}«' for lbl in labels[1:]])})"
    return s + "."


# --- grammatical gender questions ("Welches Geschlecht hat X?") ------------------------
#
# Known FACT beats induced RULE beats honest silence: if GENUS has actually recorded a noun's
# gender (from Wikidata), it reports that -- never a guess where a fact is held. Only for a
# noun with no recorded gender does it fall to the induced suffix rule (gender_rule.predict_gender,
# Phase B SYSTEME breadth), clearly labelled as inferred, not certain. A noun can legitimately
# carry more than one recorded gender (homonymous lexemes, e.g. "Messer") -- both are shown.

_GENDER_PATTERNS = [
    re.compile(r"\bwelches\s+geschlecht\s+hat\s+" + _FILL + _ART + r"?\s*" + _TERM, re.I),
    re.compile(r"\bwelchen\s+artikel\s+(?:hat|braucht)\s+" + _FILL + _ART + r"?\s*" + _TERM, re.I),
    re.compile(r"\bder,?\s*die\s+oder\s+das\s+" + _TERM, re.I),
]


def _gender_term(conn, tok: str) -> dict:
    """The core of a gender question once the noun is already known -- shared by the
    regex-triggered :func:`gender_question` and the Deuter's free-form ``gender`` guess. Always
    returns a narratable dict (even ``prediction: None``) once a term is actually asked about --
    "GENUS doesn't know" is itself an honest answer to a genuine gender question."""
    for form in _forms(tok):
        known = sorted({r["object"] for r in sources.relations(
            conn, subject=f"{form}@de", predicate="grammatical_gender")})
        if known:
            return {"gender_q": True, "noun": form, "known": known}
    from genus import gender_rule
    for form in _forms(tok):
        r = gender_rule.predict_gender(conn, f"{form}@de")
        if r["found"]:
            return {"gender_q": True, "noun": form, "known": [], "prediction": r}
    return {"gender_q": True, "noun": tok, "known": [], "prediction": None}


def gender_question(conn, question: str) -> dict:
    """A grammatical-gender question about a German noun; ``{gender_q: False}`` if not one."""
    for pattern in _GENDER_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        return _gender_term(conn, m.group(1))
    return {"gender_q": False}


def narrate_gender(r: dict) -> str:
    if r["known"]:
        return f"»{r['noun']}« ist {_join_de(r['known'])} (bekannt, aus der Quelle)."
    p = r.get("prediction")
    if p:
        return (f"GENUS kennt »{r['noun']}« noch nicht, vermutet aber {p['gender']} "
                f"— Regel: Endung „-{p['suffix']}\" ({p['reliability']:.0%} Trefferquote über "
                f"{p['support']} bekannte Nomen; das ist eine Vermutung, kein Wissen).")
    return f"GENUS kennt »{r['noun']}« nicht gut genug, um auch nur zu vermuten — es rät nicht."


# --- Rechenfähigkeit: "Bestimme die Ableitung von f(x) = ..." ---------------------------
#
# Das Abitur-Ziel (Ronny, 2026-07-03: "GENUS soll die Aufgaben schaffen, nicht nur die Wörter
# kennen"): eine Ableitungs-Aufgabe ist keine Wissensfrage, sondern eine Rechnung -- exakt über
# genus.mathematik (sympy), niemals vom Deuter geraten. Diese feste Formulierung ist wie
# relate/common/gender_question ein deterministisches Muster: es fasst NUR eine erkennbare
# Aufgabenstellung auf, rechnet über den echten Kern und ist genauso selbst-prüfend (ein
# unlesbarer Term liefert ehrlich {"ok": False}, nie eine erfundene Ableitung).

_ORDNUNGSWORT = {"erste": 1, "zweite": 2, "dritte": 3}
_MATHTERM = r"([A-Za-z0-9äöüÄÖÜß\s\^\*\+\-/,\.\(\)]+?)"
_ABLEITUNG_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne|wie\s+lautet)\s+" + _FILL + r"die\s+(?:(erste|zweite|dritte)\s+)?"
        r"ableitung\s+von\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"[.!?]?\s*$", re.I),
    re.compile(r"\bleite\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"\s+ab[.!?]?\s*$", re.I),
]


def _ableitung_frage(text: str) -> dict | None:
    """Erkennt eine feste Ableitungs-Aufgabenformulierung; ``None`` sonst. Gibt
    ``{"term", "variable", "ordnung"}`` zurück -- reine Extraktion, keine Rechnung."""
    m = _ABLEITUNG_PATTERNS[0].search(text)
    if m:
        ordnung = _ORDNUNGSWORT.get((m.group(1) or "").lower(), 1)
        return {"term": m.group(3).strip(), "variable": m.group(2), "ordnung": ordnung}
    m = _ABLEITUNG_PATTERNS[1].search(text)
    if m:
        return {"term": m.group(2).strip(), "variable": m.group(1), "ordnung": 1}
    return None


def ableitung_frage(text: str) -> dict:
    """Die Ableitungs-Aufgabe in ``text``, exakt gerechnet; ``{"berechnung_q": False}``,
    wenn keine erkennbare Aufgabenstellung vorliegt."""
    from genus import mathematik

    gefunden = _ableitung_frage(text)
    if gefunden is None:
        return {"berechnung_q": False}
    r = mathematik.ableitung(gefunden["term"], gefunden["variable"], gefunden["ordnung"])
    r["berechnung_q"] = True
    return r


def narrate_ableitung(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    strich = "'" * r["ordnung"]
    return (f"f{strich}({r['variable']}) = {r['ableitung']} "
            f"(exakt berechnet, für f({r['variable']}) = {r['term']}).")


_EXTREMSTELLEN_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne|wie\s+lautet)\s+" + _FILL + r"die\s+extremstellen\s+von\s+"
        r"f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"[.!?]?\s*$", re.I),
]


def _extremstellen_frage(text: str) -> dict | None:
    m = _EXTREMSTELLEN_PATTERNS[0].search(text)
    if m is None:
        return None
    return {"term": m.group(2).strip(), "variable": m.group(1)}


def extremstellen_frage(text: str) -> dict:
    """Die Extremstellen-Aufgabe in ``text``, exakt gerechnet; ``{"berechnung_q": False}``,
    wenn keine erkennbare Aufgabenstellung vorliegt. Baut auf :func:`mathematik.extremstellen`
    auf -- dieselbe Rand/Kern-Trennung wie :func:`ableitung_frage`."""
    from genus import mathematik

    gefunden = _extremstellen_frage(text)
    if gefunden is None:
        return {"berechnung_q": False}
    r = mathematik.extremstellen(gefunden["term"], gefunden["variable"])
    r["berechnung_q"] = True
    return r


def narrate_extremstellen(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    if not r["punkte"]:
        return f"f({r['variable']}) = {r['term']} hat keine Extremstellen (exakt berechnet)."
    zeilen = [f"{p['art']} bei {r['variable']} = {p['x']} (f({r['variable']}) = {p['y']})"
              for p in r["punkte"]]
    return (f"Extremstellen von f({r['variable']}) = {r['term']}: " + "; ".join(zeilen)
            + " (exakt berechnet).")


_BOUND = r"([A-Za-z0-9\.\-]+)"
_STAMMFUNKTION_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne|wie\s+lautet)\s+" + _FILL + r"(?:eine|die)\s+stammfunktion\s+"
        r"von\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM + r"[.!?]?\s*$", re.I),
]
_INTEGRAL_PATTERNS = [
    re.compile(
        r"\b(?:bestimme|berechne)\s+" + _FILL + r"das\s+integral\s+von\s+f\(?(\w)\)?\)?\s*=\s*"
        + _MATHTERM + r"\s+(?:in\s+den\s+grenzen\s+von|zwischen)\s+" + _BOUND
        + r"\s+(?:bis|und)\s+" + _BOUND + r"[.!?]?\s*$", re.I),
]


def stammfunktion_frage(text: str) -> dict:
    """Die Stammfunktions-Aufgabe in ``text``, exakt gerechnet (inkl. "+ C"); ``{"berechnung_q":
    False}``, wenn keine erkennbare Aufgabenstellung vorliegt."""
    from genus import mathematik

    m = _STAMMFUNKTION_PATTERNS[0].search(text)
    if m is None:
        return {"berechnung_q": False}
    r = mathematik.stammfunktion(m.group(2).strip(), m.group(1))
    r["berechnung_q"] = True
    return r


def narrate_stammfunktion(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    return (f"F({r['variable']}) = {r['stammfunktion']} "
            f"(exakt berechnet, für f({r['variable']}) = {r['term']}).")


def integral_frage(text: str) -> dict:
    """Die Aufgabe eines bestimmten Integrals in ``text``, exakt gerechnet; ``{"berechnung_q":
    False}``, wenn keine erkennbare Aufgabenstellung ("...in den Grenzen von a bis b" /
    "...zwischen a und b") vorliegt."""
    from genus import mathematik

    m = _INTEGRAL_PATTERNS[0].search(text)
    if m is None:
        return {"berechnung_q": False}
    r = mathematik.integral(m.group(2).strip(), m.group(3), m.group(4), m.group(1))
    r["berechnung_q"] = True
    return r


_KURVENDISKUSSION_PATTERNS = [
    re.compile(
        r"\b(?:f(?:ü|ue)hre\s+" + _FILL + r"eine\s+)?kurvendiskussion\s+"
        r"(?:f(?:ü|ue)r|von|zu)\s+f\(?(\w)\)?\s*=\s*" + _MATHTERM
        + r"(?:\s+durch)?[.!?]?\s*$", re.I),
]


def kurvendiskussion_frage(text: str) -> dict:
    """Die Kurvendiskussions-Aufgabe in ``text`` -- gerechnet DURCH die Werkzeug-Registry
    (das erste komponierte Werkzeug im echten Dispatch): das Rezept schlägt seine drei
    Kern-Schritte zur Laufzeit im Register nach. ``{"berechnung_q": False}``, wenn keine
    erkennbare Aufgabenstellung vorliegt."""
    from genus import werkzeug, werkzeuge_seed

    m = _KURVENDISKUSSION_PATTERNS[0].search(text)
    if m is None:
        return {"berechnung_q": False}
    werkzeuge_seed.registriere_mathe_werkzeuge()
    r = werkzeug.registriert("kurvendiskussion").implementierung(m.group(2).strip(), m.group(1))
    r["berechnung_q"] = True
    return r


def _unendlich_lesbar(wert: str) -> str:
    return {"oo": "+∞", "-oo": "−∞"}.get(wert, wert)


def narrate_kurvendiskussion(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    je_schritt = {s["schritt"]: s for s in r["schritte"]}
    v = r["variable"]
    ns = je_schritt["nullstellen"]["nullstellen"]
    ns_text = ", ".join(f"{v} = {n}" for n in ns) if ns else "keine"
    punkte = je_schritt["extremstellen"]["punkte"]
    ex_text = ("; ".join(f"{p['art']} bei {v} = {p['x']} (f({v}) = {p['y']})" for p in punkte)
               if punkte else "keine")
    vu = je_schritt["verhalten_unendlich"]
    return (f"Kurvendiskussion für f({v}) = {r['term']}:\n"
            f"• Nullstellen: {ns_text}\n"
            f"• Extremstellen: {ex_text}\n"
            f"• Verhalten im Unendlichen: f → {_unendlich_lesbar(vu['plus_unendlich'])} für "
            f"{v} → +∞, f → {_unendlich_lesbar(vu['minus_unendlich'])} für {v} → −∞\n"
            f"(exakt berechnet, als Rezept: Nullstellen → Extremstellen → Grenzverhalten)")


def narrate_integral(r: dict) -> str:
    if not r["ok"]:
        return f"Das kann ich nicht ausrechnen: {r['fehler']}"
    return (f"Das bestimmte Integral von f({r['variable']}) = {r['term']} in den Grenzen von "
            f"{r['untere_grenze']} bis {r['obere_grenze']} ist {r['integral']} (exakt berechnet).")


# --- memory ("Merke dir: ...") -----------------------------------------------------------
#
# Slice 1 of Personen-Gedächtnis was named "person:ronny", but Ronny immediately used it to
# teach GENUS a fact about GENUS ITSELF ("Merk dir dass du GENUS heißt") -- filed under "facts
# about Ronny", read back nonsensically under "Was weißt du über mich?" (his own 😂 in the live
# log said it all). The fix wasn't a patch, it was a correct generalization: this is a general
# NOTEBOOK, not a "things about one person" store -- GENUS doesn't (and, honestly, mostly
# can't) know WHO or WHAT a free-text note is about; it only knows WHO TOLD it.
#
# Storage moved on from a flat, unnetworked relation (Punkt 1 von docs/GENUS_GEDAECHTNIS.md,
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


# --- Personen-Gedächtnis, Scheibe 2: Episoden beiläufig in Antworten einweben -------------
#
# Scheibe 1 machte das Gedächtnis nur auf explizite Rückfrage sichtbar ("Was weißt du über
# mich?"). Der reale nächste Schritt (Ronny) ist NICHT die automatische Extraktion aus
# gewöhnlichem Gespräch -- die gibt es faktisch schon: die "tatsache"-Zelle des Verstehens-
# Würfels notiert unaufgefordert erwähnte Aussagen längst (gedeckelt, unbestätigt). Was fehlt,
# ist das WEBEN: eine Erinnerung taucht bisher nie beiläufig in einer anderen Antwort auf, selbst
# wenn das Thema überschneidet. Der Abruf (Punkt 2 von docs/GENUS_GEDAECHTNIS.md, 2026-07-03)
# läuft jetzt über den echten Graphen (``erinnerung.erwaehnter_bezug`` -- Konzept-Anker, nicht
# roher Substring-Abgleich), nicht mehr über einen reinen Wort-in-Wort-Vergleich. Nur EIN
# Treffer, um nicht aufdringlich zu werden; bestätigt/vermutet bleibt sichtbar unterschieden,
# wie überall sonst in diesem Speicher.

def _notiz_bezug(conn, question: str) -> str | None:
    """Ein kurzer, ehrlicher Nebenbei-Hinweis, falls ``question`` denselben Begriff berührt wie
    eine gemerkte Episode -- ``None`` sonst. Nie erfunden: die Episode wird wörtlich zitiert.
    Ob das Beiläufige überhaupt erscheint, entscheidet der Antwort-Würfel (Kreuz-Konsistenz:
    knapp ⇒ kein Beiwerk) — Persönlichkeit wirkt an der Sprache, nie am Wissen."""
    from genus import antwort, erinnerung  # local: keeps companion's import-time surface a leaf otherwise

    if not antwort.belegung(conn, "plausch")["beiwerk_notiz"]:
        return None
    treffer = erinnerung.erwaehnter_bezug(conn, question)
    if treffer is None:
        return None
    if treffer["bestaetigt"]:
        return f" (Nebenbei: du hast mir erzählt „{treffer['inhalt']}“.)"
    return f" (Nebenbei, noch unbestätigt: du hattest erwähnt „{treffer['inhalt']}“.)"


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
        erinnerung.merke(conn, fact, quelle="ronny")
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


# --- Kausal-Fragen ("Verursacht X Y?" / "Was verursacht X?") ----------------------------
#
# Der is_a-Frage-Pfad (relate) beantwortet „Ist ein X ein Y?"; die KAUSAL-Frage liest dieselbe
# dichte causes/caused_by-Schicht + die transitive Kausalkette (genus/hypothese.kausal_pfad, EINE
# Quelle -- keine zweite Wahrheit). Gläsern wie relate: bei „ja" wird der Kausal-WEG gezeigt.
# Ehrlich: „kein bekannter Zusammenhang" heißt NICHT „nein" (open-world). Deterministisch, kein Modell.

_KAUSAL_URSACHE = [
    re.compile(r"\bwas\s+" + _FILL + r"verursacht\s+" + _FILL + _ART + r"?\s*" + _TERM, re.I),
    re.compile(r"\bwodurch\s+" + _FILL + r"entsteh(?:t|en)\s+" + _FILL + _ART + r"?\s*" + _TERM, re.I),
    re.compile(r"\bwoher\s+" + _FILL + r"komm(?:t|en)\s+" + _FILL + _ART + r"?\s*" + _TERM, re.I),
]
_KAUSAL_JA_NEIN = re.compile(
    r"\bverursacht\s+" + _FILL + _ART + r"?\s*" + _TERM + r"\s+" + _FILL + _ART + r"?\s*" + _TERM, re.I)


def _qids_of(conn, form: str) -> set[str]:
    return {r["object"] for r in sources.relations(conn, subject=f"{form}@de", predicate=sources.EXPRESSES)}


def _ursachen_von(conn, x_tok: str) -> dict:
    """Die bekannten Ursachen von X: ``{s : s causes X}`` ∪ ``{o : X caused_by o}``, benannt."""
    x_form = _concept_form(conn, x_tok)
    if x_form is None:
        return {"kausal_q": False}
    ursachen: set[str] = set()
    for q in _qids_of(conn, x_form):
        for r in sources.relations(conn, predicate="causes", object=q):
            ursachen.add(r["subject"])
        for r in sources.relations(conn, subject=q, predicate="caused_by"):
            ursachen.add(r["object"])
    # Auch bei LEERER Ursachen-Liste kausal_q=True: „Was verursacht X?" verlangt eine Antwort auf
    # die KAUSAL-Frage; die ehrliche „kenne keine Ursache" ist responsiver als eine Definition, die
    # eine andere Frage beantwortet -- und im Bot führt Durchfallen zum Deuter -> „nicht verstanden"
    # (kein Wort-Rückfall), nicht zur Definition. Kanal-sicher: der Kausal-Pfad antwortet selbst.
    return {"kausal_q": True, "art": "ursachen", "subjekt": x_form,
            "ursachen": sorted({_label(conn, u) for u in ursachen})}


def _kausal_zwischen(conn, x_tok: str, y_tok: str) -> dict:
    """Erreicht X kausal Y (transitiv, über die vereinte Kette)? Bei ja mit dem gezeigten Weg."""
    from genus import hypothese

    x_form = _concept_form(conn, x_tok)
    y_concepts, y_form = _concepts_of(conn, y_tok)
    if x_form is None or not y_concepts:
        return {"kausal_q": False}
    for xq in sorted(_qids_of(conn, x_form)):
        for yq in sorted(y_concepts):
            if xq == yq:
                continue                 # X und Y sind dasselbe Konzept (Synonyme) -- Identität
            pfad = hypothese.kausal_pfad(conn, xq, yq)   # ist KEINE belegte Kausation (Review-Fund):
            if pfad and len(pfad) >= 2:  # ein echter Kausal-Weg hat >= 2 Knoten (nicht der von==nach-Kurzschluss)
                return {"kausal_q": True, "art": "ja", "subjekt": x_form, "objekt": y_form,
                        "pfad": [_label(conn, p) for p in pfad]}
    return {"kausal_q": True, "art": "unbekannt", "subjekt": x_form, "objekt": y_form}


def relate_kausal(conn, question: str) -> dict:
    """Eine Kausal-Frage aus dem Graphen: „Was verursacht X?" (die Ursachen) oder „Verursacht X Y?"
    (ja/nein, mit Kausal-Weg). ``{kausal_q: False}``, wenn keine Kausal-Frage oder unauflösbar
    (dann versucht der Wort-Pfad weiter — dieselbe Selbst-Prüfung wie bei relate)."""
    for pat in _KAUSAL_URSACHE:
        m = pat.search(question)
        if m:
            r = _ursachen_von(conn, m.group(1))
            if r["kausal_q"]:
                return r
    m = _KAUSAL_JA_NEIN.search(question)
    if m:
        r = _kausal_zwischen(conn, m.group(1), m.group(2))
        if r["kausal_q"]:
            return r
    return {"kausal_q": False}


def narrate_kausal(conn, r: dict) -> str:
    """Gläserne deutsche Kausal-Antwort — bei „ja" wird der Weg gezeigt, Unbekanntes ehrlich benannt."""
    if r["art"] == "ursachen":
        if r["ursachen"]:
            liste = ", ".join(f"»{u}«" for u in r["ursachen"])
            return f"Als Ursache von »{r['subjekt']}« kenne ich: {liste}."
        return (f"Eine Ursache von »{r['subjekt']}« kenne ich nicht — das heißt nicht, dass es "
                f"keine gibt, nur dass mein Graph keine nennt.")
    if r["art"] == "ja":
        pfad = r["pfad"]
        if len(pfad) <= 2:
            return f"Ja. »{r['subjekt']}« verursacht »{r['objekt']}«."
        return "Ja, über eine Kausalkette: " + " → ".join(f"»{p}«" for p in pfad) + "."
    return (f"Einen Kausal-Zusammenhang von »{r['subjekt']}« zu »{r['objekt']}« kenne ich nicht "
            f"— das heißt nicht, dass es keinen gibt.")


def _muster_antwort(conn, question: str) -> tuple[str, str] | None:
    """The fixed-pattern cells (relation/kausal/comparative/gender/derivative) -- self-verifying: a
    pattern only claims the question when its terms actually resolve (in the graph, or -- for
    the derivative cell -- as a valid computable term). Returns ``(text, zelle)`` so a caller
    can record WHICH cell answered; ``None`` otherwise."""
    rel = relate(conn, question)
    if rel.get("relational"):
        return narrate_relation(conn, rel), "beziehung"
    kau = relate_kausal(conn, question)
    if kau.get("kausal_q"):
        return narrate_kausal(conn, kau), "beziehung"
    com = common(conn, question)
    if com.get("common"):
        return narrate_common(conn, com), "vergleich"
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


def _wort_antwort(conn, question: str) -> str | None:
    """The bare word reading -- any known word in the question, answered from its grounding.
    Deliberately the LAST reading in the Würfel order (it is greedy by nature and used to
    shadow better readings when it ran early -- the live bug class of 2026-07-02)."""
    a = answer(conn, question)
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


def respond(conn, question: str) -> str:
    """The full conversational answer to ``question``: remember -> recall -> state ->
    relational -> comparative -> gender -> word -> help, in that order (the personal-memory
    checks run first so they can never be shadowed by a fixed pattern or a known word; the rest
    matches ``cli.ask_command``). Plain text, no CLI tags. Pure deterministic half -- no model,
    and (except the explicit "merke dir") no writes: the Würfel's reading-records happen only
    in ``respond_with_deuter``, the conversational channel."""
    text = _ritual_antwort(conn, question)
    if text is not None:
        return text
    muster = _muster_antwort(conn, question)
    if muster is not None:
        return muster[0]
    text = _wort_antwort(conn, question)
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
    Vorschlag weiter gewachsen ist (Ronny 2026-07-05, docs/GENUS_INTELLIGENZ.md §9)."""
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


# --- Mehr-Zug-Arbeitsgedächtnis (Punkt 4 von docs/GENUS_GEDAECHTNIS.md, Scheibe "das Tier von
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
    return {"text": respond(conn, question), "question": question}


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
    "faehigkeiten": "eine Frage danach, was ich kann",
    "empfehlungsfrage": "eine Bitte um Empfehlung",
    "weltfrage": "eine Frage über die Welt draußen",
    "korrektur": "eine Korrektur an einer Tatsache",
    "meinung": "eine Meinungsäußerung",
    "lernen": "eine Aufforderung, etwas zu lernen",
    "tun": "eine Aufforderung, etwas in der Welt zu tun",
}


def _zelle_definition(conn, guess, question, last_question, last_answer, stimme=None):
    subject = guess.get("subject")
    if not subject:
        return None
    found = _last_known_word(conn, subject)
    if found is None:
        return None
    return respond(conn, f"Was ist {found}?")


def _zelle_beziehung(conn, guess, question, last_question, last_answer, stimme=None):
    if not (guess.get("subject") and guess.get("object")):
        return None
    r = _relate_terms(conn, guess["subject"], guess["object"])
    if r["relational"] and r["verdict"] == "yes":
        return narrate_relation(conn, r)      # eine echte is_a-Einordnung -- die stärkste Antwort
    # keine POSITIVE is_a-Beziehung? -> dieselbe Zelle trägt auch die GERICHTETE Kausal-Beziehung
    # („Verursacht X Y?", „Führt X zu Y?" -- Formulierungen, die die festen Muster von
    # _muster_antwort verfehlen, der Deuter aber als beziehung liest). Wichtig: „beide bekannt,
    # keine is_a-Kante" ist verdict=="no_path" (relational=True!) -- genau der Kausal-Fall; er darf
    # NICHT von der is_a-Zurückhaltung geschluckt werden. Reihenfolge: is_a-Ja > Kausal-Ja >
    # ehrliche is_a-Zurückhaltung. Die Kausal-Antwort ist selbst wortlautfest (Richtung = Wahrheit).
    k = _kausal_zwischen(conn, guess["subject"], guess["object"])
    if k["kausal_q"] and k["art"] == "ja":
        return narrate_kausal(conn, k)
    return narrate_relation(conn, r) if r["relational"] else None


def _zelle_ursache(conn, guess, question, last_question, last_answer, stimme=None):
    # „Was verursacht X?" / „Wodurch entsteht X?" -- das eigene Blatt der Kausal-FRAGE nach
    # Ursachen (früher ohne Handler: es kletterte zur Zelle frage-begriff und bekam die
    # DEFINITION von X statt seiner Ursachen -- eine andere Frage beantwortet, P3.1). Jetzt
    # führt es zur gebauten Kausal-Fähigkeit; unauflösbar -> None (klettert ehrlich weiter).
    subject = guess.get("subject")
    if not subject:
        return None
    r = _ursachen_von(conn, subject)
    return narrate_kausal(conn, r) if r["kausal_q"] else None


def _zelle_vergleich(conn, guess, question, last_question, last_answer, stimme=None):
    if not (guess.get("subject") and guess.get("object")):
        return None
    r = _common_terms(conn, guess["subject"], guess["object"])
    return narrate_common(conn, r) if r["common"] else None


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


def _zelle_offene_fragen(conn, guess, question, last_question, last_answer, stimme=None):
    return narrate_inquiries(conn, open_questions(conn))


def _zelle_ziele(conn, guess, question, last_question, last_answer, stimme=None):
    return narrate_ziele(conn)


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
_TREND_DE = {
    "rising": "Die Temperatur steigt gerade.",
    "falling": "Die Temperatur faellt gerade.",
    "stable": "Sie ist gerade recht konstant.",
}
_WETTER_FRISCH_STUNDEN = 2.0   # ~ zwei stuendliche Ticks; darueber ist der Wert nicht mehr „gerade"


def _formatiere_grad(wert) -> str:
    """Die Sensor-Zahl als deutscher Grad-Wert (Komma), auf eine Nachkommastelle -- lieber
    ehrlich rund als falsche Praezision."""
    zahl = float(wert)
    return f"{zahl:.1f}".replace(".", ",") + " °C"


def _wetter_alter_stunden(conn, claim_key, quelle):
    """Stunden zwischen JETZT (Wanduhr) und der neuesten Messung von ``claim_key`` aus der
    gewaehlten Quelle -- gegen die Wanduhr, NICHT relativ zur eigenen Reihe wie
    ``sources.resolve``'s ``live`` (das misst Frische nur zwischen Quellen und ist bei EINER
    Quelle immer 1.0). Nur ein echter Wanduhr-Vergleich laesst einen tage-alten Wert als „nicht
    mehr gerade" auffallen. Rein read-time (Mundstueck, nichts gespeichert -> Replay unberuehrt,
    wie die Motor-Erzaehlung). ``None``, wenn kein Zeitstempel lesbar ist."""
    from datetime import datetime, timezone

    from genus import sources

    stempel = [r["created_at"] for r in sources.assertions(conn, claim_key)
               if r["source"] == quelle and r.get("created_at")]
    if not stempel:
        return None
    try:
        ts = datetime.fromisoformat(max(stempel).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0


# WMO-Wetter-Codes (open-meteo) -> deutscher Zustand. Die Quelle liefert die Zahl; die
# Uebersetzung ist eine deterministische Nachschlage-Tabelle (kein Urteil, keine Erfindung).
_WMO_DE = {
    0: "klar", 1: "ueberwiegend klar", 2: "teils bewoelkt", 3: "bewoelkt",
    45: "neblig", 48: "gefrierender Nebel",
    51: "leichter Nieselregen", 53: "Nieselregen", 55: "dichter Nieselregen",
    56: "gefrierender Nieselregen", 57: "gefrierender Nieselregen",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    66: "gefrierender Regen", 67: "gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall", 77: "Schneegriesel",
    80: "leichte Regenschauer", 81: "Regenschauer", 82: "heftige Regenschauer",
    85: "Schneeschauer", 86: "starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "schweres Gewitter mit Hagel",
}


def _frischer_wert(conn, claim_key):
    """Ein zahlenwertiges Wetter-Feld aus dem Ledger -- aber NUR, wenn seine EIGENE neueste
    Messung frisch ist (absolutes Wanduhr-Alter <= :data:`_WETTER_FRISCH_STUNDEN`). Ein altes
    Feld (der letzte Fetch hat es ausgelassen, oder eine Zweitquelle hielt nur die Temperatur
    frisch) wird verschwiegen statt als aktuell ausgegeben -- jedes Feld traegt seine eigene
    Frische, nicht die der Temperatur. ``None`` auch bei keinem Wert, nicht-Zahl oder nan/inf
    (``int()``/``round()`` wuerden sonst krachen). Rein lesend."""
    import math

    from genus import sources

    res = sources.resolve(conn, claim_key)
    v = res.get("value")
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    alter = _wetter_alter_stunden(conn, claim_key, res.get("chosen_source"))
    if alter is None or alter > _WETTER_FRISCH_STUNDEN:
        return None
    return f


# --- der WELT-Sinn: Wetter ODER Nachrichten (P4) -----------------------------------------
#
# Der Deuter fasst beides als „weltfrage" (Etikett: „Wetter, Nachrichten, aktuelle Ereignisse").
# Hier wird unterschieden: Nachrichten-Schluesselwoerter -> News-Sinn, sonst -> Wetter-Sinn.
# Beide rein lesend, gläsern. Nachrichten-Schlagzeilen sind FREMDER, ungeprueffter Text: sie
# werden WORTGETREU angezeigt und nie interpretiert -- „weltfrage" ist wortlautfest, also formt
# die Stimme sie nie um, und GENUS handelt nie auf eine Schlagzeile hin (beobachteter Inhalt =
# Daten, nie Befehl). Der News-Puffer lebt an der MEMBRAN (deploy/observe_news.sh schreibt ihn,
# Ledger != Memory -- ephemerer Fremdtext gehoert nicht ins Ereignis-Ledger); der Kern LIEST ihn
# nur (kein HTTP im Kern).
_NEWS_SCHLUESSEL = ("neues", "neuigkeit", "nachricht", "news", "schlagzeile")
# Wetter-Woerter haben Vorrang: „das aktuelle WETTER" ist keine News-Frage. (Frueher fingen
# „aktuell"/„passiert" als News-Schluessel jede Wetterfrage ab -- Review-Fund, entfernt.)
_WETTER_SCHLUESSEL = ("wetter", "temperatur", "grad", "regen", "regnet", "warm", "kalt",
                      "sonne", "sonnig", "schnee", "wind", "sturm", "gewitter", "frost",
                      "bewoelkt", "bewölkt", "wolke")
_NEWS_MAX = 5
_NEWS_FRISCH_STUNDEN = 6.0
_NEWS_ANTWORT_MARKER = "Schlagzeilen ("   # GENUS' EIGENER Kopf einer News-Antwort mit Fremdtext


def _ist_news_frage(text) -> bool:
    t = (text or "").casefold()
    if any(w in t for w in _WETTER_SCHLUESSEL):   # eine Wetter-Frage bleibt Wetter
        return False
    return any(s in t for s in _NEWS_SCHLUESSEL)


def _lies_news_puffer():
    """Der Membran-News-Puffer (JSON) als Dict -- rein lesend, robust gegen fehlend/kaputt."""
    import json
    import os

    pfad = os.environ.get("GENUS_NEWS_PUFFER",
                          os.path.join(os.path.expanduser("~"), ".genus", "news_puffer.json"))
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _puffer_alter_stunden(ts):
    """Stunden seit dem Puffer-Zeitstempel (Wanduhr) -- ``None``, wenn nicht lesbar."""
    from datetime import datetime, timezone

    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def _news_bericht(conn):
    """Die aktuellen Schlagzeilen aus dem Membran-Puffer -- WORTGETREU (Fremdtext, nie
    interpretiert), mit Frische + Quelle, ehrlich, wenn nichts (Frisches) da ist."""
    puffer = _lies_news_puffer() or {}
    roh = puffer.get("schlagzeilen")
    zeilen = ([z.get("titel") for z in roh if isinstance(z, dict) and z.get("titel")]
              if isinstance(roh, list) else [])   # robust: schlagzeilen kein/kaputte Liste -> leer
    if not zeilen:
        return ("Nach Nachrichten kann ich schon greifen, aber gerade habe ich keine "
                "Schlagzeilen — mein Nachrichten-Sinn erreicht die Welt im Moment nicht.")
    quelle = puffer.get("quelle") or "meiner Nachrichtenquelle"
    alter = _puffer_alter_stunden(puffer.get("ts"))
    if alter is not None and alter > _NEWS_FRISCH_STUNDEN:
        wann = (f"von vor rund {round(alter / 24)} Tagen" if alter >= 24
                else f"von vor rund {round(alter)} Stunden")
        kopf = f"Meine letzten Schlagzeilen ({wann}, laut {quelle}) — frischere habe ich gerade nicht:"
    else:
        kopf = f"Die aktuellen Schlagzeilen (laut {quelle}):"
    liste = "\n".join(f"• {titel}" for titel in zeilen[:_NEWS_MAX])
    return f"{kopf}\n{liste}"


# Der billigste Sinn: die eigene Uhr. GENUS liest die Pi-Uhr (read-time, kein Netz noetig) und
# weiss aus dem bestehenden Uhr-Check (operation, system.clock), ob es einen NTP-Vorbehalt
# anhaengen muss -- ein selbst-bezueglicher Sinn (die eigene Zeit + das Vertrauen darin).
# Bewusst EINDEUTIGE Wendungen: „welche zeit" (Teilstring von „Zeitung") und das breite
# „welcher tag" sind RAUS (Review-Fund) -- und eine Zeit-Frage weicht ohnehin Wetter/News-
# Woertern, damit „Welcher Wochentag wird der waermste?" nicht die Uhr zieht.
_ZEIT_SCHLUESSEL = ("wie spät", "wie spaet", "spät ist", "spaet ist", "uhrzeit",
                    "wie viel uhr", "wieviel uhr", "welche uhrzeit", "welches datum",
                    "welcher wochentag", "welchen wochentag", "der wievielte")
_WOCHENTAG_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _ist_zeit_frage(text) -> bool:
    t = (text or "").casefold()
    if any(w in t for w in _WETTER_SCHLUESSEL) or any(s in t for s in _NEWS_SCHLUESSEL):
        return False   # eine Wetter-/News-Frage bleibt Wetter/News, auch mit Zeit-Wort drin
    return any(s in t for s in _ZEIT_SCHLUESSEL)


def _uhrzeit_bericht(conn):
    """Die aktuelle Uhrzeit + Datum aus der Pi-eigenen Uhr -- mit ehrlichem NTP-Vorbehalt, wenn
    der Uhr-Check (system.clock) die Uhr als nicht synchronisiert kennt. Rein lesend."""
    from datetime import datetime

    from genus import projection

    jetzt = datetime.now()
    satz = (f"Es ist gerade {jetzt.strftime('%H:%M')} Uhr — {_WOCHENTAG_DE[jetzt.weekday()]}, "
            f"der {jetzt.strftime('%d.%m.%Y')}.")
    clock = projection.active_belief(conn, "system.clock")
    if clock is not None and clock["claim_value"] == "unsynchronized":
        satz += " (Meine Uhr ist gerade nicht mit der Netzzeit synchron — also ohne Gewähr.)"
    return satz


def wetter_kurz(conn):
    """Eine kurze Wetter-Zeile fuer den Morgen-Gruss (Zustand + Temperatur) -- nur bei FRISCHEM
    Wert; ``None`` sonst (dann schweigt der Morgen zum Wetter, statt Altes zu behaupten)."""
    from genus import sources

    temp_res = sources.resolve(conn, "weather.temp_outside")
    wert = temp_res.get("value")
    if wert is None:
        return None
    alter = _wetter_alter_stunden(conn, "weather.temp_outside", temp_res.get("chosen_source"))
    if alter is None or alter > _WETTER_FRISCH_STUNDEN:
        return None
    code = _frischer_wert(conn, "weather.code")
    zustand = _WMO_DE.get(int(code)) if code is not None else None
    return f"{zustand}, {_formatiere_grad(wert)}" if zustand else _formatiere_grad(wert)


def news_top(conn):
    """Die oberste AKTUELLE Schlagzeile (wortgetreu) fuer den Morgen-Gruss -- ``None``, wenn
    keine (frischen) da sind. Fremdtext: der Morgen-Gruss wird deterministisch und WORTGETREU
    gesendet (kein Modell), also bleibt die Schlagzeile unangetastet wie im Chat."""
    puffer = _lies_news_puffer() or {}
    alter = _puffer_alter_stunden(puffer.get("ts"))
    if alter is None or alter > _NEWS_FRISCH_STUNDEN:   # kein Alter bekannt = nicht als frisch zeigen
        return None
    roh = puffer.get("schlagzeilen")
    if not isinstance(roh, list):
        return None
    for z in roh:
        if isinstance(z, dict) and z.get("titel"):
            return z["titel"]
    return None


def _zelle_weltfrage(conn, guess, question, last_question, last_answer, stimme=None):
    """Der Welt-Sinn (P4): Zeit-Frage -> Uhr, Nachrichten-Frage -> News, sonst -> Wetter (der
    Deuter fasst all das als „weltfrage"). Alle drei rein lesend."""
    text = (guess.get("text") if isinstance(guess, dict) else "") or question or ""
    if _ist_zeit_frage(text):
        return _uhrzeit_bericht(conn)
    if _ist_news_frage(text):
        return _news_bericht(conn)
    return _wetter_bericht(conn)


def _wetter_bericht(conn):
    """Spricht den wahrgenommenen Wetter-Bericht aus -- rein lesend. Ehrliche Teil-Antwort:
    jedes reiche Feld (Zustand, gefuehlt, Feuchte, Wind, Vorhersage, Regen) wird nur genannt,
    wenn es wirklich UND frisch im Ledger liegt; fehlt/veraltet es, wird geschwiegen, nie
    erfunden."""
    from genus import projection, sources

    temp_res = sources.resolve(conn, "weather.temp_outside")
    wert = temp_res.get("value")
    if wert is None:
        return ("Von der Welt draussen fuehle ich das Wetter — aber gerade habe ich keinen "
                "Wert: mein Wetter-Sinn erreicht die Welt im Moment nicht. Frag gern spaeter "
                "noch einmal.")
    quelle = temp_res.get("chosen_source")
    alter = _wetter_alter_stunden(conn, "weather.temp_outside", quelle)
    if not (alter is not None and alter <= _WETTER_FRISCH_STUNDEN):
        # nicht frisch: nur der letzte Temperatur-Wert, ehrlich als alt benannt -- keine alten
        # Detailfelder als aktuell ausgeben
        if alter is None:
            return (f"Mein letzter Wetter-Wert war {_formatiere_grad(wert)}, aber wie frisch er "
                    f"ist, weiss ich gerade nicht. Mehr sage ich dir mit einem frischen Wert.")
        wann = (f"vor rund {round(alter / 24)} Tagen" if alter >= 24
                else f"vor rund {round(alter)} Stunden")
        return (f"Mein letzter Wetter-Wert ({wann}) war {_formatiere_grad(wert)} — frischer habe "
                f"ich gerade nichts. Sobald mein Sinn wieder etwas empfaengt, sage ich dir mehr.")

    # frisch -> der reiche Bericht, jede Zutat nur bei echtem UND frischem Material (jedes Feld
    # traegt seine eigene Frische -- ein altes Feld wird verschwiegen, nie als aktuell gesprochen)
    code = _frischer_wert(conn, "weather.code")
    zustand = _WMO_DE.get(int(code)) if code is not None else None
    gefuehlt = _frischer_wert(conn, "weather.apparent")
    feuchte = _frischer_wert(conn, "weather.humidity")
    wind = _frischer_wert(conn, "weather.wind")
    tmax = _frischer_wert(conn, "weather.temp_max")
    tmin = _frischer_wert(conn, "weather.temp_min")
    regen = _frischer_wert(conn, "weather.rain_prob")

    kern = f"{zustand} bei {_formatiere_grad(wert)}" if zustand else _formatiere_grad(wert)
    if gefuehlt is not None and abs(gefuehlt - float(wert)) >= 1.0:
        kern += f" (gefuehlt {_formatiere_grad(gefuehlt)})"
    satz = f"Gerade draussen: {kern}."
    trend_row = projection.active_belief(conn, "weather.trend")
    trend = _TREND_DE.get(trend_row["claim_value"]) if trend_row else None
    if trend:
        satz += " " + trend
    detail = []
    if feuchte is not None:
        detail.append(f"Luftfeuchte {round(feuchte)} %")
    if wind is not None:
        detail.append(f"Wind {round(wind)} km/h")
    if detail:
        satz += " " + ", ".join(detail) + "."
    if tmin is not None and tmax is not None:
        satz += f" Heute {_formatiere_grad(tmin)} bis {_formatiere_grad(tmax)}"
        satz += (f", Regenwahrscheinlichkeit {round(regen)} %." if regen is not None else ".")
    elif regen is not None:
        satz += f" Regenwahrscheinlichkeit heute {round(regen)} %."
    if quelle and quelle != "weather.api":   # ein echter Provider-Name, kein internes Alt-Label
        satz += f" Diese Werte kommen von {quelle}."
    if temp_res.get("contradiction"):
        satz += " Meine Wetterquellen sind sich bei der Temperatur uneinig, also ohne Gewaehr."
    if tmax is not None:
        satz += " Fuer andere Orte oder weiter als heute reicht mein Wetter-Sinn noch nicht."
    else:
        satz += (" Vorhersage, Regen oder andere Orte kann ich noch nicht — dafuer fehlt meinem "
                 "Wetter-Sinn noch Material.")
    return satz


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
    "grammatik": _zelle_grammatik,
    "warum-herkunft": _zelle_nachfrage,
    "vertiefung": _zelle_nachfrage,
    "anschlussfrage": _zelle_nachfrage,
    "tatsache": _zelle_tatsache,
    "merken": _zelle_merken,
    "erinnerungs-abruf": _zelle_erinnerung,
    "zustand": _zelle_zustand,
    "offene-fragen": _zelle_offene_fragen,
    "ziele": _zelle_ziele,
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
# „beziehung" ist NICHT frei formulierbar: eine Relations-Aussage ist GERICHTET („A verursacht B",
# „A zählt zu B") -- die Stimme kann die Richtung umkehren, und die Substantiv-Leine prüft nur
# Vorkommen, nicht Reihenfolge (live gefunden 2026-07-06: „Staubsauger verursacht Sog" wurde zu
# „Sog verursacht Staubsauger"). Bei gerichteten Fakten IST die Struktur die Wahrheit -> wortlautfest.
_ZELLEN_FREI_FORMULIERBAR = frozenset({
    "definition", "vergleich", "grammatik", "frage-begriff",
})
_ZELLEN_PRUEFBAR = {
    "definition": "graph", "beziehung": "graph", "ursache": "graph", "vergleich": "graph",
    "grammatik": "graph", "frage-begriff": "graph", "zustand": "graph",
    "offene-fragen": "graph", "ziele": "graph",
    "warum-herkunft": "sitzung", "vertiefung": "sitzung", "anschlussfrage": "sitzung",
    "kuerzer": "sitzung", "ausfuehrlicher": "sitzung", "anders-erklaeren": "sitzung",
    "wiederholen": "sitzung",
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
# Die frühere Menge _STIMME_GEEIGNET ist weg (Phase 3): welche Zellen der Stimme angeboten
# werden dürfen, folgt strukturell aus der wortlautfest-Pflichtentscheidung ihrer
# Werkzeug-Spec (registriere_zellen / werkzeug.stimme_geeignet) -- eine Quelle, kein Paar.


def _stimme_versucht(conn, text: str, stimme) -> str:
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
    if anw is not None:
        try:
            geglaettet = stimme(text, anweisung=anw)
        except TypeError:
            geglaettet = stimme(text)
    else:
        geglaettet = stimme(text)
    return text if geglaettet is None else geglaettet + _STIMME_TAG


def _personalisiert(conn, question: str, text: str, stimme, marker: str = "") -> str:
    """Stimme-Versuch, dann ``marker`` (z.B. der Deuter-Hinweis), dann die Notiz-Einwebung
    (Personen-Gedächtnis Scheibe 2) -- in dieser Reihenfolge: die Notiz ist eine reine,
    deterministische Ergänzung ganz am Ende und darf die Anker-Prüfung der Stimme (die nur den
    narrate-Kern beurteilen soll) nicht verwirren."""
    text = _stimme_versucht(conn, text, stimme)
    return text + marker + (_notiz_bezug(conn, question) or "")


_ANCHOR_BLEIBT = {   # cells that reformat/retrace the EXISTING topic, never introduce a new one
    "warum-herkunft", "vertiefung", "anschlussfrage",
    "kuerzer", "ausfuehrlicher", "anders-erklaeren", "wiederholen",
}


def _deuter_antwort(conn, guess: dict, question: str, last_question: str | None,
                     last_answer: str | None = None, stimme=None) -> dict | None:
    """Map an OPEN model reading onto the Absichts-Raster and act from the known cell -- or
    climb ONE step to its Zwicky-Zelle (Blatt -> Zelle, nie tiefer -- eine Zelle ist schon die
    gröbste sinnvolle Einheit) -- or name honestly what GENUS read but cannot do yet. ``None``
    only when the reading is unklar/unbekannt or empty (then the caller falls through to the
    last word reading and the honest fallback)."""
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
        _record_still(verstehen.record_reading, conn, "unklar", "model:deuter")
        return None
    zellen = _handelbare_werkzeuge()
    zelle = verstehen.zelle_of(conn, kind)
    attempted = [kind] + ([zelle] if zelle else [])
    hatte_handler = False
    for step in attempted:
        zellen_werkzeug = zellen.get(step)
        if zellen_werkzeug is None:
            continue
        hatte_handler = True
        text = zellen_werkzeug.implementierung(conn, guess, question, last_question,
                                               last_answer, stimme)
        if text is not None:
            _record_still(verstehen.record_reading, conn, kind, "model:deuter")
            marker = "" if step in ("tatsache", "merken") else _DEUTED
            anchor = last_question if step in _ANCHOR_BLEIBT else question
            if not zellen_werkzeug.wortlautfest:
                # Stimme-Eignung folgt strukturell aus der Spec (Phase 3) -- keine zweite,
                # separat zu pflegende Menge mehr
                text = _personalisiert(conn, question, text, stimme, marker)
            elif marker and marker not in text:
                # die Meta-Zellen bauen auf last_answer auf, das oft schon einen Hinweis trägt
                # (Nochmal/Ausführlicher wiederholen ihn wörtlich mit) -- nie doppelt anhängen
                text = text + marker
            return {"text": text, "question": anchor, "kind": kind}
    if hatte_handler:
        return None   # capability exists but nothing resolved here -- fail safe, never claim inability
    # known cell, no capability anywhere up the chain: say so, honestly -- and count it,
    # because exactly these counts prioritise what gets built next
    _record_still(verstehen.record_reading, conn, kind, "model:deuter")
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
                         letzter_anschluss: str | None = None) -> dict:
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
        text = _stimme_versucht(conn, respond(conn, letzter_anschluss), stimme)
        return {"text": text, "question": letzter_anschluss, "gelesen": []}
    if last_question and is_why_followup(question):
        text = "\n".join(render_trace(conn, trace(conn, last_question)))
        return {"text": text, "question": last_question}
    if verlauf and is_backreference(question):
        frueher = _fruehere_frage_mit_bekanntem_begriff(conn, verlauf)
        if frueher is not None:
            text = respond(conn, frueher) + _BACKREF_TAG.format(frueher)
            return {"text": text, "question": frueher}
    text = _ritual_antwort(conn, question)
    if text is not None:
        return {"text": text, "question": question}
    muster = _muster_antwort(conn, question)
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
        text = (_stimme_versucht(conn, muster[0], stimme)
                if _werkzeug.stimme_geeignet(f"{ZELLE_PREFIX}{muster[1]}") else muster[0])
        if deuter is not None:
            text += _notiz_bezug(conn, question) or ""
        return {"text": text, "question": question, "gelesen": [muster[1]]}
    if deuter is not None:
        segmente = deuter(question)
        if isinstance(segmente, dict):
            segmente = [segmente]
        if segmente is not None:   # der Deuter LIEF -- auch eine leere Liste zählt als Lauf
            teile: list[str] = []
            gelesen: list[str] = []
            anchor = question
            for segment in segmente:
                gedeutet = _deuter_antwort(conn, segment, question, last_question, last_answer,
                                            stimme=stimme)
                if gedeutet is not None:
                    teile.append(gedeutet["text"])
                    anchor = gedeutet["question"]
                    if gedeutet.get("kind"):
                        gelesen.append(gedeutet["kind"])
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
    text = _wort_antwort(conn, question)
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
