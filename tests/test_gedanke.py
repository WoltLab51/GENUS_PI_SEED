"""Der proaktive GEDANKE (genus/gedanke.py, Ronny 2026-07-08): das WICHTIGE -- Entscheidungs-
Vorschlaege + selbst gebildete Begriffs-Fragen -- wird SOFORT eine bestaetigte Nachricht-Hand,
statt bis zum naechsten Morgen aufgestaut zu werden. Idempotent, gedeckelt, nur das Wichtige."""
import sqlite3

from genus import gedanke, hand, inquiries, proposals
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _action_proposal(conn, desc="Darf ich die Luecke beim Blatt weltfrage angehen?"):
    proposals.record_proposal_created_event(
        conn, proposal_id=proposals.next_proposal_id(conn),
        proposal_type="ExperienceProposal", claim_key="verstehen.x", claim_value="luecke",
        source_belief=None, source_event=1,
        payload={"description": desc, "action_required": True, "review_recommended": True})
    conn.commit()   # in Produktion laeuft push auf einer FRISCHEN Verbindung (eigener Cron), nicht mitten in einer Txn


def test_push_macht_wichtigen_vorschlag_zu_bestaetigter_hand():
    conn = _fresh()
    _action_proposal(conn)
    neu = gedanke.push(conn)
    assert len(neu) == 1
    offen = hand.offene(conn)
    assert len(offen) == 1
    h = offen[0]
    assert h["status"] == hand.FREIGEGEBEN
    assert "klären" in h["inhalt"] and h["quelle"].startswith("gedanke:proposal:")
    assert h["faellig_um"] is None   # sofort faellig -> der Cron sendet gleich (nicht erst morgen)


def test_push_ist_idempotent():
    conn = _fresh()
    _action_proposal(conn)
    gedanke.push(conn)
    assert gedanke.push(conn) == []          # derselbe Gedanke wird nur EINMAL zur Hand
    assert len(hand.offene(conn)) == 1


def test_push_ignoriert_betriebs_rauschen():
    # ein action_required=False Vorschlag (Monitoring) ist KEIN proaktiver Gedanke -> nur das Wichtige
    conn = _fresh()
    proposals.record_proposal_created_event(
        conn, proposal_id=proposals.next_proposal_id(conn),
        proposal_type="OperationProposal", claim_key="system.load", claim_value="hoch",
        source_belief=None, source_event=1,
        payload={"description": "Last war hoch", "action_required": False, "review_recommended": True})
    conn.commit()
    assert gedanke.push(conn) == []


def test_push_schickt_selbst_gebildete_begriffs_frage():
    conn = _fresh()
    inquiries.record_inquiry_created_event(
        conn, inquiry_id=inquiries.next_inquiry_id(conn),
        inquiry_type=inquiries.ABSTRAKTION_INQUIRY_TYPE, claim_key="konzept:auto:x|wachstum",
        source_belief=None, source_event=1, question_key=inquiries.ABSTRAKTION_QUESTION,
        payload={"art": "wachstum", "elternteil": "geraet", "kandidaten": ["mixer"]})
    conn.commit()
    neu = gedanke.push(conn)
    assert len(neu) == 1 and "Begriff" in hand.offene(conn)[0]["inhalt"]
