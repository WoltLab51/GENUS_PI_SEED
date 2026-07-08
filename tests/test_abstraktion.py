"""faehigkeit:abstrahieren, Scheibe 1 (genus/abstraktion.py): GENUS findet noch UNBENANNTE
Merkmal-Buendel unter Geschwistern im eigenen Graphen -- rein lesend, modellfrei, mit dem
Ueberraschungs-Test gegen die Tautologie (docs/GENUS_INTELLIGENZ.md: Verdichtung, widerlegbar)."""
import sqlite3

from genus import abstraktion, reactors, sources
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _rel(conn, s, p, o, quelle="test"):
    reactors.observe_relation(conn, s, p, o, quelle)


def _geraet_gruppe(conn):
    # drei Geraete unter "geraet" teilen ein 3er-Buendel; ein viertes Kind teilt nichts davon
    for kind in ("foehn", "toaster", "bohrer"):
        _rel(conn, kind, "is_a", "geraet")
        _rel(conn, kind, "made_of", "kunststoff")
        _rel(conn, kind, "used_for", "haushalt")
        _rel(conn, kind, "has_part", "motor")
    _rel(conn, "buch", "is_a", "geraet")
    _rel(conn, "buch", "made_of", "papier")


def test_verdichte_findet_unbenanntes_buendel_mit_ueberraschung():
    conn = _fresh()
    _geraet_gruppe(conn)
    kandidaten = abstraktion.verdichte(conn, "geraet")
    assert len(kandidaten) == 1
    k = kandidaten[0]
    assert set(k["mitglieder"]) == {"bohrer", "foehn", "toaster"}
    assert set(k["buendel"]) == {("made_of", "kunststoff"), ("used_for", "haushalt"),
                                 ("has_part", "motor")}
    assert k["vorhergesagt"]        # teilt MEHR als die zwei Definitions-Merkmale = keine Tautologie
    assert "buch" not in k["mitglieder"]


def test_tautologie_ohne_ueberraschung_wird_verworfen():
    # drei Dinge teilen GENAU zwei unterscheidende Merkmale (< MIN_MERKMALE=3) -> keine
    # Ueberraschung ueber eine 2-Merkmal-Definition hinaus -> kein Begriff
    conn = _fresh()
    for kind in ("stuhl", "hocker", "bank"):
        _rel(conn, kind, "is_a", "moebel")
        _rel(conn, kind, "made_of", "holz")
        _rel(conn, kind, "used_for", "sitzen")
    _rel(conn, "regal", "is_a", "moebel")          # ein Nicht-Mitglied -> holz/sitzen unterscheiden
    assert abstraktion.verdichte(conn, "moebel") == []


def test_universelles_merkmal_faelscht_keine_ueberraschung():
    # Review-Fund 1: ein Merkmal, das ALLE Kinder tragen, gehoert zum "P-Sein" und darf nie als
    # Ueberraschung zaehlen. a,b,c teilen 2 unterscheidende + 1 universelles -> nur 2 zaehlen -> kein Begriff.
    conn = _fresh()
    for kind in ("a", "b", "c", "d", "e", "f"):
        _rel(conn, kind, "is_a", "ding")
        _rel(conn, kind, "part_of", "sammlung")    # von ALLEN getragen -> universell, ausgeschlossen
    for kind in ("a", "b", "c"):
        _rel(conn, kind, "made_of", "holz")
        _rel(conn, kind, "has_part", "griff")
    assert abstraktion.verdichte(conn, "ding") == []


def test_feinerer_begriff_unter_benanntem_oberbegriff_ueberlebt():
    # Review-Fund 3: die Gruppe teilt einen benannten Oberbegriff Q, aber Q hat NOCH ein weiteres
    # Kind -> Q benennt nur eine groebere Obergruppe; der feinere Begriff ist SEHR WOHL neu.
    conn = _fresh()
    _rel(conn, "Kraftfahrzeug@de", "label", "kraftfahrzeug")
    _rel(conn, "kraftfahrzeug", "is_a", "fahrzeug")
    for kind in ("auto", "bus", "lkw", "motorrad"):
        _rel(conn, kind, "is_a", "kraftfahrzeug")
        _rel(conn, kind, "is_a", "fahrzeug")
        _rel(conn, kind, "used_for", "transport")
    for kind in ("auto", "bus", "lkw"):            # nur diese drei teilen das reichere Buendel
        _rel(conn, kind, "made_of", "metall")
        _rel(conn, kind, "has_part", "motor")
        _rel(conn, kind, "has_part", "lenkrad")
    kand = abstraktion.verdichte(conn, "fahrzeug")
    assert any(set(k["mitglieder"]) == {"auto", "bus", "lkw"} for k in kand)


def test_zu_kleine_gruppe_ist_kein_begriff():
    # nur ZWEI teilen das Buendel -> unter MIN_MITGLIEDER -> ein Zufall zu zweit, kein Begriff
    conn = _fresh()
    for kind in ("a", "b"):
        _rel(conn, kind, "is_a", "sache")
        _rel(conn, kind, "made_of", "x")
        _rel(conn, kind, "used_for", "y")
        _rel(conn, kind, "has_part", "z")
    assert abstraktion.verdichte(conn, "sache") == []


