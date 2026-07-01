import sqlite3

from click.testing import CliRunner

from genus import cli, inference, reactors, sources
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _rel(conn, subject, predicate, object_, source="dict"):
    reactors.observe_relation(conn, subject, predicate, object_, source)


def test_transitive_inference_derives_and_justifies():
    conn = _fresh()
    _rel(conn, "dog", "is_a", "mammal")
    _rel(conn, "mammal", "is_a", "animal")
    derived = inference.infer(conn, "dog", "is_a")
    objects = {d["object"] for d in derived}
    assert "animal" in objects          # dog is_a animal -- derived
    assert "mammal" not in objects      # directly asserted -> not "derived"
    animal = next(d for d in derived if d["object"] == "animal")
    assert len(animal["chain"]) == 2    # the premise chain (dog->mammal->animal)
    assert animal["trust"] == 0.5       # weakest premise (single source = seed)
    conn.close()


def test_symmetric_inference_mirrors():
    conn = _fresh()
    _rel(conn, "run", "synonym", "execute")
    derived = inference.infer(conn, "execute", "synonym")
    assert "run" in {d["object"] for d in derived}
    conn.close()


def test_non_inferrable_predicate_derives_nothing():
    conn = _fresh()
    _rel(conn, "Germany", "capital", "Berlin")
    assert inference.infer(conn, "Germany", "capital") == []
    conn.close()


def test_inference_terminates_on_a_cycle():
    conn = _fresh()
    _rel(conn, "A", "is_a", "B")
    _rel(conn, "B", "is_a", "A")
    assert isinstance(inference.infer(conn, "A", "is_a"), list)  # must not hang
    conn.close()


def test_infer_cli_runs(monkeypatch):
    conn = _fresh()
    _rel(conn, "dog", "is_a", "mammal")
    _rel(conn, "mammal", "is_a", "animal")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["infer", "dog", "is_a"])
    assert result.exit_code == 0, result.output
    assert "animal" in result.output


# --- the lexeme <-> concept layer (multilingual) -------------------------------------

def _seed_animals(conn):
    # language-neutral concept hierarchy (Latin-keyed natural kinds)
    _rel(conn, "Canis", "is_a", "Mammalia", "wikidata")
    _rel(conn, "Mammalia", "is_a", "Animalia", "wikidata")
    # words in two languages express the SAME concepts
    _rel(conn, sources.lexeme_key("Hund", "de"), "expresses", "Canis", "ot")
    _rel(conn, sources.lexeme_key("dog", "en"), "expresses", "Canis", "wn")
    _rel(conn, sources.lexeme_key("Tier", "de"), "expresses", "Animalia", "ot")
    _rel(conn, sources.lexeme_key("animal", "en"), "expresses", "Animalia", "wn")


def test_lexeme_concept_lookup_both_directions():
    conn = _fresh()
    _seed_animals(conn)
    assert sources.senses(conn, "Hund", "de") == ["Canis"]
    assert sources.lexicalize(conn, "Canis") == ["Hund", "dog"]      # all forms
    assert sources.lexicalize(conn, "Canis", lang="de") == ["Hund"]  # one language
    assert sources.split_lexeme("Hund@de") == ("Hund", "de")
    assert sources.split_lexeme("Canis") == ("Canis", None)          # a bare concept
    conn.close()


def test_lexeme_reasons_through_concepts_sense_coherently():
    conn = _fresh()
    _seed_animals(conn)
    # a *different sense* of the word, off in another domain -- must NOT contaminate
    _rel(conn, "Bevoelkerung", "is_a", "Gruppe", "ot")  # unrelated concept line

    de = inference.infer_lexeme(conn, "Hund", "is_a", "de")
    objs = {r["object"] for r in de}
    assert objs == {"Mammalia", "Animalia"}             # clean ancestors, no "Gruppe"
    animalia = next(r for r in de if r["object"] == "Animalia")
    assert "Tier" in animalia["lexemes"]                # rendered back into German
    assert animalia["chain"][0]["predicate"] == "expresses"  # the chain starts at the word
    assert animalia["chain"][0]["subject"] == "Hund@de"
    conn.close()


