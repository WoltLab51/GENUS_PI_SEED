"""Die HÄNDE (genus/hand.py, Ronny 2026-07-08): das eiserne Gate für Außenhandlungen — keine
Ausführung ohne aktions-genaues menschliches OK, genau einmal, fixer Boden, Anti-Weglauf,
volle Prüf-Spur. Das ist der am härtesten gegatete Teil des ganzen Systems (§8)."""
import inspect
import sqlite3

from genus import hand
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_der_ganze_weg_vorschlag_bestaetigung_ausfuehrung():
    conn = _fresh()
    v = hand.vorschlagen(conn, "nachricht", "Erinnerung: Anruf um 18 Uhr")
    assert v["vorgeschlagen"]
    hid = v["hand_id"]
    assert hand.hand(conn, hid)["status"] == hand.VORGESCHLAGEN
    assert hand.faellige(conn, "2099-01-01T00:00:00Z") == []      # unbestätigt -> nie fällig
    assert hand.bestaetigen(conn, hid)["bestaetigt"]
    assert [f["hand_id"] for f in hand.faellige(conn, "2099-01-01T00:00:00Z")] == [hid]
    assert hand.markiere_ausgefuehrt(conn, hid)["ausgefuehrt"]
    assert hand.hand(conn, hid)["status"] == hand.AUSGEFUEHRT
    assert hand.faellige(conn, "2099-01-01T00:00:00Z") == []      # danach nicht mehr fällig


def test_kernel_keine_ausfuehrung_ohne_bestaetigung():
    # DER HARTE CONSTRAINT: ein unbestätigter Vorschlag lässt sich NIE ausführen
    conn = _fresh()
    hid = hand.vorschlagen(conn, "nachricht", "heimlich senden")["hand_id"]
    r = hand.markiere_ausgefuehrt(conn, hid)
    assert r["ausgefuehrt"] is False and "NICHT freigegeben" in r["grund"]
    assert hand.faellige(conn, "2099-01-01T00:00:00Z") == []      # Membran bekommt ihn nie
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM event_log WHERE event_type='hand_ausgefuehrt'"
    ).fetchone()["n"] == 0


def test_genau_einmal_nie_doppelt():
    conn = _fresh()
    hid = hand.vorschlagen(conn, "nachricht", "x")["hand_id"]
    hand.bestaetigen(conn, hid)
    assert hand.markiere_ausgefuehrt(conn, hid)["ausgefuehrt"]
    zweiter = hand.markiere_ausgefuehrt(conn, hid)
    assert zweiter["ausgefuehrt"] is False and "einmal" in zweiter["grund"]
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM event_log WHERE event_type='hand_ausgefuehrt'"
    ).fetchone()["n"] == 1


def test_abgelehnt_wird_nie_ausgefuehrt():
    conn = _fresh()
    hid = hand.vorschlagen(conn, "nachricht", "x")["hand_id"]
    assert hand.ablehnen(conn, hid)["abgelehnt"]
    assert hand.bestaetigen(conn, hid)["bestaetigt"] is False     # nach Ablehnung nicht bestätigbar
    assert hand.markiere_ausgefuehrt(conn, hid)["ausgefuehrt"] is False


def test_fixer_boden_nur_erlaubte_art():
    # eine Art mit Geld-/Fremd-/Systemwirkung kann gar nicht erst entstehen
    conn = _fresh()
    r = hand.vorschlagen(conn, "geld_ueberweisen", "1000000 an fremd")
    assert r["vorgeschlagen"] is False and "nicht erlaubt" in r["grund"]
    assert hand.offene(conn) == []


def test_anti_weglauf_deckelt_offene():
    conn = _fresh()
    for i in range(hand.MAX_OFFENE):
        assert hand.vorschlagen(conn, "nachricht", f"m{i}")["vorgeschlagen"]
    ueberzaehlig = hand.vorschlagen(conn, "nachricht", "zu viel")
    assert ueberzaehlig["vorgeschlagen"] is False and "Zu viele" in ueberzaehlig["grund"]


def test_faellig_erst_ab_faelligkeit():
    conn = _fresh()
    hid = hand.vorschlagen(conn, "nachricht", "später",
                           faellig_um="2099-06-01T12:00:00Z")["hand_id"]
    hand.bestaetigen(conn, hid)
    assert hand.faellige(conn, "2099-01-01T00:00:00Z") == []                 # noch nicht
    assert [f["hand_id"] for f in hand.faellige(conn, "2099-12-31T00:00:00Z")] == [hid]


def test_leere_hand_gibt_es_nicht():
    conn = _fresh()
    assert hand.vorschlagen(conn, "nachricht", "   ")["vorgeschlagen"] is False


def test_kein_override_pfad_strukturell():
    # die Bestätigung IST das Gate: es gibt keinen override-Parameter, an dem man vorbeikäme
    assert "override" not in inspect.signature(hand.markiere_ausgefuehrt).parameters


def test_kaputtes_ereignis_legt_das_gate_nicht_lahm():
    # Review-Fund: ein gefälschtes/kaputtes hand_*-Ereignis (Nicht-Dict-Payload, aus einem
    # manipulierten/replizierten Ledger) darf das GANZE Gate nicht lahmlegen -- es wird
    # übersprungen, gute Hände laufen weiter
    conn = _fresh()
    gut = hand.vorschlagen(conn, "nachricht", "echte Erinnerung")["hand_id"]
    hand.bestaetigen(conn, gut)
    conn.execute("INSERT INTO event_log (event_type, payload) VALUES ('hand_vorgeschlagen', '[1,2,3]')")
    conn.commit()
    assert [f["hand_id"] for f in hand.faellige(conn, "2099-01-01T00:00:00Z")] == [gut]
    assert hand.markiere_ausgefuehrt(conn, gut)["ausgefuehrt"]   # kein Absturz, gute Hand läuft


def test_atomar_geschuetzt_read_check_append_unter_einem_lock():
    # der TOCTOU-Fix: die Mutatoren halten den Schreib-Lock über Lesen+Prüfen+Anhängen
    # (BEGIN IMMEDIATE) -- hier als Rauch-Test, dass der Weg sauber committet und nichts hängen
    # bleibt (kein offener Transaktions-Rest nach einer Ausführung)
    conn = _fresh()
    hid = hand.vorschlagen(conn, "nachricht", "x")["hand_id"]
    hand.bestaetigen(conn, hid)
    assert hand.markiere_ausgefuehrt(conn, hid)["ausgefuehrt"]
    assert conn.in_transaction is False   # sauber committet, kein haengender Lock
