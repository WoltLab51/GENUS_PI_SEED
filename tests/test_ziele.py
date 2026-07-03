"""Der Ziel-Graph (genus.ziele): Ronnys Ziele als provenanctes Wissen -- Inversion ④ des
Audits (docs/GENUS_AUDIT_2026_07.md). GENUS weiß damit zum ersten Mal, DASS es Ziele hat,
und kann selbst benennen, was ihm dafür fehlt."""
import sqlite3

from genus import companion, ziele
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _gesaet():
    conn = _fresh()
    ziele.seed_ziele(conn)
    return conn


def test_seed_ziele_is_idempotent():
    conn = _fresh()
    erste = ziele.seed_ziele(conn)
    assert erste > 0
    assert ziele.seed_ziele(conn) == 0   # ein zweiter Lauf sät nichts Neues


def test_mission_and_all_goals_are_in_the_graph():
    conn = _gesaet()
    assert ziele.mission(conn) == "Menschen unterstützen. digital. GENUS."
    alle = ziele.ziele(conn)
    assert len(alle) == len(ziele.ZIEL_SEED) - 1   # alle außer der Mission selbst
    ids = {z["id"] for z in alle}
    assert "ziel:selbst-entwicklung" in ids and "ziel:begleiter" in ids


def test_goals_keep_insertion_order_not_alphabetical():
    # dieselbe Lehre wie bei Notizen/Episoden: sources.relations sortiert alphabetisch nach
    # Objekt -- die Reihenfolge der Ziele muss aber Ronnys Seed-Reihenfolge sein
    conn = _gesaet()
    erwartet = [ziel_id for ziel_id, _ in ziele.ZIEL_SEED if ziel_id != ziele.MISSION]
    assert [z["id"] for z in ziele.ziele(conn)] == erwartet


def test_every_goal_serves_the_mission():
    conn = _gesaet()
    from genus import sources
    for ziel_id, _ in ziele.ZIEL_SEED:
        if ziel_id == ziele.MISSION:
            continue
        dient = sources.relations(conn, subject=ziel_id, predicate=ziele.DIENT)
        assert [r["object"] for r in dient] == [ziele.MISSION], ziel_id


def test_goal_dependencies_carry_capability_status():
    conn = _gesaet()
    selbst = next(z for z in ziele.ziele(conn) if z["id"] == "ziel:selbst-entwicklung")
    by_id = {f["id"]: f for f in selbst["braucht"]}
    assert by_id["faehigkeit:vorschlags-loop"]["status"] == "fehlt"
    assert by_id["faehigkeit:selbst-bild"]["status"] == "teilweise"


def test_fehlende_faehigkeiten_lists_each_gap_once():
    conn = _gesaet()
    fehlt = ziele.fehlende_faehigkeiten(conn)
    ids = [f["id"] for f in fehlt]
    assert len(ids) == len(set(ids))   # generator-organ dient 3 Zielen, erscheint aber 1x
    assert "faehigkeit:generator-organ" in ids
    assert all(f["status"] != "live" for f in fehlt)


def test_seed_edges_never_pollute_the_concept_is_a_statistics():
    # bewusst KEIN is_a zwischen Zielen: die gelernten Schluss-Regeln kalibrieren sich aus
    # den is_a-Daten -- Ziel-Kanten dort hineinzumischen würde die Statistik verfälschen
    conn = _gesaet()
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM relation_projection "
        "WHERE predicate = 'is_a' AND (subject LIKE 'ziel:%' OR subject LIKE 'faehigkeit:%')"
    ).fetchone()
    assert rows["n"] == 0


def test_ziele_question_recognizes_the_cue_phrases():
    for q in ("Was sind deine Ziele?", "was willst du werden", "Was ist deine Mission?",
              "Wofür bist du da?", "was fehlt dir"):
        assert companion.ziele_question(q), q
    for q in ("Was ist ein Fahrrad?", "was beschäftigt dich", ""):
        assert not companion.ziele_question(q), q


def test_narrate_ziele_speaks_mission_goals_and_honest_gaps():
    conn = _gesaet()
    text = companion.narrate_ziele(conn)
    assert "Menschen unterstützen. digital. GENUS." in text
    assert "Begleiter" in text
    assert "fehlt mir noch" in text            # die Lücken werden ehrlich benannt
    assert "vorschlags-loop" in text
    assert "Quelle: Ronny" in text             # Herkunft, wie überall


def test_narrate_ziele_is_honest_before_the_seed_is_applied():
    conn = _fresh()   # z.B. der Live-Pi vor dem einen sauberen Apply
    text = companion.narrate_ziele(conn)
    assert "noch nicht" in text


def test_ziele_ritual_answers_through_the_conversation_path():
    conn = _gesaet()
    result = companion.respond_with_deuter(conn, "Was sind deine Ziele?")
    assert "Meine Mission" in result["text"] and "fehlt mir noch" in result["text"]


def test_ziele_leaf_reaches_the_handler_via_the_deuter_path():
    # freie Formulierung, die kein Cue trifft -- der Deuter liest "ziele", der Handler antwortet
    conn = _gesaet()
    deuter = lambda q: [{"absicht": "ziele", "text": q}]
    result = companion.respond_with_deuter(conn, "erzähl doch mal, wo die Reise hingeht",
                                           deuter=deuter)
    assert "Meine Mission" in result["text"]
    assert "Sprachmodell gedeutet" in result["text"]   # nie stillschweigend modell-gedeutet
