from click.testing import CliRunner

from genus import cli, event_router, integrity, ledger, projection, query, state
from tests.conftest import observe_activity_value, observe_cpu_value


def test_state_refresh_records_elevated_pressure_from_active_high_beliefs(conn):
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    events = state.refresh(conn)

    assert [event["event_type"] for event in events] == ["state_changed"]
    row = conn.execute("SELECT * FROM state_projection").fetchone()
    assert row["state_key"] == state.STATE_KEY
    assert row["state_value"] == state.ELEVATED
    assert row["status"] == state.ACTIVE
    assert row["derivation"] == state.DERIVATION
    assert "supporting_beliefs" in row.keys()


def test_state_refresh_is_idempotent_without_vector_change(conn):
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    first = state.refresh(conn)
    before = integrity.snapshot_event_log(conn)

    second = state.refresh(conn)
    after = integrity.snapshot_event_log(conn)

    assert len(first) == 1
    assert second == []
    assert after == before


def test_state_changes_from_elevated_to_nominal(conn):
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    state.refresh(conn)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    events = state.refresh(conn)

    assert [event["event_type"] for event in events] == ["state_changed"]
    rows = conn.execute("SELECT * FROM state_projection ORDER BY id").fetchall()
    assert rows[0]["state_value"] == state.ELEVATED
    assert rows[0]["status"] == state.SUPERSEDED
    assert rows[0]["superseded_by"] == rows[1]["id"]
    assert rows[1]["state_value"] == state.NOMINAL
    assert rows[1]["status"] == state.ACTIVE


def test_state_replay_is_stable(conn):
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    state.refresh(conn)
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert summary["active_states"] == 1
    assert before == after


def test_integrity_accepts_state_changed(conn):
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    state.refresh(conn)

    result = integrity.check(conn)

    assert result["ok"] is True
    assert result["active_states"] == 1


def test_query_status_and_state_patterns(conn):
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    state.refresh(conn)

    status = query.ask(conn, "status")
    response = query.ask(conn, "zustand")

    assert status["status"]["active_states"] == 1
    assert response["kind"] == "states"
    assert response["states"][0]["state_value"] == state.ELEVATED


def test_explain_state_links_supporting_beliefs(conn):
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    state.refresh(conn)

    explanation = query.explain_state(conn, 1)

    assert explanation["state_event"]["event_type"] == "state_changed"
    assert len(explanation["supporting_beliefs"]) == 2
    assert {belief["claim_key"] for belief in explanation["supporting_beliefs"]} == {
        "system.activity",
        "system.load",
    }


def test_state_cli_refresh_show_and_explain(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    observe_activity_value(conn, 1.0)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    runner = CliRunner()
    refresh_result = runner.invoke(cli.main, ["state", "refresh"])
    show_result = runner.invoke(cli.main, ["state", "show"])
    explain_result = runner.invoke(cli.main, ["explain", "state", "1"])

    assert refresh_result.exit_code == 0
    assert "system.pressure=elevated" in refresh_result.output
    assert show_result.exit_code == 0
    assert "ACTIVE STATES" in show_result.output
    assert "elevated" in show_result.output
    assert explain_result.exit_code == 0
    assert "supporting_beliefs:" in explain_result.output


def test_contested_active_belief_does_not_support_derived_pressure_state(conn):
    observe_activity_value(conn, 0.0)
    support = ledger.append(
        conn, "evidence_recorded",
        {"metric_key": "system.load", "metric_value": 10.0, "source_observation": 1},
    )
    belief_id = projection.next_belief_id(conn)
    projection.apply_belief_created(conn, {
        "belief_id": belief_id, "claim_key": "system.load", "claim_value": "normal",
        "derivation": "test", "supporting_events": [support],
    })
    for i in (2, 3):
        counter = ledger.append(
            conn, "evidence_recorded",
            {"metric_key": "system.load", "metric_value": 99.0, "source_observation": i},
        )
        projection.apply_belief_weakened(
            conn, {"belief_id": belief_id, "contradicting_event": counter}
        )

    candidate = state.derive_pressure_state(conn)

    assert candidate["state_value"] == state.UNKNOWN
    assert "system.load" not in candidate["components"]
    assert candidate["components"]["excluded_contested_beliefs"] == [belief_id]
