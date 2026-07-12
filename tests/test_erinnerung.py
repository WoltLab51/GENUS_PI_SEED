"""Episoden statt flacher Notizen (genus.erinnerung, Punkt 1+2 von docs/design/MEMORY.md).

Bewusst NICHT mit "Hund" getestet (live-Feedback 2026-07-03: dieselbe Beispielwahl in jedem
Test/jeder Live-Probe der ganzen Sitzung deckt echte Schwächen nicht auf, weil sie nie eine
andere Flexionsform, ein zweites unabhängiges Thema oder ein konzeptloses Wort durchspielt).
Stattdessen: "Fahrrad" (hat ein Konzept, regelmäßig UND unregelmäßig flektiert), "Tisch" (hat
ein Konzept, regelmäßiger Plural -- prüft die Endungs-Toleranz gezielt) und "Konzert" (nur eine
DBnary-Glosse, KEIN Konzept -- prüft den Lexem-Rückfall), je als eigenständiges Thema, damit
Verwechslungen zwischen zwei Themen genauso auffallen würden wie ein falscher Treffer."""
import sqlite3

from genus import erinnerung, reactors
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _mit_begriffen():
    conn = _fresh()
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Tisch@de", "expresses", "Q_tisch", "wikidata")
    reactors.observe_relation(conn, "Konzert@de", "defined_as", "eine musikalische Auffuehrung", "dbnary")
    return conn


def test_merke_schreibt_genau_vier_kanten_mit_derselben_quelle():
    conn = _mit_begriffen()
    eid = erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    e = erinnerung._episode(conn, eid)
    assert e["inhalt"] == "mein Fahrrad hat einen Platten"
    assert e["quelle"] == "ronny"
    assert e["am"]   # ein Datum wurde gesetzt
    assert e["erwaehnt"] == ["Q_fahrrad"]   # Konzept-Anker, nicht die Wortform


def test_zwei_episoden_bekommen_verschiedene_ids_auch_ruecken_an_ruecken():
    # live gefunden (2026-07-03): time.time_ns() lieferte auf diesem System denselben Wert
    # fuenfmal hintereinander -- zwei schnell erzeugte Episoden waeren also kollidiert
    conn = _mit_begriffen()
    ids = {erinnerung.merke(conn, f"Ereignis Nummer {i}", quelle="ronny") for i in range(20)}
    assert len(ids) == 20


def test_reihenfolge_kommt_aus_der_projektion_nicht_aus_der_id():
    conn = _mit_begriffen()
    erinnerung.merke(conn, "zuerst: der Tisch wackelt", quelle="ronny")
    erinnerung.merke(conn, "danach: das Konzert war laut", quelle="ronny")
    alle = erinnerung.episoden(conn)
    assert [e["inhalt"] for e in alle] == ["zuerst: der Tisch wackelt", "danach: das Konzert war laut"]


def test_konzept_anker_verbindet_singular_und_regelmaessigen_plural():
    conn = _mit_begriffen()
    erinnerung.merke(conn, "der Tisch wackelt", quelle="ronny")
    treffer = erinnerung.verwandte_episoden(conn, "was ist mit den Tischen im Buero")
    assert [t["inhalt"] for t in treffer] == ["der Tisch wackelt"]


def test_unregelmaessiger_umlaut_plural_bleibt_ehrlich_unerkannt():
    # keine Morphologie-Analyse, nur Endungs-Kandidaten -- "Fahrraeder" (Umlaut-Plural von
    # Fahrrad) ist kein Endungs-Fall und darf deshalb NICHT stillschweigend erraten werden
    conn = _mit_begriffen()
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    treffer = erinnerung.verwandte_episoden(conn, "wie war das noch mit den Fahrraedern")
    assert treffer == []


def test_begriff_ohne_konzept_faellt_auf_die_lexem_kante_zurueck():
    conn = _mit_begriffen()
    eid = erinnerung.merke(conn, "ich war gestern auf einem Konzert", quelle="ronny")
    e = erinnerung._episode(conn, eid)
    assert e["erwaehnt"] == ["Konzert@de"]
    treffer = erinnerung.verwandte_episoden(conn, "wie war das Konzert")
    assert [t["inhalt"] for t in treffer] == [e["inhalt"]]


def test_zwei_unabhaengige_themen_werden_nicht_verwechselt():
    conn = _mit_begriffen()
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    erinnerung.merke(conn, "ich war gestern auf einem Konzert", quelle="ronny")
    nur_fahrrad = erinnerung.verwandte_episoden(conn, "was ist mit meinem Fahrrad los")
    assert [t["inhalt"] for t in nur_fahrrad] == ["mein Fahrrad hat einen Platten"]
    nur_konzert = erinnerung.verwandte_episoden(conn, "wie war das Konzert")
    assert [t["inhalt"] for t in nur_konzert] == ["ich war gestern auf einem Konzert"]


def test_bestaetigt_und_vermutet_bleiben_nach_quelle_getrennt():
    conn = _mit_begriffen()
    erinnerung.merke(conn, "der Tisch wackelt", quelle="ronny")
    erinnerung.merke(conn, "ich soll mein Fahrrad reparieren lassen", quelle="model:deuter")
    assert erinnerung.bestaetigte_episoden(conn) == ["der Tisch wackelt"]
    assert erinnerung.vermutete_episoden(conn) == ["ich soll mein Fahrrad reparieren lassen"]


def test_historische_nacht_aggregate_sind_keine_persoenliche_vermutung():
    conn = _mit_begriffen()
    erinnerung.merke(conn, "Gestern ging es mehrfach um den Tisch", quelle="model:nacht")
    erinnerung.merke(conn, "ich soll mein Fahrrad reparieren lassen", quelle="model:deuter")

    assert erinnerung.vermutete_episoden(conn) == ["ich soll mein Fahrrad reparieren lassen"]


def test_neueste_episode_zuerst_bei_mehreren_treffern():
    conn = _mit_begriffen()
    erinnerung.merke(conn, "das Konzert war laut", quelle="ronny")
    erinnerung.merke(conn, "das naechste Konzert kommt im Herbst", quelle="ronny")
    treffer = erinnerung.verwandte_episoden(conn, "erzaehl mir vom Konzert")
    assert [t["inhalt"] for t in treffer] == ["das naechste Konzert kommt im Herbst", "das Konzert war laut"]


def test_verwandte_episoden_ohne_bekannten_begriff_ist_leer():
    conn = _mit_begriffen()
    erinnerung.merke(conn, "der Tisch wackelt", quelle="ronny")
    assert erinnerung.verwandte_episoden(conn, "wie ist das Wetter heute") == []


def test_migriere_notizen_ueberfuehrt_und_zieht_die_alten_kanten_zurueck():
    conn = _mit_begriffen()
    reactors.observe_relation(conn, "genus:notizen", "notiz", "das Konzert war laut", "ronny")
    reactors.observe_relation(conn, "genus:notizen", "notiz", "der Tisch wackelt", "model:deuter")
    n = erinnerung.migriere_notizen(conn)
    assert n == 2
    assert erinnerung.bestaetigte_episoden(conn) == ["das Konzert war laut"]
    assert erinnerung.vermutete_episoden(conn) == ["der Tisch wackelt"]
    from genus import sources
    assert sources.relations(conn, subject="genus:notizen", predicate="notiz") == []
    assert erinnerung.migriere_notizen(conn) == 0   # idempotent: nichts mehr zu migrieren
