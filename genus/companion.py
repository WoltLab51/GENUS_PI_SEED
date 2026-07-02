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


def relate(conn, question: str) -> dict:
    """Answer a yes/no is_a question from the graph; ``{relational: False}`` if it isn't one
    (or names something GENUS can't resolve, so a plain word-lookup should try instead)."""
    for pattern in _REL_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        x_form = _concept_form(conn, m.group(1))
        y_concepts, y_form = _concepts_of(conn, m.group(2))
        if x_form is None or not y_concepts:
            continue  # not a relation GENUS can own -- fall through to the word companion
        ancestors = inference.infer_lexeme(conn, x_form, "is_a", "de")
        hits = [a for a in ancestors if a["object"] in y_concepts]
        if hits:
            best = min(hits, key=lambda a: len(a["chain"]))
            return {"relational": True, "verdict": "yes", "subject": x_form, "object": y_form,
                    "target": best["object"], "trust": best["trust"], "chain": best["chain"]}
        return {"relational": True, "verdict": "no_path", "subject": x_form, "object": y_form}
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


def common(conn, question: str) -> dict:
    """The shared is_a ancestors of two words, closest first; ``{common: False}`` if not asked."""
    for pattern in _COMMON_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        x, y = _concept_form(conn, m.group(1)), _concept_form(conn, m.group(2))
        if x is None or y is None:
            continue
        dx, dy = _ancestor_depths(conn, x), _ancestor_depths(conn, y)
        ordered = sorted(set(dx) & set(dy), key=lambda c: dx[c] + dy[c])
        shared = [c for c in ordered if _label(conn, c) != c]   # only human-nameable categories
        return {"common": True, "found": bool(shared), "x": x, "y": y, "shared": shared}
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


def gender_question(conn, question: str) -> dict:
    """A grammatical-gender question about a German noun; ``{gender_q: False}`` if not one."""
    for pattern in _GENDER_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        tok = m.group(1)
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


# --- a single shared answer, for any conversational channel -----------------------------
#
# `cli.ask_command` has its own routing (terminal-log formatting, [ASK]/[BLF]/... tags -- left
# untouched, well-tested). `respond` is the same underlying routing order, rendered as plain
# text for a channel where that log-tag style would look odd (e.g. a chat bridge like Telegram).
# Read-only, no side effects -- identical data functions, a different voice for a different room.

def respond(conn, question: str) -> str:
    """The full conversational answer to ``question``: state -> relational -> comparative ->
    gender -> word -> help, in that order (matches ``cli.ask_command``). Plain text, no CLI tags."""
    from genus import query  # local: keeps companion's import-time surface a leaf otherwise

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
    return state["answer"]  # the "unknown fixed query pattern" help, same fallback as the CLI


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


# --- the DEUTER: a capped, last-resort edge model, called only when nothing else answers ------
#
# Benchmarked (not guessed) across 7 models/families on the Pi before choosing: Qwen2.5-1.5B-
# Instruct hit the same accuracy (7/8 on a hand-scored German routing test) as models twice to
# four times its size, at the lowest latency/RAM of the reliable tier -- see the roadmap entry
# for the full comparison. The model lives at the edge (deploy/deuter.py); genus/ stays
# model-free -- ``deuter`` here is a plain callable a caller supplies (dependency injection),
# never imported by this module. It WAEHLT only (an intent from a fixed list, a subject word
# from the question) -- it never writes the answer; the deterministic pipeline still supplies
# the actual, sourced content. Any subject it names is GRAPH-VERIFIED before anything happens.

_UNKNOWN_FALLBACK = "unknown fixed query pattern"  # query.ask's stable "nothing recognized" sentinel


def respond_with_deuter(conn, question: str, last_question: str | None = None, deuter=None) -> dict:
    """Like ``respond_in_conversation``, but with an optional last-resort DEUTER for when the
    deterministic pipeline finds NOTHING at all: an edge model may guess
    ``{"intent": ..., "subject": ...}`` (``deuter(question) -> dict | None``, e.g.
    ``deploy.deuter.interpret``). Only two guesses are ever acted on, both re-run through the
    existing deterministic machinery rather than answered directly:
    - ``followup`` (with a known ``last_question``) retraces it exactly like a recognized bare
      follow-up -- this is what lets a phrasing OUTSIDE the small fixed cue-phrase set
      (:data:`_WHY_FOLLOWUP`) still reach the trace.
    - ``definition`` with a subject GENUS actually has something recorded about (checked via
      :func:`_last_known_word`, never trusted blindly) re-asks a clean synthesized question.
    Anything else (chitchat/relation/unclear, an unknown subject, or no ``deuter``/no guess at
    all) leaves the honest fallback untouched. The answer is marked as model-assisted, glass-box
    -- never silently. ``deuter=None`` (the default) reproduces ``respond_in_conversation``
    exactly, so every existing caller stays safe without wiring one in."""
    result = respond_in_conversation(conn, question, last_question)
    if deuter is None or result["text"] != _UNKNOWN_FALLBACK:
        return result
    guess = deuter(question)
    if not guess:
        return result
    if guess.get("intent") == "followup" and last_question:
        text = "\n".join(render_trace(conn, trace(conn, last_question)))
        return {"text": text + " (Frage vom Sprachmodell gedeutet.)", "question": last_question}
    if guess.get("intent") == "definition" and guess.get("subject"):
        found = _last_known_word(conn, guess["subject"])
        if found is not None:
            text = respond(conn, f"Was ist {found}?")
            return {"text": text + " (Frage vom Sprachmodell gedeutet.)", "question": question}
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
