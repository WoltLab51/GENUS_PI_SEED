import sqlite3

from click.testing import CliRunner

from genus import cli, inference, reactors
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
