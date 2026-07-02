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
    """The concept a word most prominently expresses (the grounded Wikidata pick), if known."""
    rows = sources.relations(conn, subject=f"{form}@de", predicate="expresses")
    if not rows:
        return None
    grounded = [r["object"] for r in rows if r["source"] == "wikidata"]
    return grounded[0] if grounded else rows[0]["object"]


def _known(conn, form: str) -> bool:
    return bool(_objects(conn, form, "expresses") or _objects(conn, form, "defined_as")
               or _objects(conn, form, "primary_gloss"))


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
        sentence += f"; es zählt zu {_join_de(named)}"
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
        sentence += f" In anderen Sprachen: {', '.join(a['languages'][:4])}."
    return sentence


# --- relational questions ("Ist ein X ein Y?") -----------------------------------------
#
# A yes/no is_a question, answered by the *existing* inference primitive: map X to its
# concept(s), walk the concept-level is_a hierarchy (sense-coherent by construction), and
# check whether Y is among the ancestors. The answer is a derived edge, so it carries its
# whole premise chain -- glass-box: GENUS shows *the way* from X to Y, and the trust is the
# weakest premise. No model, nothing invented; the reasoning is the answer.

_ART = r"(?:einen|einer|eine|ein|der|die|das|den|dem)"
_TERM = r"([A-Za-zäöüÄÖÜß]+)"
_REL_PATTERNS = [
    re.compile(r"\bist\s+" + _ART + r"?\s*" + _TERM + r"\s+" + _ART + r"?\s*art(?:\s+von)?\s+" + _TERM, re.I),
    re.compile(r"\bist\s+" + _ART + r"?\s*" + _TERM + r"\s+" + _ART + r"\s+" + _TERM, re.I),
    re.compile(r"\bsind\s+" + _TERM + r"\s+" + _ART + r"?\s*" + _TERM, re.I),
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
            s += f" Der Weg: {' → '.join(path)}."
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
    re.compile(r"\bwas\s+haben\s+" + _ART + r"?\s*" + _TERM + r"\s+und\s+" + _ART + r"?\s*" + _TERM + r"\s+gemeinsam", re.I),
    re.compile(r"\bwas\s+ist\s+" + _ART + r"?\s*" + _TERM + r"\s+und\s+" + _ART + r"?\s*" + _TERM + r"\s+gemeinsam", re.I),
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
    s = f"»{r['x']}« und »{r['y']}« haben gemeinsam: beide zählen zu {labels[0]}"
    if len(labels) > 1:
        s += f" (und weiter zu {_join_de(labels[1:])})"
    return s + "."


# --- grammatical gender questions ("Welches Geschlecht hat X?") ------------------------
#
# Known FACT beats induced RULE beats honest silence: if GENUS has actually recorded a noun's
# gender (from Wikidata), it reports that -- never a guess where a fact is held. Only for a
# noun with no recorded gender does it fall to the induced suffix rule (gender_rule.predict_gender,
# Phase B SYSTEME breadth), clearly labelled as inferred, not certain. A noun can legitimately
# carry more than one recorded gender (homonymous lexemes, e.g. "Messer") -- both are shown.

_GENDER_PATTERNS = [
    re.compile(r"\bwelches\s+geschlecht\s+hat\s+" + _ART + r"?\s*" + _TERM, re.I),
    re.compile(r"\bwelchen\s+artikel\s+(?:hat|braucht)\s+" + _ART + r"?\s*" + _TERM, re.I),
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


# --- memory ("Merke dir: ...") -----------------------------------------------------------
#
# Slice 1 of Personen-Gedächtnis, corrected the same day it shipped: it was named
# "person:ronny", but Ronny immediately used it to teach GENUS a fact about GENUS ITSELF
# ("Merk dir dass du GENUS heißt") -- filed under "facts about Ronny", read back nonsensically
# under "Was weißt du über mich?" (his own 😂 in the live log said it all). The fix isn't a
# patch, it's a correct generalization: this is a general NOTEBOOK, not a "things about one
# person" store -- GENUS doesn't (and, honestly, mostly can't) know WHO or WHAT a free-text
# note is about; it only knows WHO TOLD it. A note is an ordinary relation
# (genus:notizen -notiz-> "<text>"), reusing the exact same provenanced machinery as every
# other fact GENUS holds -- no new event type, no new schema.
#
# Storage form (Ronny asked directly: "dicht aber schnell?"): the triple store already IS both
# -- normalized (no duplication), indexed (subject+predicate lookup, sub-ms) -- for the volume
# that exists and will exist for a good while. A semantic (embedding) index over notes, so
# "was weißt du über Hunde" could find a note by MEANING and not just literal recall, is a
# real, named future step -- deliberately NOT built now (self-calibration-no-presets: build
# capacity when the need is real, not speculatively for a notebook with a handful of entries).
#
# Two trust tiers, not a formal Proposal/Review cycle -- reusing a mechanism that's already
# fully built and trusted, not inventing a new one:
#   - source="ronny" (explicit "Merke dir: ..."): a HUMAN source, full/uncapped trust, exactly
#     like the teacher-loop. Ronny SAID to remember it -- that IS "enorm wichtig".
#   - source="model:deuter" (an unprompted personal STATEMENT the Deuter noticed in ordinary
#     conversation, e.g. "ich habe zwei Hunde" with no "merke dir" at all): capped at half the
#     trust seed, automatically, by the SAME model-source cap that already governs every other
#     model contribution (sources.MODEL_SOURCE_PREFIX) -- "GENUS schlägt vor" IS exactly what a
#     capped, unconfirmed source means elsewhere in this graph. Never silently promoted to full
#     trust; saying "Merke dir" for real about the same thing later adds a full-trust entry
#     alongside it (corroboration raises confidence, same as anywhere else in the graph).
#
# "Über Nacht Erinnerungen bilden" (Ronny's idea, sleep-like consolidation): deliberately NOT
# built here. It needs conversation TURNS to exist as ledger material to consolidate FROM --
# today only explicit/suggested notes are recorded, not raw conversation (Ledger ≠ Memory holds
# for ordinary chat). That is a separate, real architectural fork (do we start logging
# conversation turns, and in what form) -- worth revisiting once there is enough note/
# suggestion volume that consolidation would have real material to work with, not before.

NOTE_SUBJECT = "genus:notizen"
NOTE_PREDICATE = "notiz"
STATEMENT_SOURCE = "model:deuter"
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


def remember(conn, fact: str, source: str = "ronny") -> int:
    """Records a note -- an ordinary, provenanced relation. ``source="ronny"`` (the default) is
    an explicit, human-trusted command; ``source="model:deuter"`` is the Deuter noticing an
    unprompted personal statement, automatically capped (a suggestion, not a confirmed fact)."""
    from genus import reactors  # local: keeps companion's import-time surface a leaf otherwise
    result = reactors.observe_relation(conn, NOTE_SUBJECT, NOTE_PREDICATE, fact, source)
    return result["event_id"]


def _notes(conn, source_filter) -> list[str]:
    """Notes matching ``source_filter(source) -> bool``, oldest first.

    A dedicated query, not ``sources.relations()`` -- that orders alphabetically by object
    (right for graph traversal, wrong here: notes would sort by their TEXT, not by when they
    were told to GENUS, which looked like silent shuffling). Ordered by the projection's own
    ``id`` (insertion order), the simplest faithful proxy for "when was this remembered"."""
    rows = conn.execute(
        "SELECT object, source FROM relation_projection WHERE subject = ? AND predicate = ? ORDER BY id",
        (NOTE_SUBJECT, NOTE_PREDICATE),
    ).fetchall()
    return [row["object"] for row in rows if source_filter(row["source"])]


def confirmed_notes(conn) -> list[str]:
    """Notes a human explicitly asked GENUS to remember -- full trust."""
    return _notes(conn, lambda s: not s.startswith(sources.MODEL_SOURCE_PREFIX))


def suggested_notes(conn) -> list[str]:
    """Notes the Deuter noticed unprompted in ordinary conversation -- capped, unconfirmed."""
    return _notes(conn, lambda s: s.startswith(sources.MODEL_SOURCE_PREFIX))


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


# --- a single shared answer, for any conversational channel -----------------------------
#
# `cli.ask_command` has its own routing (terminal-log formatting, [ASK]/[BLF]/... tags -- left
# untouched, well-tested). `respond` is the same underlying routing order, rendered as plain
# text for a channel where that log-tag style would look odd (e.g. a chat bridge like Telegram).
# Read-only except for one deliberate, explicit exception: "merke dir: ..." (personal memory) --
# every other branch is a pure read, identical data functions, a different voice for a room.

def respond(conn, question: str) -> str:
    """The full conversational answer to ``question``: remember -> recall -> state ->
    relational -> comparative -> gender -> word -> help, in that order (the personal-memory
    checks run first so they can never be shadowed by a fixed pattern or a known word; the rest
    matches ``cli.ask_command``). Plain text, no CLI tags."""
    from genus import query  # local: keeps companion's import-time surface a leaf otherwise

    fact = remember_command(question)
    if fact is not None:
        remember(conn, fact)
        return f"Gemerkt: „{fact}“"
    if is_recall_question(question):
        return narrate_notes(confirmed_notes(conn), suggested_notes(conn))
    state = query.ask(conn, question)
    if state.get("kind") != "unknown":
        return state["answer"]
    if inquiries_question(question):
        return narrate_inquiries(conn, open_questions(conn))
    rel = relate(conn, question)
    if rel.get("relational"):
        return narrate_relation(conn, rel)
    com = common(conn, question)
    if com.get("common"):
        return narrate_common(conn, com)
    gen = gender_question(conn, question)
    if gen.get("gender_q"):
        return narrate_gender(gen)
    a = answer(conn, question)
    if a["found"]:
        text = narrate(a)
        if a.get("concept"):
            text += f" (Mehr Herkunft: „genus concept {a['concept']}\" oder „genus why answer …\".)"
        return text
    return state["answer"]  # the honest "nothing recognized" help, same fallback as the CLI


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
    return f"»{claim}« ({t}){times}."


def narrate_inquiries(conn, oq: dict) -> str:
    """The open concerns as fluent German -- and the honest note that answering them happens
    at the terminal, because this channel deliberately cannot write."""
    groups = oq["groups"]
    if not groups:
        return "Gerade beschäftigt mich nichts Offenes — alle meine Fragen sind beantwortet."
    header = ("Mich beschäftigt gerade eine Sache:" if len(groups) == 1
              else f"Mich beschäftigen gerade {len(groups)} Dinge:")
    lines = [header]
    lines += ["• " + _speak_inquiry(conn, g) for g in groups]
    lines.append("(Antworten kann ich hier nicht entgegennehmen — das geht am Terminal: "
                 "„genus inquiries\" und „genus teach\".)")
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


# --- the DEUTER: a capped edge model that parses free phrasing INTO the deterministic core -----
#
# Benchmarked (not guessed) across 7 models/families on the Pi before choosing: Qwen2.5-1.5B-
# Instruct hit the same accuracy (7/8 on a hand-scored German routing test) as models twice to
# four times its size, at the lowest latency/RAM of the reliable tier -- see the roadmap entry
# for the full comparison. The model lives at the edge (deploy/deuter.py); genus/ stays
# model-free -- ``deuter`` here is a plain callable a caller supplies (dependency injection),
# never imported by this module.
#
# Only called as a last resort (the fixed regex patterns above are cheap and, when they match,
# already fully reliable -- no reason to spend a model call once a pattern already nailed it),
# but no longer a narrow one: EVERY intent the deterministic core can act on (definition,
# relation, comparative, gender, statement, followup) is reachable through the Deuter now, not
# just three of them. Ronny's framing: "mit klaren Vorgaben, was GENUS braucht" -- the model
# WAEHLT only (an intent from a fixed list, one or two words from the question); it never
# writes the answer or invents a fact. Every subject/object it names is GRAPH-VERIFIED against
# the SAME resolution helpers the regex path uses (_relate_terms/_common_terms/_gender_term/
# _last_known_word) before anything happens -- a wrong guess just leaves the honest fallback in
# place, it can never fabricate an answer.

_UNKNOWN_FALLBACK = (   # query.ask's stable "nothing recognized" sentinel -- keep in sync
    "Das kann GENUS nicht einordnen — kein bekannter Befehl, kein gelerntes Wort."
)
_DEUTED = " (Frage vom Sprachmodell gedeutet.)"


def respond_with_deuter(conn, question: str, last_question: str | None = None, deuter=None) -> dict:
    """Like ``respond_in_conversation``, but with an optional DEUTER for when the deterministic
    pipeline finds NOTHING at all: an edge model may guess ``{"intent", "subject", "object"}``
    (``deuter(question) -> dict | None``, e.g. ``deploy.deuter.interpret``). Every guess is
    resolved through the SAME deterministic machinery the regex path uses, never answered
    directly by the model:
    - ``followup`` (with a known ``last_question``) retraces it exactly like a recognized bare
      follow-up -- this is what lets a phrasing OUTSIDE the small fixed cue-phrase set
      (:data:`_WHY_FOLLOWUP`) still reach the trace.
    - ``definition`` with a subject GENUS actually has something recorded about (checked via
      :func:`_last_known_word`, never trusted blindly) re-asks a clean synthesized question.
    - ``relation``/``comparative`` with BOTH terms present are resolved via
      :func:`_relate_terms`/:func:`_common_terms` -- the same graph-derived answer a matching
      regex would have produced, just reached from free phrasing instead.
    - ``gender`` with a subject that resolves (known fact or induced rule) is resolved via
      :func:`_gender_term`.
    - ``statement`` (an unprompted personal statement, e.g. "ich habe zwei Hunde" with no
      "merke dir" at all) is recorded VERBATIM as a capped, unconfirmed note
      (:data:`STATEMENT_SOURCE`) -- GENUS noticing something worth remembering without being
      told to, honestly marked as a guess, never silently promoted to full trust.
    Anything that doesn't resolve (chitchat/unclear, missing terms, an unknown subject, or no
    ``deuter``/no guess at all) leaves the honest fallback untouched -- a wrong guess can only
    ever fail safe. Every model-assisted answer is marked as such, glass-box, never silently.
    ``deuter=None`` (the default) reproduces ``respond_in_conversation`` exactly, so every
    existing caller stays safe without wiring one in."""
    result = respond_in_conversation(conn, question, last_question)
    if deuter is None or result["text"] != _UNKNOWN_FALLBACK:
        return result
    guess = deuter(question)
    if not guess:
        return result
    intent, subject, obj = guess.get("intent"), guess.get("subject"), guess.get("object")
    if intent == "followup" and last_question:
        text = "\n".join(render_trace(conn, trace(conn, last_question)))
        return {"text": text + _DEUTED, "question": last_question}
    if intent == "definition" and subject:
        found = _last_known_word(conn, subject)
        if found is not None:
            text = respond(conn, f"Was ist {found}?")
            return {"text": text + _DEUTED, "question": question}
    if intent == "relation" and subject and obj:
        r = _relate_terms(conn, subject, obj)
        if r["relational"]:
            return {"text": narrate_relation(conn, r) + _DEUTED, "question": question}
    if intent == "comparative" and subject and obj:
        r = _common_terms(conn, subject, obj)
        if r["common"]:
            return {"text": narrate_common(conn, r) + _DEUTED, "question": question}
    if intent == "gender" and subject:
        r = _gender_term(conn, subject)
        if r["known"] or r.get("prediction"):
            return {"text": narrate_gender(r) + _DEUTED, "question": question}
    if intent == "statement":
        remember(conn, question, source=STATEMENT_SOURCE)
        text = (f"Das klingt nach einer Erinnerung — ich hab's mir notiert, aber noch unsicher "
                f"(sag „merke dir: {question}“, wenn's wichtig ist, dann bin ich mir sicher).")
        return {"text": text, "question": question}
    return result


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
