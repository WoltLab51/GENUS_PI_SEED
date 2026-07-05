"""Selbst-Codieren Stufe 0 (Audit-Inversion ③): der VerstehensLuecke-Detector -- GENUS spürt
aus der eigenen Belegung, wo sein Verstehen nicht hinreicht, und macht daraus PROPOSALS über
die bestehende Proposal≠Change-Maschinerie. Ronnys Ziel ⑥ wörtlich: "spürt hin, wo eine Lücke
ist und fragt, ob es seinen Plan umsetzen darf". Der Mensch gated; nichts wird auto-angewandt."""
import json
import sqlite3

from genus import companion, experience, verstehen
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _luecken_scan(conn):
    """Nur die VerstehensLuecke-Kandidaten aus einem vollen Scan."""
    return [r for r in experience.scan(conn)
            if r.get("experience_type") == experience.VERSTEHENS_LUECKE_TYPE]


def _proposals(conn):
    rows = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'proposal_created' ORDER BY id"
    ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def test_detector_stays_quiet_without_any_lived_demand():
    conn = _fresh()
    assert experience._verstehens_luecke_candidates(conn) == []


def test_concentrated_demand_on_a_gap_leaf_becomes_a_proposal():
    conn = _fresh()
    # gelebter Druck auf einer ehrlichen Lücke (weltfrage hat keinen Handler, Zelle auch nicht)
    for _ in range(4):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    verstehen.record_reading(conn, "empfehlungsfrage", "model:deuter")   # Rauschen: 1 Lesung

    ergebnisse = _luecken_scan(conn)
    kinds = [r["pattern"]["kind"] for r in ergebnisse]
    assert kinds == ["weltfrage"]   # 4 >= Saat 3; das 1x-Rauschen bleibt unter der Schwelle
    props = [p for p in _proposals(conn)
             if p.get("payload", {}).get("experience_type") == experience.VERSTEHENS_LUECKE_TYPE
             or p.get("claim_value") == "verstehens_luecke"]
    assert props, "die Lücke muss ein echtes Proposal erzeugen, nicht nur eine Experience"


def test_proposal_carries_the_plan_and_asks_for_permission():
    conn = _fresh()
    for _ in range(5):
        verstehen.record_reading(conn, "tun", "model:deuter")
    experience.scan(conn)
    props = [p for p in _proposals(conn) if p.get("claim_value") == "verstehens_luecke"]
    assert len(props) == 1
    beschreibung = props[0]["payload"]["description"]
    assert "Lücke" in beschreibung and "Darf ich" in beschreibung   # fragt um Erlaubnis
    assert "tun" in beschreibung
    assert props[0]["payload"]["action_required"] is True


def test_handled_leaves_never_appear_as_gaps_even_with_readings():
    conn = _fresh()
    for _ in range(10):
        verstehen.record_reading(conn, "definition", "model:deuter")   # hat einen Handler
    assert experience._verstehens_luecke_candidates(conn) == []


def test_unklar_runs_count_as_their_own_blind_spot():
    conn = _fresh()
    for _ in range(4):
        verstehen.record_reading(conn, "unklar", "model:deuter")
    ergebnisse = _luecken_scan(conn)
    assert [r["pattern"]["kind"] for r in ergebnisse] == ["unklar"]
    beschreibung = [p for p in _proposals(conn)
                    if p.get("claim_value") == "verstehens_luecke"][0]["payload"]["description"]
    assert "gar nicht deuten" in beschreibung
    # Gesamtprüfungs-Fund: "unklar" ist kein Blatt -- sein Plan muss "besser deuten" sein,
    # nicht "dieses Blatt soll eine Fähigkeit bekommen" (das kann es nie)
    assert "Deuten selbst muss besser werden" in beschreibung
    assert "dieses Blatt" not in beschreibung


def test_threshold_is_self_calibrated_from_the_own_population_not_a_preset():
    conn = _fresh()
    # zwei klar getrennte Gruppen: {1,2} Rauschen vs. {9} Druck -> breiteste Lücke
    # setzt die Schwelle über das Rauschen, auch wenn 2 nahe der Saat liegt
    verstehen.record_reading(conn, "empfehlungsfrage", "model:deuter")
    for _ in range(2):
        verstehen.record_reading(conn, "korrektur", "model:deuter")
    for _ in range(9):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    kandidaten = experience._verstehens_luecke_candidates(conn)
    assert [c["pattern"]["kind"] for c in kandidaten] == ["weltfrage"]
    assert kandidaten[0]["pattern"]["threshold"] == 3   # 2+1: knapp über der Rausch-Gruppe


def test_seed_stays_a_validity_floor_when_all_demand_is_tiny():
    conn = _fresh()
    # zwei Blätter mit 1 und 2 Lesungen: die breiteste Lücke lieferte Schwelle 2 -- aber die
    # Saat (3) ist eine GÜLTIGKEITS-Untergrenze und wird nie unterschritten -> kein Kandidat
    verstehen.record_reading(conn, "weltfrage", "model:deuter")
    for _ in range(2):
        verstehen.record_reading(conn, "tun", "model:deuter")
    assert experience._verstehens_luecke_candidates(conn) == []


def test_scan_is_idempotent_no_duplicate_proposals():
    conn = _fresh()
    for _ in range(4):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    experience.scan(conn)
    experience.scan(conn)   # zweiter Lauf: experience_key existiert -> kein neues Proposal
    props = [p for p in _proposals(conn) if p.get("claim_value") == "verstehens_luecke"]
    assert len(props) == 1


