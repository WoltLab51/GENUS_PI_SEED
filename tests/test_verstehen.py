"""Der Verstehens-Würfel als echte Zwicky-Box (genus.verstehen): drei unabhängige Parameter
(Sprechakt, Gegenstand, Bezug), eine geprüfte Kreuz-Konsistenz-Tabelle, Feinblätter als is_a-Kinder
ihrer Kreuzprodukt-Zelle. Das Raster ist Wissen in derselben Form wie alles andere Wissen -- gesät
mit Quelle "ronny", gelesen mit Herkunft, gezählt read-time aus dem Event-Log."""
import json
import sqlite3

from genus import verstehen
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_seed_raster_sows_leaves_and_zellen_exactly_once():
    conn = _fresh()
    # jede Zelle kombiniert_aus Sprechakt + Bezug (+ Gegenstand, falls vorhanden)
    erwartete_komb_kanten = sum(3 if gegenstand is not None else 2 for (_, gegenstand) in verstehen.ZELLEN)
    erwartet = erwartete_komb_kanten + len(verstehen.RASTER_SEED)
    sown = verstehen.seed_raster(conn)
    assert sown == erwartet
    assert verstehen.seed_raster(conn) == 0   # idempotent: a re-run sows nothing new
    leaf_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM relation_projection WHERE subject LIKE 'absicht:%'"
    ).fetchone()
    assert leaf_rows["n"] == len(verstehen.RASTER_SEED)   # and duplicates nothing in the projection
    zelle_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM relation_projection WHERE subject LIKE 'zelle:%'"
    ).fetchone()
    assert zelle_rows["n"] == erwartete_komb_kanten


def test_zellen_is_a_true_cross_product_not_just_naming():
    # jede Zelle ist über gewöhnliche, herkunftstragende Relationen mit ihren Parametern
    # verbunden -- "welche Zellen nutzen gegenstand:welt?" ist eine echte Graph-Abfrage
    conn = _fresh()
    verstehen.seed_raster(conn)
    assert verstehen.zellen_von(conn, gegenstand="welt") == ["aufforderung-welt", "frage-welt"]
    assert "frage-begriff" in verstehen.zellen_von(conn, sprechakt="frage")
    assert "floskel" not in verstehen.zellen_von(conn, gegenstand="welt")


def test_kreuz_konsistenz_excludes_unstimmige_kombinationen():
    # Zwickys Schritt 4: nicht jede der 3×5 möglichen (Sprechakt,Gegenstand)-Kombinationen ist
    # gesät -- ausgeschlossene sind dokumentiert (Moduldoc), nicht stillschweigend vergessen
    conn = _fresh()
    verstehen.seed_raster(conn)
    gesaete = set(verstehen.ZELLEN.values())
    assert len(gesaete) == 11   # 10 (Sprechakt,Gegenstand)-Zellen + die gegenstandslose Floskel
    for ausgeschlossen in ("aussage-genus", "aussage-gespraech", "aufforderung-begriff",
                           "aufforderung-nutzer", "aussage-welt"):
        assert ausgeschlossen not in gesaete


def test_seed_source_is_ronny_full_human_trust():
    from genus import sources
    conn = _fresh()
    verstehen.seed_raster(conn)
    edges = sources.relations(conn, subject=verstehen.node("definition"), predicate="is_a")
    assert [e["source"] for e in edges] == [verstehen.SEED_SOURCE]
    assert not verstehen.SEED_SOURCE.startswith(sources.MODEL_SOURCE_PREFIX)


def test_kinds_and_leaf_kinds_cover_the_raster():
    conn = _fresh()
    verstehen.seed_raster(conn)
    kinds = verstehen.kinds(conn)
    assert {"definition", "empfehlungsfrage", "gruss", "weltfrage", "tun"} <= kinds
    leaves = verstehen.leaf_kinds(conn)
    assert leaves == sorted(kinds)   # every absicht node IS a leaf now -- Zellen are a different namespace
    # Zellen (das neue Kreuzprodukt) sind NIE Blätter -- sie sind nur Landeplätze, nie eine
    # dem Modell angebotene Lesart
    for zelle in verstehen.ZELLEN.values():
        assert zelle not in leaves


