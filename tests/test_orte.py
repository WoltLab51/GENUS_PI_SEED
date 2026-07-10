"""Der Orte-Seed (Planer-Absicht „ort", Scheibe ①): die kuratierte Geo-Grundierung macht
„Ist Kassel in Hessen?" überhaupt beantwortbar -- geprüft auf der Inferenz-Ebene (die
Absicht selbst kommt in Scheibe ②)."""
import sqlite3

from genus import inference, orte, sources
from genus.db import init_schema


def _geseedet():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    orte.seed_orte(conn)
    return conn


def _located_in_ahnen(conn, wort):
    return {a["object"] for a in inference.infer_lexeme(conn, wort, orte.LOCATED_IN, "de")}


def test_stadt_liegt_transitiv_im_bundesland_und_im_land():
    conn = _geseedet()
    ahnen = _located_in_ahnen(conn, "Kassel")
    assert "Q1199" in ahnen      # Hessen -- „Ist Kassel in Hessen?" -> ja
    assert "Q183" in ahnen       # Deutschland -- „Ist Kassel in Deutschland?" -> ja (2 Hops)


def test_stadtstaat_liegt_direkt_im_land():
    conn = _geseedet()
    assert "Q183" in _located_in_ahnen(conn, "Berlin")   # „Ist Berlin in Deutschland?" -> ja


def test_falsche_zuordnung_wird_nicht_behauptet():
    # Kassel liegt NICHT in Bayern (Q980) -- open-world-ehrlich, keine erfundene Kante
    conn = _geseedet()
    assert "Q980" not in _located_in_ahnen(conn, "Kassel")


def test_wort_loest_auf_und_konzept_ist_benennbar():
    conn = _geseedet()
    # Auflösung: Hessen@de -expresses-> Q1199
    formen = {r["object"] for r in sources.relations(conn, subject="Hessen@de", predicate="expresses")}
    assert "Q1199" in formen
    # Anzeige: Q1199 lexikalisiert zu „Hessen" (kein blanker Q-Knoten in einer Antwort)
    assert "Hessen" in sources.lexicalize(conn, "Q1199", "de")


def test_kurzform_frankfurt_loest_auf():
    conn = _geseedet()
    assert "Q1794" in {r["object"] for r in sources.relations(
        conn, subject="Frankfurt@de", predicate="expresses")}


def test_seed_ist_idempotent():
    conn = _geseedet()
    assert orte.seed_orte(conn) == 0   # zweiter Lauf sät nichts Neues


def test_alle_bundeslaender_haengen_am_land():
    conn = _geseedet()
    for _, qid in orte.BUNDESLAENDER:
        if qid == orte.DEUTSCHLAND:
            continue
        ahnen = {r["object"] for r in sources.relations(conn, subject=qid, predicate=orte.LOCATED_IN)}
        assert orte.DEUTSCHLAND in ahnen, f"{qid} haengt nicht an Deutschland"
