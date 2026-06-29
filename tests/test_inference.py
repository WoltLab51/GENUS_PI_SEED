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
