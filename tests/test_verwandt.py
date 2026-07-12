"""Die Verwandtschaft (genus.verwandt + auskunft.verwandt_frage/narrate_verwandt): Begriffe nach
BEDEUTUNGS-NÄHE als Gewicht. Das Lese-Ende ist rein deterministisch (Graph-Lesen + Sortieren);
die Gewichte selbst kommen offline vom Embedder (deploy/verwandtschaft.py, dort gemessen)."""
import sqlite3

from genus import auskunft, reactors, verwandt
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _wort(conn, wort, qid):
    reactors.observe_relation(conn, f"{wort}@de", "expresses", qid, "wikidata")


def _verw(conn, a, b, cos, source="model:embedder"):
    reactors.observe_relation(conn, a, "verwandt", b, source, derivation=f"cos={cos}")


def _tiere(conn):
    _wort(conn, "Hund", "Q144")
    _wort(conn, "Wolf", "Q18498")
    _wort(conn, "Katze", "Q146")
    _wort(conn, "Goldfisch", "Q123599")
    _verw(conn, "Q144", "Q18498", 0.71)   # Hund ~ Wolf (nah)
    _verw(conn, "Q144", "Q146", 0.66)     # Hund ~ Katze
    _verw(conn, "Q144", "Q123599", 0.41)  # Hund ~ Goldfisch (fern)
    return conn


def test_gewicht_aus_herleitung():
    assert verwandt.gewicht_aus_herleitung("cos=0.71") == 0.71
    assert verwandt.gewicht_aus_herleitung("source:model:embedder cos=0.5") == 0.5
    assert verwandt.gewicht_aus_herleitung("source:model:embedder") is None
    assert verwandt.gewicht_aus_herleitung(None) is None


def test_verwandte_ordnet_nach_gewicht_der_naechste_zuerst():
    conn = _tiere(_fresh())
    r = verwandt.verwandte(conn, "Hund")
    assert r["found"] and r["concept"] == "Q144"
    namen = [v["name"] for v in r["verwandte"]]
    assert namen == ["Wolf", "Katze", "Goldfisch"]        # streng nach Gewicht
    assert r["verwandte"][0]["gewicht"] == 0.71           # Wolf ist am nächsten


def test_verwandtschaft_ist_symmetrisch_beide_richtungen():
    # die Kante wurde Hund->Wolf geschrieben; die Frage nach WOLF findet Hund trotzdem
    conn = _tiere(_fresh())
    r = verwandt.verwandte(conn, "Wolf")
    assert r["found"]
    assert "Hund" in [v["name"] for v in r["verwandte"]]


def test_k_begrenzt_die_liste():
    conn = _tiere(_fresh())
    r = verwandt.verwandte(conn, "Hund", k=2)
    assert [v["name"] for v in r["verwandte"]] == ["Wolf", "Katze"]


def test_bekanntes_wort_ohne_kanten_ist_found_mit_leerer_liste():
    conn = _fresh()
    _wort(conn, "Tisch", "Q14748")            # bekannt, aber keine verwandt-Kante
    r = verwandt.verwandte(conn, "Tisch")
    assert r["found"] and r["verwandte"] == []


def test_unbekanntes_wort_ist_not_found():
    conn = _fresh()
    assert verwandt.verwandte(conn, "Xyzzy")["found"] is False


def test_blanker_q_knoten_ohne_namen_wird_uebersprungen():
    conn = _fresh()
    _wort(conn, "Hund", "Q144")
    _verw(conn, "Q144", "Q999999", 0.8)       # kein Name für Q999999
    r = verwandt.verwandte(conn, "Hund")
    assert r["found"] and r["verwandte"] == []   # nie ein kryptischer Q-Knoten in der Antwort


def test_dublette_gleicher_name_nimmt_das_staerkere_gewicht():
    conn = _fresh()
    _wort(conn, "Hund", "Q144")
    _wort(conn, "Katze", "Q146")
    _wort(conn, "Katze", "Q146b")             # zwei Q-ids, gleicher Anzeigename „Katze"
    _verw(conn, "Q144", "Q146", 0.6)
    _verw(conn, "Q144", "Q146b", 0.72)
    r = verwandt.verwandte(conn, "Hund")
    katzen = [v for v in r["verwandte"] if v["name"] == "Katze"]
    assert len(katzen) == 1 and katzen[0]["gewicht"] == 0.72


# --- die Frage-Erkennung + Narration -----------------------------------------------------

def test_verwandt_frage_erkennt_die_formulierungen():
    conn = _tiere(_fresh())
    for frage in ["Was ist mit Hund verwandt?", "Was ist Hund ähnlich?",
                  "Womit hängt Hund zusammen?", "verwandte Begriffe zu Hund",
                  "Was ist ähnlich wie Hund?"]:
        r = auskunft.verwandt_frage(conn, frage)
        assert r["verwandt_q"], frage
        assert r["wort"] == "Hund"


def test_verwandt_frage_greift_nicht_ins_leere_bei_unbekanntem_wort():
    conn = _fresh()
    assert auskunft.verwandt_frage(conn, "Was ist mit Xyzzy verwandt?")["verwandt_q"] is False


def test_artikel_praefix_wird_nicht_vom_wort_abgebissen():
    # Regression: der optionale Artikel _ART? darf keinen Wort-ANFANG fressen — „Demokratie"
    # wurde als „dem" + „okratie" zerlegt, „Denkmal" als „den" + „kmal". Betrifft den ganzen
    # Muster-Satz (Klasse), hier am Verwandt-Extraktor gesichert.
    from genus.auskunft import _verwandt_subjekt
    assert _verwandt_subjekt("Was ist mit Demokratie verwandt?") == "Demokratie"
    assert _verwandt_subjekt("Womit hängt Denkmal zusammen?") == "Denkmal"
    assert _verwandt_subjekt("Was ist mit Einhorn verwandt?") == "Einhorn"
    assert _verwandt_subjekt("Was ist mit der Katze verwandt?") == "Katze"   # echter Artikel weg


def test_narrate_verwandt_nennt_die_begriffe_geordnet_mit_gewicht():
    conn = _tiere(_fresh())
    r = auskunft.verwandt_frage(conn, "Was ist mit Hund verwandt?")
    text = auskunft.narrate_verwandt(conn, r)
    assert "»Wolf«" in text and "»Katze«" in text
    assert text.index("»Wolf«") < text.index("»Katze«")   # der nächste zuerst
    assert "0.71" in text                                  # das Gewicht ist sichtbar


def test_narrate_verwandt_ist_ehrlich_bei_duennem_netz():
    conn = _fresh()
    _wort(conn, "Tisch", "Q14748")
    r = auskunft.verwandt_frage(conn, "Was ist mit Tisch verwandt?")
    # bekanntes Wort ohne Kanten -> verwandt_q True, aber leere Liste -> ehrliche Antwort
    assert r["verwandt_q"]
    assert "noch" in auskunft.narrate_verwandt(conn, r).lower()
