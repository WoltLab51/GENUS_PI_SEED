import json

from click.testing import CliRunner

from genus import cli, event_router, governance, integrity, proposals, query, state
from tests.conftest import observe_activity_value, observe_cpu_value, observe_memory_value


def test_accept_blocked_under_elevated_pressure(conn):
    proposal_id = create_elevated_pressure_proposal(conn)

    verdict = proposals.review_proposal_governed(conn, proposal_id, "accepted")

    assert verdict["decision"] == governance.BLOCKED
    assert verdict["blocked_by"] == governance.POLICY_PRESSURE_GUARD
    assert not conn.execute(
        "SELECT 1 FROM event_log WHERE event_type = 'proposal_reviewed'"
    ).fetchone()
    proposal = proposals.get_proposal(conn, proposal_id)
    assert proposal["state"] == proposals.PENDING
    policy_event = event_payload(conn, "policy_evaluated")
    decision_event = event_payload(conn, "governance_decision")
    governance_row = conn.execute("SELECT * FROM governance_log").fetchone()
    assert policy_event["result"] == governance.POLICY_BLOCK
    assert decision_event["decision"] == governance.BLOCKED
    assert governance_row["decision"] == governance.BLOCKED
    assert governance_row["override"] == 0


def test_accept_with_override_allowed_and_documented(conn):
    proposal_id = create_elevated_pressure_proposal(conn)

    verdict = proposals.review_proposal_governed(
        conn,
        proposal_id,
        "accepted",
        "trotzdem ok",
        override=True,
    )

    assert verdict["decision"] == governance.ALLOWED
    assert verdict["override"] is True
    proposal = proposals.get_proposal(conn, proposal_id)
    assert proposal["state"] == proposals.ACCEPTED
    policy_event = event_payload(conn, "policy_evaluated")
    governance_row = conn.execute("SELECT * FROM governance_log").fetchone()
    assert policy_event["result"] == governance.POLICY_BLOCK
    assert governance_row["decision"] == governance.ALLOWED
    assert governance_row["override"] == 1


def test_reject_not_blocked_by_pressure_guard(conn):
    proposal_id = create_elevated_pressure_proposal(conn)

    verdict = proposals.review_proposal_governed(conn, proposal_id, "rejected")

    assert verdict["decision"] == governance.ALLOWED
    proposal = proposals.get_proposal(conn, proposal_id)
    assert proposal["state"] == proposals.REJECTED
    policy_event = event_payload(conn, "policy_evaluated")
    assert policy_event["result"] == governance.PASS


def test_accept_allowed_when_pressure_nominal(conn):
    proposal_id = create_elevated_pressure_proposal(conn)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)
    state.refresh(conn)

    verdict = proposals.review_proposal_governed(conn, proposal_id, "accepted")

    assert verdict["decision"] == governance.ALLOWED
    proposal = proposals.get_proposal(conn, proposal_id)
    assert proposal["state"] == proposals.ACCEPTED
    policy_event = event_payload(conn, "policy_evaluated")
    assert policy_event["result"] == governance.PASS


def test_kernel_violation_cannot_be_overridden(conn):
    proposal_id = create_elevated_pressure_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, "accepted", override=True)

    verdict = proposals.review_proposal_governed(
        conn,
        proposal_id,
        "rejected",
        override=True,
    )

    assert verdict["decision"] == governance.BLOCKED
    assert verdict["kernel"] is True
    assert verdict["blocked_by"] == governance.CONSTRAINT_TERMINAL_REVIEW
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'proposal_reviewed'"
    ).fetchone()["count"] == 1
    constraint_events = event_payloads(conn, "constraint_checked", decision_id=2)
    assert any(
        event["constraint_key"] == governance.CONSTRAINT_TERMINAL_REVIEW
        and event["result"] == governance.VIOLATION
        for event in constraint_events
    )
    governance_row = conn.execute(
        "SELECT * FROM governance_log WHERE id = ?",
        (2,),
    ).fetchone()
    assert governance_row["decision"] == governance.BLOCKED
    assert governance_row["override"] == 1


def test_invalid_decision_blocked_by_kernel(conn):
    proposal_id = create_elevated_pressure_proposal(conn)

    verdict = proposals.review_proposal_governed(
        conn,
        proposal_id,
        "maybe",
        override=True,
    )

    assert verdict["decision"] == governance.BLOCKED
    assert verdict["blocked_by"] == governance.CONSTRAINT_VALID_DECISION
    assert proposals.get_proposal(conn, proposal_id)["state"] == proposals.PENDING


