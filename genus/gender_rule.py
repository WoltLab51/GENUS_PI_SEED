"""Grammatical gender by suffix -- SYSTEME's second rule-domain, genuinely different from
inference.py's is_a/synonym world (a new predicate, new data, new kind of rule) but built the
same way: induce a rule from GENUS's own graph, predict, self-test, calibrate the reliability
cut from the natural gap in the data. No linguistic knowledge is hardcoded (no "-chen is neuter"
fact) -- every candidate suffix is scored from evidence, and only the suffixes the data itself
vindicates as reliable are trusted. `grammatical_gender` is per LEXEME (from Wikidata's P5185),
so a noun with two homonymous lexemes (e.g. "Messer" = the knife, neuter; and "Messer" = one who
measures, masculine, a rare agent noun) legitimately carries two genders -- richness, not
corruption, exactly like `expresses` and `defined_as` already tolerate multi-valued words.
"""
from __future__ import annotations

from collections import defaultdict

from genus import sources

# Candidate cue lengths (last N characters of the noun). Not a claim that these are "the"
# German gender suffixes -- just the alphabet of candidates whose reliability the data judges.
SUFFIX_LENGTHS = (4, 3, 2)  # longest (most specific) tried first when predicting

# Seed fallback -- self-calibration is preferred once enough suffixes have been observed to
# show a natural gap (see calibrated_reliability_cut). A seed, not a law, like MIN_VINDICATIONS.
MIN_SUPPORT = 3          # a suffix needs at least this many distinct nouns to be judged at all
MIN_RELIABILITY = 0.80   # seed: a suffix "predicts" its majority gender at/above this rate


def _suffix(noun_form: str, length: int) -> str | None:
    form = noun_form.split("@", 1)[0]
    return form[-length:] if len(form) >= length else None


def _gender_counts(conn) -> dict[str, dict[str, int]]:
    """{noun_form_key (e.g. 'Hund@de'): {gender: count}} -- count, not a single value, because
    a noun can legitimately carry more than one gender across homonymous lexemes."""
    per_noun: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in sources.relations(conn, predicate="grammatical_gender"):
        per_noun[row["subject"]][row["object"]] += 1
    return per_noun


def suffix_evidence(conn) -> dict[tuple[str, int], dict[str, int]]:
    """For every candidate suffix (at every length in SUFFIX_LENGTHS), the gender distribution
    across all nouns bearing it -- one vote per (noun, gender) pair, so a doubly-gendered noun
    like "Messer" votes for both. Read-time, over the whole recorded grammatical_gender graph."""
    evidence: dict[tuple[str, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for noun_form, genders in _gender_counts(conn).items():
        for length in SUFFIX_LENGTHS:
            suf = _suffix(noun_form, length)
            if suf is None:
                continue
            for gender, n in genders.items():
                evidence[(suf, length)][gender] += n
    return evidence


def _reliability(counts: dict[str, int]) -> tuple[str, float, int]:
    """(majority gender, its share, total support) for one suffix's gender distribution."""
    total = sum(counts.values())
    gender, n = max(counts.items(), key=lambda kv: kv[1])
    return gender, n / total, total


def calibrated_reliability_cut(conn) -> float:
    """The reliability rate GENUS learns marks a suffix as a real cue, from the natural gap in
    its own suffixes' majority-share rates -- the gender-rule twin of calibrated_symmetry_rate
    (same shape: a population of RATES, split at its widest gap). Suffixes with too little
    support (< MIN_SUPPORT) don't enter the population -- a 2-noun "rule" proves nothing. Falls
    back to the seed MIN_RELIABILITY when there aren't enough suffixes yet to show a gap."""
    rates = sorted(
        rate for counts in suffix_evidence(conn).values()
        for _, rate, support in [_reliability(counts)]
        if support >= MIN_SUPPORT
    )
    if len(rates) < 2:
        return MIN_RELIABILITY
    _, lo, hi = max((rates[i + 1] - rates[i], rates[i], rates[i + 1]) for i in range(len(rates) - 1))
    return round((lo + hi) / 2, 4)


def predict_gender(conn, noun_form: str, cut: float | None = None) -> dict:
    """Predict a noun's gender from the most specific reliable suffix rule GENUS holds. Tries
    longest suffixes first (more specific cues win over shorter, noisier ones). ``{found: False}``
    if no candidate suffix clears the reliability cut with enough support -- open-world: GENUS
    withholds a guess rather than fabricate one from thin or noisy evidence."""
    if cut is None:
        cut = calibrated_reliability_cut(conn)
    evidence = suffix_evidence(conn)
    for length in SUFFIX_LENGTHS:
        suf = _suffix(noun_form, length)
        if suf is None or (suf, length) not in evidence:
            continue
        gender, rate, support = _reliability(evidence[(suf, length)])
        if support >= MIN_SUPPORT and rate >= cut:
            return {"found": True, "noun": noun_form, "suffix": suf, "gender": gender,
                    "reliability": round(rate, 3), "support": support, "cut": cut}
    return {"found": False, "noun": noun_form, "cut": cut}


def self_test(conn) -> dict:
    """Leave-one-out self-test: for every noun with a recorded gender, predict its gender from
    the OTHER nouns' evidence only (excluding its own votes, so a noun never confirms itself),
    and check whether the prediction matches ANY of its recorded genders (open-world: a doubly-
    gendered noun like "Messer" counts as correct if the prediction hits either sense). Returns
    accuracy plus the concrete exceptions -- confident predictions that a real noun contradicts,
    the honest, informative failures of an inductive rule (not a self-contradiction to fix, a
    fact about the language)."""
    per_noun = _gender_counts(conn)
    full_evidence = suffix_evidence(conn)
    cut = calibrated_reliability_cut(conn)
    checked = correct = 0
    exceptions: list[dict] = []
    for noun_form, genders in per_noun.items():
        leave_one_out: dict[tuple[str, int], dict[str, int]] = {
            key: dict(counts) for key, counts in full_evidence.items()
        }
        for length in SUFFIX_LENGTHS:
            suf = _suffix(noun_form, length)
            if suf is None:
                continue
            key = (suf, length)
            if key in leave_one_out:
                for gender, n in genders.items():
                    leave_one_out[key][gender] = leave_one_out[key].get(gender, 0) - n
        prediction = None
        for length in SUFFIX_LENGTHS:
            suf = _suffix(noun_form, length)
            key = (suf, length) if suf is not None else None
            counts = {g: n for g, n in leave_one_out.get(key, {}).items() if n > 0} if key else {}
            if not counts:
                continue
            gender, rate, support = _reliability(counts)
            if support >= MIN_SUPPORT and rate >= cut:
                prediction = {"suffix": suf, "gender": gender, "reliability": round(rate, 3)}
                break
        if prediction is None:
            continue
        checked += 1
        if prediction["gender"] in genders:
            correct += 1
        else:
            exceptions.append({"noun": noun_form, "predicted": prediction["gender"],
                                "actual": sorted(genders), "rule": prediction["suffix"],
                                "rule_reliability": prediction["reliability"]})
    return {"checked": checked, "correct": correct,
            "accuracy": round(correct / checked, 3) if checked else None,
            "cut": cut, "exceptions": exceptions}
