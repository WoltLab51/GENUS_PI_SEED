"""narrate + Formwahl: die gläserne Stimme sagt die natürliche Kopula („es ist ein »X«"),
sobald die Formwahl-Kette den Artikel ENTSCHEIDEN kann -- sonst byte-genau der alte, formfreie
Wortlaut („es zählt zu »X«"). Der Artikel steht außerhalb der »«, die Anker-Wörter bleiben
wortgleich (Stimme-Leine unberührt)."""
import sqlite3

from genus import auskunft, reactors
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _hund(conn, mit_genus: bool):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q3736439", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q3736439", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss",
                              "Haustier, dessen Vorfahr der Wolf ist", "dbnary")
    if mit_genus:
        reactors.observe_relation(conn, "Haustier@de", "grammatical_gender", "neutrum",
                                  "wikidata-lexemes")
    return conn


def test_narrate_sagt_natuerliche_kopula_wenn_der_artikel_entschieden_ist():
    conn = _hund(_fresh(), mit_genus=True)
    text = auskunft.narrate(auskunft.answer(conn, "Was ist ein Hund?"))
    assert "es ist ein »Haustier«" in text
    assert "zählt zu" not in text
    assert "»Haustier«" in text          # der Anker bleibt wortgleich in »«


def test_narrate_bleibt_bei_der_alten_phrasierung_ohne_entscheidung():
    # kein Genus-Beleg, kein Suffix-Wissen -> die Kette entscheidet nicht -> alter Wortlaut
    conn = _hund(_fresh(), mit_genus=False)
    text = auskunft.narrate(auskunft.answer(conn, "Was ist ein Hund?"))
    assert "es zählt zu »Haustier«" in text
    assert "es ist ein" not in text


def test_feminines_elternteil_bekommt_eine():
    conn = _fresh()
    reactors.observe_relation(conn, "Apfel@de", "expresses", "Q89", "wikidata")
    reactors.observe_relation(conn, "Q89", "is_a", "Q3314483", "wikidata")
    reactors.observe_relation(conn, "Frucht@de", "expresses", "Q3314483", "wikidata")
    reactors.observe_relation(conn, "Apfel@de", "primary_gloss", "eine Kernobst-Frucht", "dbnary")
    reactors.observe_relation(conn, "Frucht@de", "grammatical_gender", "feminin", "wikidata-lexemes")
    text = auskunft.narrate(auskunft.answer(conn, "Was ist ein Apfel?"))
    assert "es ist eine »Frucht«" in text


def test_mehrere_eltern_bekommen_je_ihren_artikel_wenn_alle_entschieden():
    # ALLE benannten Eltern entschieden -> "es ist ein »A« und ein »B«" (Nominativ ist sicher,
    # das Label trägt schon die richtige Adjektiv-Endung); die Klasse, nicht nur der Einzelfall
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q3736439", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q729", "wikidata")   # zweiter Elternteil
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q3736439", "wikidata")
    reactors.observe_relation(conn, "Tier@de", "expresses", "Q729", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "dbnary")
    reactors.observe_relation(conn, "Haustier@de", "grammatical_gender", "neutrum", "wikidata-lexemes")
    reactors.observe_relation(conn, "Tier@de", "grammatical_gender", "neutrum", "wikidata-lexemes")
    text = auskunft.narrate(auskunft.answer(conn, "Was ist ein Hund?"))
    assert "es ist ein »Haustier« und ein »Tier«" in text
    assert "zählt zu" not in text


def test_ein_unentschiedener_elternteil_faellt_ganz_auf_formfrei_zurueck():
    # ein Elternteil ohne Entscheidung (kein Genus, keine Regel) -> die GANZE Aufzählung bleibt
    # formfrei, statt halb Artikel / halb nicht zu mischen
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q3736439", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q729", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q3736439", "wikidata")
    reactors.observe_relation(conn, "Xyzzytier@de", "expresses", "Q729", "wikidata")   # kein Genus/Regel
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "dbnary")
    reactors.observe_relation(conn, "Haustier@de", "grammatical_gender", "neutrum", "wikidata-lexemes")
    text = auskunft.narrate(auskunft.answer(conn, "Was ist ein Hund?"))
    assert "zählt zu" in text and "»Haustier«" in text and "»Xyzzytier«" in text
    assert "es ist ein »" not in text


def test_answer_ohne_waage_bleibt_deterministisch_und_traegt_artikel_feld():
    conn = _hund(_fresh(), mit_genus=True)
    a = auskunft.answer(conn, "Was ist ein Hund?")   # keine Waage injiziert
    assert a["artikel"]["Haustier"]["weg"] == "gegruendet"


def test_wohngebaeude_bekommt_ueber_seinen_graph_kopf_den_richtigen_artikel():
    conn = _fresh()
    reactors.observe_relation(conn, "Haus@de", "expresses", "Q3947", "wikidata")
    reactors.observe_relation(conn, "Q3947", "is_a", "Q11755880", "wikidata")
    reactors.observe_relation(conn, "Wohngebäude@de", "expresses", "Q11755880", "wikidata")
    reactors.observe_relation(conn, "Q11755880", "is_a", "Q41176", "wikidata")
    reactors.observe_relation(conn, "Gebäude@de", "expresses", "Q41176", "wikidata")
    reactors.observe_relation(conn, "Gebäude@de", "grammatical_gender", "neutrum",
                              "wikidata-lexemes")
    reactors.observe_relation(conn, "Haus@de", "primary_gloss", "ein Bauwerk", "dbnary")

    text = auskunft.narrate(auskunft.answer(conn, "Was ist ein Haus?"))

    assert "es ist ein »Wohngebäude«" in text
    assert "eine »Wohngebäude«" not in text


def test_lexikon_usage_label_bleibt_im_graph_aber_nicht_in_der_gesprochenen_definition():
    conn = _fresh()
    reactors.observe_relation(conn, "Demokratie@de", "primary_gloss",
                              "ohne Plural: Volksherrschaft; politisches Prinzip", "dbnary")

    antwort = auskunft.answer(conn, "Was ist Demokratie?")
    text = auskunft.narrate(antwort)

    assert antwort["meaning"] == ["ohne Plural: Volksherrschaft; politisches Prinzip"]
    assert "versteht GENUS: Volksherrschaft" in text
    assert "ohne Plural" not in text


def test_normale_doppelpunkts_bedeutung_wird_nicht_weggeputzt():
    assert auskunft._sprechgloss("ohne Zweifel: eine gute Idee") == "ohne Zweifel: eine gute Idee"


def test_geklammerte_usage_marke_verbraucht_auch_ihren_doppelpunkt():
    assert auskunft._sprechgloss("[ohne Plural]: Volksherrschaft") == "Volksherrschaft"
