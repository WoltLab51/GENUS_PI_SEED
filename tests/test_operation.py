import json

from click.testing import CliRunner

from genus import cli, event_router, governance, integrity, operation, proposals, query


def test_network_check_creates_healthy_belief(conn):
    result = operation.record_network_check(
        conn,
        status=operation.STATUS_OK,
        target="192.168.178.1",
        detail="gateway reachable",
    )

    belief = conn.execute("SELECT * FROM belief_projection").fetchone()
    operations = operation.list_operations(conn)

    assert result["check_event_id"] == 1
    assert belief["claim_key"] == operation.CLAIM_NETWORK
    assert belief["claim_value"] == operation.HEALTHY
    assert belief["derivation"] == operation.DERIVATION_CHECK
    assert operations[0]["check_key"] == operation.CHECK_NETWORK_GATEWAY
    assert operations[0]["status"] == operation.STATUS_OK
    assert conn.execute("SELECT COUNT(*) AS count FROM proposal_log").fetchone()["count"] == 0


def test_network_failure_supersedes_and_creates_one_proposal(conn):
    operation.record_network_check(conn, operation.STATUS_OK, "192.168.178.1")
    first_failure = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=1,
    )
    second_failure = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=2,
    )

    active = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = ? AND state = 'active'",
        (operation.CLAIM_NETWORK,),
    ).fetchone()
    proposal_rows = proposals.list_proposals(conn)

    assert first_failure["belief"]["event_type"] == "belief_superseded"
    assert second_failure["belief"]["event_type"] == "belief_confirmed"
    assert active["claim_value"] == operation.UNSTABLE
    assert len(proposal_rows) == 1
    assert proposal_rows[0]["proposal_type"] == operation.PROPOSAL_TYPE


def test_recovery_restart_is_governed_and_replay_stable(conn):
    result = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=1,
        action=operation.ACTION_RESTART_NETWORK,
    )
    recovery = result["recovery"]
    assert recovery["verdict"]["decision"] == governance.ALLOWED

    operation.record_recovery_result(
        conn,
        recovery_id=recovery["recovery_id"],
        result=operation.RECOVERY_SUCCEEDED,
        detail="restarted NetworkManager",
    )
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert summary["operations"] == 2
    assert after == before
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = ?",
        (operation.RECOVERY_ATTEMPT_EVENT,),
    ).fetchone()["count"] == 1


def test_reboot_recovery_blocked_until_failure_threshold(conn):
    blocked = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=1,
        action=operation.ACTION_REBOOT,
    )
    allowed = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=3,
        action=operation.ACTION_REBOOT,
    )

    assert blocked["recovery"]["verdict"]["decision"] == governance.BLOCKED
    assert blocked["recovery"]["attempt_event_id"] is None
    assert allowed["recovery"]["verdict"]["decision"] == governance.ALLOWED
    assert allowed["recovery"]["attempt_event_id"] is not None
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = ?",
        (operation.RECOVERY_ATTEMPT_EVENT,),
    ).fetchone()["count"] == 1


def test_reboot_recovery_is_rate_limited_by_governance(conn):
    first = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=3,
        action=operation.ACTION_REBOOT,
    )
    second = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=4,
        action=operation.ACTION_REBOOT,
    )

    assert first["recovery"]["verdict"]["decision"] == governance.ALLOWED
    assert second["recovery"]["verdict"]["decision"] == governance.BLOCKED
    assert second["recovery"]["verdict"]["blocked_by"] == governance.POLICY_REBOOT_COOLDOWN
    assert second["recovery"]["attempt_event_id"] is None
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = ?",
        (operation.RECOVERY_ATTEMPT_EVENT,),
    ).fetchone()["count"] == 1


def test_recovery_action_requires_failed_check(conn):
    try:
        operation.record_network_check(
            conn,
            operation.STATUS_OK,
            "192.168.178.1",
            action=operation.ACTION_RESTART_NETWORK,
        )
    except ValueError as exc:
        assert "failed check" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_integrity_accepts_operation_events(conn):
    result = operation.record_network_check(
        conn,
        operation.STATUS_FAIL,
        "192.168.178.1",
        failures=1,
        action=operation.ACTION_RESTART_NETWORK,
    )
    operation.record_recovery_result(
        conn,
        result["recovery"]["recovery_id"],
        operation.RECOVERY_FAILED,
        "restart failed",
    )

    checked = integrity.check(conn)

    assert checked["ok"] is True
    assert checked["operations"] == 2


def test_operation_query_and_cli(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)

    result = CliRunner().invoke(
        cli.main,
        [
            "operation",
            "network-check",
            "--status",
            "ok",
            "--target",
            "192.168.178.1",
            "--json",
        ],
    )
    payload = json.loads(result.output)
    response = query.ask(conn, "betrieb")

    assert result.exit_code == 0
    assert payload["belief"]["claim_value"] == operation.HEALTHY
    assert response["kind"] == "operations"
    assert response["operations"][0]["status"] == operation.STATUS_OK
