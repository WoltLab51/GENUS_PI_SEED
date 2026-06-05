import pytest

from genus import ledger, reactors
from genus.sensor import mock_cpu
from tests.conftest import observe_cpu_value


def test_observe_cpu_reading_records_observation_then_evidence(conn):
    result = reactors.observe_cpu_reading(conn, mock_cpu(42.0))

    rows = conn.execute("SELECT event_type FROM event_log ORDER BY id").fetchall()

    assert result["observation_id"] == 1
    assert [row["event_type"] for row in rows] == [
        "observation_created",
        "evidence_recorded",
    ]


def test_process_observation_rejects_non_observation_event(conn):
    event_id = ledger.append(conn, "evidence_recorded", {"metric_key": "x"})

    with pytest.raises(ValueError, match="observation_created"):
        reactors.process_observation(conn, event_id)


def test_reactor_preserves_belief_and_proposal_behavior(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    belief = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.load' AND claim_value = 'high'
        """
    ).fetchone()
    proposals = conn.execute("SELECT COUNT(*) AS count FROM proposal_log").fetchone()

    assert belief["state"] == "active"
    assert proposals["count"] == 1
