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


# --- Scheibe ②: die Absicht „ort" auf dem Primärpfad ---------------------------------------

def test_planer_deduziert_den_ort_plan_und_beziehung_bleibt_intakt():
    from genus import reactors, werkzeuge_auskunft as wa
    conn = _geseedet()
    assert wa.ort_geplant(conn, "Kassel", "Hessen")["verdict"] == "yes"
    assert wa.ort_geplant(conn, "Kassel", "Deutschland")["verdict"] == "yes"   # transitiv
    assert wa.ort_geplant(conn, "Hessen", "Kassel")["verdict"] == "no_path"    # Richtung
    assert wa.ort_geplant(conn, "Kassel", "Bayern")["verdict"] == "no_path"    # falsch
    # beziehung (is_a) darf durch das zweite located_in-Primitiv NICHT brechen
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_pet", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_pet", "wikidata")
    assert wa.relate_geplant(conn, "Hund", "Haustier")["verdict"] == "yes"


def test_ort_regex_erkennt_und_beantwortet():
    from genus import companion
    conn = _geseedet()
    r = companion.ort(conn, "Ist Kassel in Hessen?")
    assert r["relational"] and r["verdict"] == "yes"
    assert companion.ort(conn, "Liegt München in Bayern?")["verdict"] == "yes"
    # „X in Y" trennt Ort von beziehung: der is_a-Erkenner greift hier NICHT
    assert companion.relate(conn, "Ist Kassel in Hessen?")["relational"] is False


def test_muster_pfad_liefert_die_ort_zelle():
    from genus import companion
    conn = _geseedet()
    text, zelle = companion._muster_antwort(conn, "Ist Kassel in Hessen?")
    assert zelle == "ort"
    assert "»Kassel« liegt in »Hessen«" in text


def test_gespraech_beantwortet_ort_warm_mit_festem_kern():
    from genus import companion
    conn = _geseedet()
    res = companion.respond_with_deuter(conn, "Ist Kassel in Hessen?")
    assert "»Kassel« liegt in »Hessen«" in res["text"]   # der gerichtete Fakt-Kern
    assert res["gelesen"] == ["ort"]


def test_deuter_ort_guess_wird_graph_verifiziert():
    from genus import companion
    conn = _geseedet()
    deuter = lambda q: {"absicht": "ort", "subject": "Kassel", "object": "Hessen"}
    res = companion.respond_with_deuter(conn, "liegt dieses kassel eigentlich in hessen", deuter=deuter)
    assert "»Kassel« liegt in »Hessen«" in res["text"]
    assert "Sprachmodell gedeutet" in res["text"]


def test_geerdete_quellen_sind_hoch_vertraut_strukturell_nicht_preset():
    # menschlich verantwortet -> geerdeter Boden. Der Wert ist STRUKTURELL der Spiegel der
    # Modell-Kappe (Modell halbiert das Vertrauen des Unbewiesenen, geerdet halbiert dessen
    # Misstrauen) -- keine zweite Konstante, kein Preset (Ronnys Ausreißer-Frage 2026-07-10).
    from genus import companion, sources
    conn = _geseedet()
    erwartet = 1 - (1 - sources.SOURCE_TRUST_SEED) / 2
    assert sources.source_trust(conn, "kuratiert") == erwartet
    assert sources.source_trust(conn, "ronny") == erwartet     # GENUS kennt Ronny
    assert sources.source_trust(conn, "unbekannt-xyz") == sources.SOURCE_TRUST_SEED
    assert companion.ort(conn, "Ist Kassel in Hessen?")["trust"] >= erwartet
    # die Ordnung der Zeugen-Güte: model < unbewiesen < geerdet
    assert (sources.MODEL_TRUST_SEED < sources.SOURCE_TRUST_SEED < sources.GROUNDED_TRUST)


def test_narrate_ort_richtung_kann_nicht_kippen():
    from genus import companion
    conn = _geseedet()
    r = companion.ort(conn, "Ist Kassel in Hessen?")
    warm = companion.narrate_ort(conn, r, {"waerme": "warm"})
    assert warm.startswith("Ja, klar —") and "»Kassel« liegt in »Hessen«" in warm
    assert warm.index("»Kassel«") < warm.index("»Hessen«")   # Kern-Insel, Richtung fest