def test_concept_graph_is_reused_across_languages():
    conn = _fresh()
    _seed_animals(conn)
    # the SAME concept facts answer the English word for free -- reason once, all languages
    en = inference.infer_lexeme(conn, "dog", "is_a", "en")
    assert {r["object"] for r in en} == {"Mammalia", "Animalia"}
    en_animalia = next(r for r in en if r["object"] == "Animalia")
    assert "animal" in en_animalia["lexemes"]
    conn.close()


def test_infer_lexeme_cli_runs_with_lang(monkeypatch):
    conn = _fresh()
    _seed_animals(conn)
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["infer", "Hund", "is_a", "--lang", "de"])
    assert result.exit_code == 0, result.output
    assert "Animalia" in result.output
    assert "Tier" in result.output


def test_relations_cli_renders_opaque_concepts_with_labels(monkeypatch):
    conn = _fresh()
    _rel(conn, "Pferd@de", "expresses", "Q726", "wikidata")
    _rel(conn, "Q726", "is_a", "Q729", "wikidata")
    _rel(conn, "Tier@de", "expresses", "Q729", "wikidata")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["relations", "Q726"])
    assert result.exit_code == 0, result.output
    assert "Q726 (Pferd)" in result.output     # opaque Q-id rendered readable
    assert "Q729 (Tier)" in result.output       # object too


def test_learns_transitivity_from_closed_triangles():
    conn = _fresh()  # a NON-seed predicate, vindicated by closed triangles -> LEARNED transitive
    for a, b, c in [("A", "B", "C"), ("D", "E", "F"), ("G", "H", "I")]:
        _rel(conn, a, "broader", b); _rel(conn, b, "broader", c)
        _rel(conn, a, "broader", c)                       # the transitive prediction, vindicated
    ev = inference.transitivity_evidence(conn, "broader")
    assert ev["vindications"] >= 3 and ev["examples"]
    assert inference.is_transitive(conn, "broader") is True    # learned from the data
    assert "broader" not in inference.TRANSITIVE_PREDICATES     # ...not assumed by a seed


def test_transitivity_falls_back_to_seed_without_evidence():
    conn = _fresh()
    assert inference.is_transitive(conn, "is_a") is True        # a seed hypothesis stands
    assert inference.is_transitive(conn, "likes") is False      # no seed, no evidence -> no


def test_learns_symmetry_from_mirrored_pairs():
    conn = _fresh()
    for a, b in [("x", "y"), ("p", "q"), ("m", "n")]:
        _rel(conn, a, "near", b); _rel(conn, b, "near", a)     # the mirror is asserted too
    assert inference.symmetry_evidence(conn, "near")["mirrored"] >= 3
    assert inference.is_symmetric(conn, "near") is True         # learned, not a seed
    assert "near" not in inference.SYMMETRIC_PREDICATES


def test_symmetry_needs_a_rate_not_just_a_count():
    conn = _fresh()  # the live is_a case: many one-way edges + a few incidental cycles != symmetry
    for i in range(200):
        _rel(conn, f"n{i}", "below", f"n{i + 1}")            # 200 one-directional edges
    for a, b in [("c1", "c2"), ("c3", "c4"), ("c5", "c6")]:
        _rel(conn, a, "below", b); _rel(conn, b, "below", a)  # 3 incidental cycles (6 mirrors)
    ev = inference.symmetry_evidence(conn, "below")
    assert ev["mirrored"] >= 3                                # a raw count would wrongly pass
    assert inference.is_symmetric(conn, "below") is False     # but the RATE is too low -> not symmetric


# --- the acyclicity self-check: a transitive hierarchy must be a DAG ---------------------