def test_two_hot_gaps_are_proposed_one_per_scan_none_lost():
    # der Konstruktionsfehler, der beim Bauen auffiel: zwei gleichzeitig heiße Lücken + die
    # 1-Proposal-pro-Scan-Kappe hätten das zweite Proposal für immer verschluckt (Experience
    # existiert -> künftige Scans überspringen). Jetzt meldet der Detector pro Lauf nur die
    # drängendste NEUE Lücke; die nächste rückt beim nächsten Scan nach.
    conn = _fresh()
    for _ in range(9):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    for _ in range(7):
        verstehen.record_reading(conn, "tun", "model:deuter")
    experience.scan(conn)
    experience.scan(conn)
    props = [p for p in _proposals(conn) if p.get("claim_value") == "verstehens_luecke"]
    beschriebene = {p["claim_key"] for p in props}
    assert beschriebene == {"verstehen.weltfrage", "verstehen.tun"}   # beide, keins verloren
    assert len(props) == 2


def test_unklar_reading_is_recorded_when_the_deuter_finds_nothing():
    # der bisher UNGEZÄHLTE Fall: Deuter lief, leere Liste -> _NICHT_VERSTANDEN. Ab jetzt zählt
    # er als Struktur (nie Text) auf absicht:unklar -- das Material für den Detector
    conn = _fresh()
    companion.respond_with_deuter(conn, "xyzzy quux", deuter=lambda q: [])
    assert verstehen.belegung(conn, "unklar")["gesamt"] == 1


def test_unklar_segment_reading_is_recorded_too():
    conn = _fresh()
    deuter = lambda q: [{"absicht": "unklar", "text": q}]
    companion.respond_with_deuter(conn, "völlig rätselhafte eingabe", deuter=deuter)
    assert verstehen.belegung(conn, "unklar")["gesamt"] == 1


# --- Der Takt ist ein Merkmal des Detektors (Ronny 2026-07-05: „verallgemeinern") --------

def test_takt_registry_trennt_gespraechsnah_von_historisch():
    takte = {d.funktion.__name__: d.takt for d in experience.DETEKTOREN}
    assert takte["_verstehens_luecke_candidates"] == experience.GESPRAECHSNAH
    for hist in ("_activity_daily_rhythm_candidates", "_belief_stability_candidates",
                 "_rule_calibration_candidates"):
        assert takte[hist] == experience.HISTORISCH
    # der gesprächsnahe Detektor ist genau der Lücken-Detektor
    assert experience.gespraechsnahe_detektoren() == (experience._verstehens_luecke_candidates,)
    # die rückwärts-kompatible Sicht bleibt die volle Funktionsliste
    assert set(experience.DETECTORS) == {d.funktion for d in experience.DETEKTOREN}


def test_spontane_regung_feuert_die_gelebte_luecke_sofort():
    conn = _fresh()
    for _ in range(4):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    regung = experience.spontane_regung(conn)
    assert regung is not None
    assert regung["kind"] == "weltfrage" and regung["proposal_id"]
    # dieselbe Lücke wird danach nicht doppelt aufgezeichnet (der Nacht-Scan holt nichts nach)
    assert _luecken_scan(conn) == []


def test_spontane_regung_schweigt_ohne_reifes_signal():
    conn = _fresh()
    verstehen.record_reading(conn, "weltfrage", "model:deuter")   # 1 Lesung, unter der Schwelle
    assert experience.spontane_regung(conn) is None


def test_spontane_regung_laesst_die_historischen_detektoren_ruhen():
    # ein gesprächsnaher Moment weckt NICHT die täglichen Historien-Betrachter
    conn = _fresh()
    for _ in range(4):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    experience.spontane_regung(conn)
    typen = {r["experience_type"] for r in conn.execute(
        "SELECT DISTINCT experience_type FROM experience_log").fetchall()}
    assert typen == {experience.VERSTEHENS_LUECKE_TYPE}   # nur die Regung, kein Rhythmus/Stabilität


def test_ein_neuer_gespraechsnaher_detektor_laeuft_ohne_scan_aenderung(monkeypatch):
    # der Kern der Verallgemeinerung: einen neuen event-getriebenen Detektor registrieren
    # heißt nur, GESPRAECHSNAH zu deklarieren -- spontane_regung nimmt ihn von selbst mit
    gerufen = {"n": 0}

    def _fake_detektor(conn):
        gerufen["n"] += 1
        return []   # kein Kandidat -> keine Nebenwirkung, wir prüfen nur, DASS er läuft

    neu = experience.DETEKTOREN + (experience.Detektor(_fake_detektor, experience.GESPRAECHSNAH),)
    monkeypatch.setattr(experience, "DETEKTOREN", neu)
    conn = _fresh()
    experience.spontane_regung(conn)
    assert gerufen["n"] == 1   # ohne eine Zeile in scan/spontane_regung zu ändern


def test_rhythm_proposals_keep_their_old_shape_backward_compatible():
    # die Generalisierung von record_experience_proposal darf den Rhythmus-Default nicht ändern
    candidate = {
        "experience_key": "k", "experience_type": "ActivityDailyRhythm", "subject_key": "s",
        "summary": "zusammenfassung", "experience_id": 1,
    }
    conn = _fresh()
    experience.record_experience_proposal(conn, candidate, experience_event_id=1)
    p = _proposals(conn)[0]
    assert p["claim_value"] == "daily_rhythm"
    assert p["payload"]["action_required"] is False
    assert "Recurring experience" in p["payload"]["description"]
