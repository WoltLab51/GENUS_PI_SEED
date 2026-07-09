"""Die ANTWORT-WERKZEUGE des Begleiters -- das „Ausführen": aus dem verifizierten Graph-
Wissen eine deterministische, gläserne Antwort komponieren. Definition (``answer``/``narrate``/
``vertiefung``/``antizipation``), Beziehung (``relate``), Gemeinsames (``common``), Grammatik
(``gender_question``) und Kausalität (``relate_kausal``) -- jedes ``*_frage``/``narrate_*``-Paar
modellfrei, nichts erfunden, jeder benannte Begriff ein Stimme-Anker in »«.

Herausgelöst aus ``companion.py`` (2026-07-09, Modularisierung Schritt ③): das ist die
Registry-nahe Schicht, aus der der Tool-Planer ③ später komponiert. Liest die Lese-Grundlage
(:mod:`genus.wortgraph`) nach unten; companion re-exportiert die öffentlichen Namen, damit die
Dispatch-Zellen, ``respond_with_deuter`` und die Tests unverändert ``companion.answer`` usw.
lesen. Azyklisch (auskunft importiert wortgraph/sources/inference, nichts aus der
Orchestrierung).
"""
import re

from genus import inference, sources
from genus.wortgraph import (
    _collapse,
    _concept_form,
    _concepts_of,
    _forms,
    _join_de,
    _konzept_name,
    _label,
    _last_known_word,
    _objects,
    _prominent_concept,
)


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
    resolve, so a plain word-lookup should try instead). Seit ③ Scheibe C läuft die Auflösung
    PLANER ZUERST (der selbst-deduzierte Plan; ``_relate_terms`` bleibt das gezählte Netz) --
    die Regex ist nur noch der Erkenner, nicht mehr der Rechenweg. Lazy-Import, kein Zyklus:
    werkzeuge_auskunft importiert auskunft seinerseits nur funktions-lokal."""
    from genus import werkzeuge_auskunft

    for pattern in _REL_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        r = werkzeuge_auskunft.relate_geplant(conn, m.group(1), m.group(2))
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