def test_every_decision_is_event_backed(conn):
    proposal_id = create_elevated_pressure_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, "accepted")
    second_proposal = create_memory_proposal(conn)
    proposals.review_proposal_governed(conn, second_proposal, "rejected")

    rows = conn.execute("SELECT * FROM governance_log ORDER BY id").fetchall()

    assert len(rows) == 2
    for row in rows:
        events = event_payloads(conn, "governance_decision", decision_id=int(row["id"]))
        assert len(events) == 1
        assert events[0]["decision_id"] == row["id"]


def test_governance_events_written_in_order(conn):
    proposal_id = create_elevated_pressure_proposal(conn)

    verdict = proposals.review_proposal_governed(conn, proposal_id, "accepted")

    rows = conn.execute(
        """
        SELECT event_type, payload FROM event_log
        WHERE event_type IN (
            'constraint_checked',
            'policy_evaluated',
            'governance_decision'
        )
        ORDER BY id
        """
    ).fetchall()
    event_types = [
        row["event_type"]
        for row in rows
        if json.loads(row["payload"])["decision_id"] == verdict["decision_id"]
    ]
    assert event_types == [
        "constraint_checked",
        "constraint_checked",
        "policy_evaluated",
        "governance_decision",
    ]


def test_governance_replay_stable(conn):
    proposal_id = create_elevated_pressure_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, "accepted")
    proposals.review_proposal_governed(
        conn,
        proposal_id,
        "accepted",
        override=True,
    )
    memory_proposal = create_memory_proposal(conn)
    proposals.review_proposal_governed(conn, memory_proposal, "rejected")
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    after = integrity.snapshot_projections(conn)
    governance_events = conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'governance_decision'"
    ).fetchone()["count"]

    assert summary["governance_decisions"] == 3
    assert after == before
    assert governance_events == 3


def test_integrity_accepts_governance_events(conn):
    proposal_id = create_elevated_pressure_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, "accepted")

    result = integrity.check(conn)

    assert result["ok"] is True
    assert result["governance_decisions"] == 1


def test_governance_cli(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    create_elevated_pressure_proposal(conn)

    runner = CliRunner()
    blocked = runner.invoke(cli.main, ["proposals", "review", "1", "--accept"])
    listed = runner.invoke(cli.main, ["governance", "list"])
    filtered = runner.invoke(
        cli.main,
        ["governance", "list", "--target", "proposal:1"],
    )
    allowed = runner.invoke(
        cli.main,
        ["proposals", "review", "1", "--accept", "--override", "--note", "ok"],
    )
    why = runner.invoke(cli.main, ["why", "decision", "1"])

    assert blocked.exit_code != 0
    assert "[GOV] BLOCKED" in blocked.output
    assert listed.exit_code == 0
    assert "blocked" in listed.output
    assert filtered.exit_code == 0
    assert "proposal:1" in filtered.output
    assert allowed.exit_code == 0
    assert "(override)" in allowed.output
    assert why.exit_code == 0
    assert "policy_evaluated:" in why.output
    assert "constraint_checked:" in why.output


def test_query_status_counts_decisions(conn):
    proposal_id = create_elevated_pressure_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, "accepted")

    response = query.ask(conn, "status")
    governance_response = query.ask(conn, "governance")

    assert response["status"]["governance_decisions"] == 1
    assert governance_response["kind"] == "governance_decisions"
    assert governance_response["governance_decisions"][0]["decision"] == "blocked"


def create_elevated_pressure_proposal(conn) -> int:
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    state.refresh(conn)
    return conn.execute(
        "SELECT id FROM proposal_log ORDER BY id LIMIT 1"
    ).fetchone()["id"]


def create_memory_proposal(conn) -> int:
    for _ in range(3):
        observe_memory_value(conn, 91.0)
    rows = conn.execute("SELECT id FROM proposal_log ORDER BY id").fetchall()
    return rows[-1]["id"]


def event_payload(conn, event_type: str) -> dict:
    row = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = ? ORDER BY id LIMIT 1",
        (event_type,),
    ).fetchone()
    assert row is not None
    return json.loads(row["payload"])


def event_payloads(
    conn,
    event_type: str,
    decision_id: int | None = None,
) -> list[dict]:
    if decision_id is None:
        rows = conn.execute(
            "SELECT payload FROM event_log WHERE event_type = ? ORDER BY id",
            (event_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT payload FROM event_log
            WHERE event_type = ?
              AND json_extract(payload, '$.decision_id') = ?
            ORDER BY id
            """,
            (event_type, decision_id),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]