def test_detects_is_a_cycles_of_any_length():
    conn = _fresh()
    _rel(conn, "dog", "is_a", "mammal"); _rel(conn, "mammal", "is_a", "animal")  # clean DAG spine
    _rel(conn, "X", "is_a", "Y"); _rel(conn, "Y", "is_a", "X")                   # a 2-cycle
    _rel(conn, "A", "is_a", "B"); _rel(conn, "B", "is_a", "C"); _rel(conn, "C", "is_a", "A")  # a 3-cycle
    rings = inference.cycles(conn, "is_a")
    assert len(rings) == 2                                    # the DAG spine contributes none
    assert ["A", "B", "C"] in rings                           # each ring rooted at its smallest node (once)
    assert any(set(r) == {"X", "Y"} for r in rings)
    # the whole point: symmetry_evidence only ever meets the 2-cycle -- the 3-ring is invisible to it
    assert inference.symmetry_evidence(conn, "is_a")["mirrored"] == 2   # only X<->Y mirrors
    conn.close()


def test_acyclic_hierarchy_has_no_cycles():
    conn = _fresh()
    for a, b in [("dog", "mammal"), ("cat", "mammal"), ("mammal", "animal"), ("animal", "organism")]:
        _rel(conn, a, "is_a", b)                             # a healthy multi-parent DAG
    assert inference.cycles(conn, "is_a") == []
    conn.close()


def test_knowledge_report_surfaces_is_a_cycles(monkeypatch):
    conn = _fresh()  # the live shape: one source (Wikidata) asserting an is_a cycle both ways
    _rel(conn, "Suppe", "is_a", "minestra", "wikidata")
    _rel(conn, "minestra", "is_a", "Suppe", "wikidata")
    k = sources.characterize_knowledge(conn)
    assert len(k["is_a_cycles"]) == 1
    assert set(k["is_a_cycles"][0]) == {"minestra", "Suppe"}
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["knowledge"])
    assert result.exit_code == 0, result.output
    assert "1 is_a cycle(s)" in result.output


def test_infer_uses_learned_rule_not_only_the_seed():
    conn = _fresh()  # 'broader' is NOT a seed, but the graph vindicates its transitivity
    for a, b, c in [("A", "B", "C"), ("D", "E", "F"), ("G", "H", "I")]:
        _rel(conn, a, "broader", b); _rel(conn, b, "broader", c); _rel(conn, a, "broader", c)
    _rel(conn, "X", "broader", "Y"); _rel(conn, "Y", "broader", "Z")  # fresh chain, no direct X->Z
    objs = {d["object"] for d in inference.infer(conn, "X", "broader")}
    assert "Z" in objs                                       # derived because 'broader' was LEARNED transitive
    assert "broader" not in inference.TRANSITIVE_PREDICATES   # ...not because a seed said so


def test_infer_stays_empty_for_a_non_transitive_predicate():
    conn = _fresh()
    _rel(conn, "a", "likes", "b"); _rel(conn, "b", "likes", "c")   # no vindication, not a seed
    assert inference.infer(conn, "a", "likes") == []


def test_reaches_is_targeted_and_directional():
    conn = _fresh()
    _rel(conn, "A", "is_a", "B"); _rel(conn, "B", "is_a", "C")
    assert inference.reaches(conn, "A", "C", "is_a") is True     # A ->* C
    assert inference.reaches(conn, "C", "A", "is_a") is False    # not the other way


def test_closes_cycle_only_for_a_transitive_predicate():
    conn = _fresh()
    _rel(conn, "A", "friend", "B"); _rel(conn, "B", "friend", "C")   # 'friend' not transitive
    assert inference.closes_cycle(conn, "C", "friend", "A") is False
    _rel(conn, "X", "is_a", "Y"); _rel(conn, "Y", "is_a", "Z")       # is_a is (seed-)transitive
    assert inference.closes_cycle(conn, "Z", "is_a", "X") is True


def test_observe_relation_flags_a_new_is_a_cycle():
    conn = _fresh()
    reactors.observe_relation(conn, "A", "is_a", "B", "src")
    reactors.observe_relation(conn, "B", "is_a", "C", "src")
    r = reactors.observe_relation(conn, "C", "is_a", "A", "src")     # closes A->B->C->A
    types = [e["event_type"] for e in r["events"]]
    assert "contradiction_detected" in types and "inquiry_created" in types


