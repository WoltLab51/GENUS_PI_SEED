"""Selbst-Codieren Stufe 1 (genus/umsetzung.py): ein genehmigtes Proposal wird umgesetzt —
der Kreis „spüren → vorschlagen → fragen → BAUEN" endet nicht mehr an der Freigabe.
Die Gate-Politik (docs/GENUS_ARCHITEKTUR.md §8) ist strukturell verankert: ohne Freigabe
keine Ausführung, nie doppelt, nur registrierte Graph-Wissen-Arten."""
import json
import sqlite3

from genus import experience, proposals, umsetzung, verstehen, ziele
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _luecken_proposal(conn, blatt: str = "weltfrage") -> int:
    """Der echte Weg: gelebte Nachfrage auf einem handler-losen Blatt -> Scan -> Proposal."""
    verstehen.seed_raster(conn)
    for _ in range(4):
        verstehen.record_reading(conn, blatt, "model:deuter")
    experience.scan(conn)
    rows = proposals.list_proposals(conn)
    kandidaten = [r for r in rows
                  if json.loads(r["payload"]).get("experience_type") == "VerstehensLuecke"]
    assert kandidaten, "Scan hat kein VerstehensLuecke-Proposal erzeugt"
    return int(kandidaten[0]["id"])


def test_luecken_proposal_traegt_seine_umsetzung_deklarativ():
    conn = _fresh()
    pid = _luecken_proposal(conn)
    payload = json.loads(proposals.get_proposal(conn, pid)["payload"])
    assert payload["umsetzung"] == {
        "art": "faehigkeits_ziel",
        "blatt": "weltfrage",
        "beschreibung": payload["umsetzung"]["beschreibung"],
    }
    assert "weltfrage" in payload["umsetzung"]["beschreibung"]


def test_ohne_freigabe_wird_nie_umgesetzt():
    conn = _fresh()
    pid = _luecken_proposal(conn)
    ergebnis = umsetzung.umsetzen(conn, pid)   # Proposal ist noch pending
    assert ergebnis["umgesetzt"] is False and "Gate" in ergebnis["grund"]
    assert ziele.fehlende_faehigkeiten(conn) == []   # nichts gesät


def test_ablehnung_setzt_nie_um():
    conn = _fresh()
    pid = _luecken_proposal(conn)
    proposals.review_proposal_governed(conn, pid, "rejected", note="nein")
    ergebnis = umsetzung.umsetzen(conn, pid)
    assert ergebnis["umgesetzt"] is False
    assert ziele.fehlende_faehigkeiten(conn) == []


def test_freigabe_verankert_die_faehigkeit_im_ziel_graphen():
    conn = _fresh()
    ziele.seed_ziele(conn)
    pid = _luecken_proposal(conn)
    proposals.review_proposal_governed(conn, pid, "accepted", note="ja, priorisieren")
    ergebnis = umsetzung.umsetzen(conn, pid)
    assert ergebnis["umgesetzt"] is True and ergebnis["art"] == "faehigkeits_ziel"
    # die Lücke ist jetzt eine benannte Fähigkeit mit Status fehlt, dient ziel:verstehen
    fehlend = ziele.fehlende_faehigkeiten(conn)
    assert any(f["id"] == "faehigkeit:weltfrage" for f in fehlend)
    # und GENUS benennt sie selbst, wenn man fragt, was ihm fehlt
    from genus import companion
    antwort = companion.narrate_ziele(conn)
    assert "weltfrage" in antwort


def test_umsetzung_laeuft_genau_einmal():
    conn = _fresh()
    ziele.seed_ziele(conn)
    pid = _luecken_proposal(conn)
    proposals.review_proposal_governed(conn, pid, "accepted")
    assert umsetzung.umsetzen(conn, pid)["umgesetzt"] is True
    zweiter = umsetzung.umsetzen(conn, pid)
    assert zweiter["umgesetzt"] is False and "schon umgesetzt" in zweiter["grund"]
    # exakt EIN Spur-Event
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM event_log WHERE event_type = 'proposal_umgesetzt'"
    ).fetchone()["n"]
    assert n == 1


def test_unregistrierte_art_wird_nie_ausgefuehrt():
    conn = _fresh()
    pid = proposals.record_proposal_created_event(
        conn, proposal_id=proposals.next_proposal_id(conn),
        proposal_type="ResourceProposal", claim_key="test", claim_value="x",
        source_belief=None, source_event=1,
        payload={"description": "t", "action_required": False, "review_recommended": True,
                 "umsetzung": {"art": "geld_ueberweisen", "betrag": 1000000}},
    )
    # pid ist die Event-Id; die Proposal-Id über die Liste holen
    prop = proposals.list_proposals(conn)[-1]
    proposals.review_proposal_governed(conn, int(prop["id"]), "accepted")
    ergebnis = umsetzung.umsetzen(conn, int(prop["id"]))
    assert ergebnis["umgesetzt"] is False
    assert "nicht registriert" in ergebnis["grund"]


def test_quelle_ist_ehrlich_genus_stufe1_nicht_ronny():
    from genus import sources

    conn = _fresh()
    ziele.seed_ziele(conn)
    pid = _luecken_proposal(conn)
    proposals.review_proposal_governed(conn, pid, "accepted")
    umsetzung.umsetzen(conn, pid)
    kanten = sources.relations(conn, subject="faehigkeit:weltfrage")
    assert kanten and all(k["source"] == umsetzung.STUFE1_SOURCE for k in kanten)


def test_rhythmus_proposals_bleiben_ohne_umsetzung():
    # der Default-Detector formt sein Proposal wie bisher -- kein umsetzung-Feld
    conn = _fresh()
    candidate = {
        "experience_key": "activity:test", "experience_type": "ActivityDailyRhythm",
        "subject_key": "system.activity", "experience_id": 1,
        "summary": "test", "proposal": None,
    }
    event_id = experience.record_experience_proposal(conn, candidate, 1)
    prop = proposals.list_proposals(conn)[-1]
    assert "umsetzung" not in json.loads(prop["payload"])