def test_zelle_of_climbs_exactly_one_step():
    conn = _fresh()
    verstehen.seed_raster(conn)
    assert verstehen.zelle_of(conn, "eigenschaft") == "frage-begriff"
    assert verstehen.zelle_of(conn, "gruss") == "floskel"
    assert verstehen.zelle_of(conn, "unbekanntes-blatt") is None


def test_record_reading_stores_structure_only_never_conversation_text():
    conn = _fresh()
    verstehen.seed_raster(conn)
    verstehen.record_reading(conn, "definition", "muster")
    verstehen.record_reading(conn, "definition", "model:deuter")
    payloads = [row["payload"] for row in conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'relation_asserted'"
    ).fetchall()]
    for raw in payloads:
        p = json.loads(raw)
        if p.get("predicate") == verstehen.READING_PREDICATE:
            assert p["object"] in ("muster", "model:deuter")   # Herkunft, kein Gesprächstext


def test_belegung_counts_per_herkunft_from_the_event_log():
    conn = _fresh()
    verstehen.seed_raster(conn)
    for _ in range(3):
        verstehen.record_reading(conn, "beziehung", "muster")
    verstehen.record_reading(conn, "beziehung", "model:deuter")
    b = verstehen.belegung(conn, "beziehung")
    assert b["gesamt"] == 4
    assert b["je_quelle"] == {"muster": 3, "model:deuter": 1}
    assert verstehen.belegung(conn, "vergleich")["gesamt"] == 0


def test_belegung_is_retraction_aware_so_a_miscount_can_be_corrected():
    # a reading is an ordinary relation -- a stray mark (e.g. a verification run that wrote
    # into the live ledger) is taken back the ordinary way, and the Kennzahl nets it out
    from genus import reactors
    conn = _fresh()
    verstehen.seed_raster(conn)
    verstehen.record_reading(conn, "empfehlungsfrage", "model:deuter")
    verstehen.record_reading(conn, "empfehlungsfrage", "model:deuter")
    assert verstehen.belegung(conn, "empfehlungsfrage")["gesamt"] == 2
    reactors.retract_relation(conn, verstehen.node("empfehlungsfrage"),
                              verstehen.READING_PREDICATE, "model:deuter", source="model:deuter")
    reactors.retract_relation(conn, verstehen.node("empfehlungsfrage"),
                              verstehen.READING_PREDICATE, "model:deuter", source="model:deuter")
    b = verstehen.belegung(conn, "empfehlungsfrage")
    assert b["gesamt"] == 0 and b["je_quelle"] == {}   # netted back to clean


def test_conversational_wuerfel_records_but_the_users_words_never_reach_the_ledger():
    # the whole Würfel round-trip on the bot path: a muster answer is counted (Belegung), and
    # NO event payload anywhere contains the user's actual words
    from genus import companion, reactors
    conn = _fresh()
    verstehen.seed_raster(conn)
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Säugetier@de", "expresses", "Q_m", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_m", "wikidata")
    frage = "Ist ein Hund ein Säugetier?"
    result = companion.respond_with_deuter(conn, frage, deuter=lambda q: None)
    assert result["text"].startswith("Ja.")
    assert verstehen.belegung(conn, "beziehung")["je_quelle"] == {"muster": 1}
    for row in conn.execute("SELECT payload FROM event_log").fetchall():
        assert frage not in row["payload"]   # Ledger != Memory: Struktur ja, Gesprächstext nie


def test_plain_respond_stays_pure_and_writes_no_readings():
    # the CLI voice must not gain a write path through the Würfel -- recording is deliberate
    # and belongs to the conversational channel only
    from genus import companion, reactors
    conn = _fresh()
    verstehen.seed_raster(conn)
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    before = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    companion.respond(conn, "Was ist ein Hund?")
    after = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    assert after == before
