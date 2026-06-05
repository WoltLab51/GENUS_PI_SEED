import json

from genus import proposals
from tests.conftest import observe_cpu_value


def test_proposal_module_writes_event_and_projection(conn):
    source_event = 1

    event_id = proposals.record_resource_proposal_for_sustained_high(
        conn,
        trigger_belief_id=7,
        trigger_event_id=source_event,
    )

    event = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    proposal = conn.execute("SELECT * FROM proposal_log").fetchone()
    event_payload = json.loads(event["payload"])

    assert event["event_type"] == "proposal_created"
    assert event_payload["proposal_id"] == proposal["id"]
    assert event_payload["proposal_type"] == "ResourceProposal"
    assert proposal["source_belief"] == 7
    assert proposal["source_event"] == source_event


def test_belief_confirmed_does_not_create_proposal_event(conn):
    for _ in range(4):
        observe_cpu_value(conn, 92.0)

    proposal_events = conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'proposal_created'"
    ).fetchone()["count"]
    confirmed_events = conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'belief_confirmed'"
    ).fetchone()["count"]

    assert confirmed_events == 1
    assert proposal_events == 1


def test_generated_events_have_required_contract_keys(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    required = {
        "observation_created": {"source", "raw_value", "unit"},
        "evidence_recorded": {"observation_id", "metric_key", "metric_value"},
        "belief_created": {
            "belief_id",
            "claim_key",
            "claim_value",
            "derivation",
            "supporting_events",
        },
        "belief_weakened": {"belief_id", "contradicting_event"},
        "belief_superseded": {
            "old_belief_id",
            "new_belief_id",
            "claim_key",
            "claim_value",
            "derivation",
            "supporting_events",
            "reason",
        },
        "contradiction_detected": {"belief_id", "reason"},
        "proposal_created": {
            "proposal_id",
            "proposal_type",
            "claim_key",
            "claim_value",
            "source_belief",
            "source_event",
            "payload",
            "reason",
        },
    }
    rows = conn.execute("SELECT event_type, payload FROM event_log").fetchall()

    for row in rows:
        payload = json.loads(row["payload"])
        assert required[row["event_type"]].issubset(payload)
