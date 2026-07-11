"""Die Formwahl (genus.formwahl): der unbestimmte Artikel für die eigene Stimme, mit Vorfahrt.
Gegründetes Genus schlägt die eigene Regel schlägt das gewogene Organ; gegründete
Mehrdeutigkeit ist endgültig. Getestet wird die KETTE deterministisch -- ob die Waage gut
wiegt, misst die Blind-Probe (test_blindprobe)."""
import sqlite3

from genus import formwahl, reactors
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _gender(conn, noun, gender, source="wikidata-lexemes"):
    reactors.observe_relation(conn, f"{noun}@de", "grammatical_gender", gender, source)


def test_gegruendetes_genus_gewinnt_vor_regel_und_waage():
    conn = _fresh()
    _gender(conn, "Haustier", "neutrum")
    # eine Waage, die LÜGEN würde -- darf trotzdem nie ans gegründete Genus heran
    r = formwahl.artikel_ein(conn, "Haustier", waage=lambda n: "eine")
    assert r == {"artikel": "ein", "weg": "gegruendet"}


def test_feminin_wird_zu_eine():
    conn = _fresh()
    _gender(conn, "Frucht", "feminin")
    assert formwahl.artikel_ein(conn, "Frucht")["artikel"] == "eine"


def test_gegruendete_mehrdeutigkeit_ist_endgueltig_none():
    # der See (maskulin) / die See (feminin): verschiedene Artikel -> keine Entscheidung,
    # und NICHTS darf sie überstimmen (auch keine selbstbewusste Waage)
    conn = _fresh()
    _gender(conn, "See", "maskulin")
    _gender(conn, "See", "feminin")
    assert formwahl.artikel_ein(conn, "See", waage=lambda n: "ein") is None


def test_gleiches_genus_aus_zwei_quellen_bleibt_entschieden():
    # zwei Belege, GLEICHER Artikel -> weiter eindeutig (nicht als "mehrdeutig" verworfen)
    conn = _fresh()
    _gender(conn, "Hund", "maskulin", source="wikidata-lexemes")
    _gender(conn, "Hund", "maskulin", source="dwds")
    assert formwahl.artikel_ein(conn, "Hund") == {"artikel": "ein", "weg": "gegruendet"}


def test_ohne_beleg_greift_die_eigene_suffix_regel():
    conn = _fresh()
    # -chen ist ein nahezu kategorisches Neutrum-Signal (echte Grammatik) -> die Regel trägt
    for noun in ("Mädchen", "Kaninchen", "Häuschen", "Brötchen", "Kätzchen"):
        _gender(conn, noun, "neutrum")
    r = formwahl.artikel_ein(conn, "Vögelchen")   # ungesehen, aber -chen
    assert r == {"artikel": "ein", "weg": "regel"}


def test_ohne_beleg_und_ohne_regel_traegt_die_waage_nur_ueber_der_schwelle():
    conn = _fresh()   # kein Genus, keine Regel-Grundlage
    r = formwahl.artikel_ein(conn, "Xylophon", waage=lambda n: "ein")
    assert r == {"artikel": "ein", "weg": "gewogen"}


def test_ohne_alles_ist_es_ehrlich_none():
    conn = _fresh()
    assert formwahl.artikel_ein(conn, "Xylophon") is None            # keine Waage injiziert
    assert formwahl.artikel_ein(conn, "Xylophon", waage=lambda n: None) is None   # Waage unter Schwelle


def test_jeder_weg_wird_gezaehlt(tmp_path, monkeypatch):
    monkeypatch.setenv("GENUS_PLANER_ZAEHLWERK", str(tmp_path / "z.jsonl"))
    from genus import zaehlwerk
    conn = _fresh()
    _gender(conn, "Frucht", "feminin")
    formwahl.artikel_ein(conn, "Frucht")
    formwahl.artikel_ein(conn, "Unbekannt")   # -> offen
    stand = zaehlwerk.stand()
    assert stand.get("formwahl:gegruendet") == 1
    assert stand.get("formwahl:offen") == 1