def test_observe_relation_does_not_flag_acyclic_is_a():
    conn = _fresh()
    reactors.observe_relation(conn, "A", "is_a", "B", "src")
    r = reactors.observe_relation(conn, "B", "is_a", "C", "src")     # no ring
    assert "contradiction_detected" not in [e["event_type"] for e in r["events"]]


def test_transitivity_threshold_is_calibrated_from_the_natural_gap():
    conn = _fresh()  # 'strong' rule-like (20 triangles), 'weak' incidental (5) -> gap between them
    for i in range(20):
        _rel(conn, f"s{i}", "strong", f"m{i}"); _rel(conn, f"m{i}", "strong", f"t{i}")
        _rel(conn, f"s{i}", "strong", f"t{i}")
    for i in range(5):
        _rel(conn, f"w{i}", "weak", f"x{i}"); _rel(conn, f"x{i}", "weak", f"y{i}")
        _rel(conn, f"w{i}", "weak", f"y{i}")
    thr = inference.calibrated_transitivity_min(conn)
    assert thr == 6 and thr != inference.MIN_VINDICATIONS      # DERIVED from the data (top of low group + 1), not the constant
    assert inference.is_transitive(conn, "strong", threshold=thr) is True   # 20 >= 6 -> above the gap
    assert inference.is_transitive(conn, "weak", threshold=thr) is False    # 5 < 6 -> below the gap, no seed


def test_calibration_falls_back_to_seed_when_population_too_thin():
    conn = _fresh()  # only one predicate with triangles -> no gap to read -> seed threshold
    for i in range(4):
        _rel(conn, f"a{i}", "only", f"b{i}"); _rel(conn, f"b{i}", "only", f"c{i}")
        _rel(conn, f"a{i}", "only", f"c{i}")
    assert inference.calibrated_transitivity_min(conn) == inference.MIN_VINDICATIONS


def test_scan_records_calibration_and_hot_path_reasons_by_it():
    from genus import experience
    conn = _fresh()  # 'strong' rule-like (20), 'weak' incidental (5) -> derived threshold 6
    for i in range(20):
        _rel(conn, f"s{i}", "strong", f"m{i}"); _rel(conn, f"m{i}", "strong", f"t{i}")
        _rel(conn, f"s{i}", "strong", f"t{i}")
    for i in range(5):
        _rel(conn, f"w{i}", "weak", f"x{i}"); _rel(conn, f"x{i}", "weak", f"y{i}")
        _rel(conn, f"w{i}", "weak", f"y{i}")
    assert inference.stored_transitivity_threshold(conn) is None      # nothing recorded yet
    experience.scan(conn)                                             # the periodic calibration runs
    assert inference.stored_transitivity_threshold(conn) == 6         # ...records the derived value
    assert inference.is_transitive(conn, "strong") is True           # hot path reasons by the STORED 6
    assert inference.is_transitive(conn, "weak") is False             # 5 < 6 (would be True under the seed 3!)


def test_calibration_recharacterizes_when_the_threshold_changes():
    from genus import experience
    conn = _fresh()
    for i in range(5):   # only one chaining predicate -> no gap -> seed threshold recorded
        _rel(conn, f"w{i}", "weak", f"x{i}"); _rel(conn, f"x{i}", "weak", f"y{i}")
        _rel(conn, f"w{i}", "weak", f"y{i}")
    experience.scan(conn)
    assert inference.stored_transitivity_threshold(conn) == inference.MIN_VINDICATIONS
    for i in range(20):  # a rule-like predicate appears -> a gap opens -> threshold shifts
        _rel(conn, f"s{i}", "strong", f"m{i}"); _rel(conn, f"m{i}", "strong", f"t{i}")
        _rel(conn, f"s{i}", "strong", f"t{i}")
    experience.scan(conn)
    assert inference.stored_transitivity_threshold(conn) == 6         # recharacterized to the new value