def test_schon_benannte_gruppe_wird_verworfen():
    # dieselbe Merkmals-Ueberlappung, aber die Gruppe hat schon einen feineren NAMEN (kraftfahrzeug)
    # -> kein NEUER Begriff, der existiert schon
    conn = _fresh()
    _rel(conn, "Kraftfahrzeug@de", "label", "kraftfahrzeug")
    _rel(conn, "kraftfahrzeug", "is_a", "fahrzeug")
    for kind in ("auto", "bus", "lkw"):
        _rel(conn, kind, "is_a", "kraftfahrzeug")
        _rel(conn, kind, "is_a", "fahrzeug")
        _rel(conn, kind, "made_of", "metall")
        _rel(conn, kind, "used_for", "transport")
        _rel(conn, kind, "has_part", "rad")
    assert abstraktion.verdichte(conn, "fahrzeug") == []


def test_narrate_zeigt_mitglieder_ueberraschung_und_schreibt_nichts_an():
    conn = _fresh()
    _geraet_gruppe(conn)
    text = abstraktion.narrate(conn, abstraktion.verdichte(conn, "geraet")[0])
    assert "Begriffs-Kandidat" in text
    assert "foehn" in text and "toaster" in text and "bohrer" in text
    assert "Überraschung" in text
    assert "schreibe nichts" in text


def test_verdichte_und_entdecke_schreiben_nichts():
    conn = _fresh()
    _geraet_gruppe(conn)
    vorher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    abstraktion.verdichte(conn, "geraet")
    abstraktion.entdecke(conn)
    nachher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    assert vorher == nachher     # rein lesend -- kein Ledger-Schreib


def test_entdecke_findet_den_kandidaten_ueber_den_ganzen_graphen():
    conn = _fresh()
    _geraet_gruppe(conn)
    kandidaten = abstraktion.entdecke(conn)
    assert any(set(k["mitglieder"]) == {"bohrer", "foehn", "toaster"} for k in kandidaten)


def test_praege_bildet_gedeckelten_begriffs_knoten():
    # Scheibe 2: konzept is_a Elternteil, jedes Mitglied is_a konzept, plus Gloss -- alles
    # model:abstraktion (Trust <= 0.25, ueberstimmt nie Geerdetes), Proposal != Change.
    conn = _fresh()
    _geraet_gruppe(conn)
    k = abstraktion.verdichte(conn, "geraet")[0]
    r = abstraktion.praege(conn, k)
    kid = r["konzept"]
    assert kid.startswith("konzept:auto:") and r["gesaet"] > 0
    assert any(x["object"] == "geraet"
               for x in sources.relations(conn, subject=kid, predicate="is_a"))
    for m in k["mitglieder"]:
        assert any(x["object"] == kid
                   for x in sources.relations(conn, subject=m, predicate="is_a"))
    assert sources.relations(conn, subject=kid, predicate="inhalt")   # ansprechbar via genus concept
    for x in sources.relations(conn, subject=kid, predicate="is_a"):
        assert x["source"] == abstraktion.MODEL_QUELLE                # gedeckelte Herkunft
    assert sources.source_trust(conn, abstraktion.MODEL_QUELLE) <= 0.25


def test_praege_ist_idempotent():
    conn = _fresh()
    _geraet_gruppe(conn)
    k = abstraktion.verdichte(conn, "geraet")[0]
    abstraktion.praege(conn, k)
    assert abstraktion.praege(conn, k)["gesaet"] == 0     # dieselbe Gruppe -> dieselbe Id, kein Duplikat


def test_konzept_id_ist_stabil_und_reihenfolge_unabhaengig():
    assert abstraktion._konzept_id(["b", "a", "c"]) == abstraktion._konzept_id(["c", "b", "a"])


def test_gepraegter_begriff_ist_ueber_concept_meaning_ansprechbar():
    # der selbst-geschriebene Gloss (inhalt) taucht in concept_meaning auf -> `genus concept` kann
    # den selbst gebildeten Begriff erklären, nicht nur seinen is_a-Elternteil zeigen.
    conn = _fresh()
    _geraet_gruppe(conn)
    k = abstraktion.verdichte(conn, "geraet")[0]
    r = abstraktion.praege(conn, k)
    bedeutung = sources.concept_meaning(conn, r["konzept"])
    assert bedeutung["meaning"] and "geraet" in bedeutung["meaning"][0].lower()
    assert "geraet" in bedeutung["is_a"]


def test_praege_gloss_bleibt_einmalig_auch_wenn_namen_sich_aendern():
    # Review-Fund (MEDIUM): der Gloss wird aus VERAENDERLICHEN Anzeigenamen gebaut. Ein zweiter Tick,
    # nachdem ein Label eingetroffen ist (Routine, wenn Wikidata/DBnary nachfliessen), darf keinen
    # ZWEITEN, abweichenden inhalt saeen -- ein Begriff hat EINEN Gloss.
    conn = _fresh()
    _geraet_gruppe(conn)
    k = abstraktion.verdichte(conn, "geraet")[0]
    abstraktion.praege(conn, k)
    _rel(conn, "Geraet@de", "label", "geraet")     # jetzt aendert sich der Anzeigename -> "Geraet"
    abstraktion.praege(conn, k)                     # zweiter Tick
    kid = abstraktion._konzept_id(k["mitglieder"])
    assert len(sources.relations(conn, subject=kid, predicate="inhalt")) == 1
