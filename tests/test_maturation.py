import json

from click.testing import CliRunner

from genus import (
    cli,
    event_router,
    experience,
    governance,
    inquiries,
    integrity,
    maturation,
    proposals,
    query,
    rules,
)


def test_scan_proposes_rule_from_experience(conn):
    source_experience = create_activity_experience(conn)

    recorded = maturation.scan(conn)

    assert len(recorded) == 1
    candidate = recorded[0]
    assert candidate["rule_key"] == "activity_expectation:system.activity:14:active"
    assert candidate["spec"] == {"hour_utc": 14, "expected_value": "active"}
    assert candidate["source_experience"] == source_experience
    rule_event = event_payload(conn, "rule_proposed")
    assert rule_event["rule_key"] == candidate["rule_key"]
    proposal = rule_proposal(conn)
    assert proposal["proposal_type"] == maturation.PROPOSAL_TYPE
    assert proposal["state"] == proposals.PENDING
    assert proposal["source_event"] == candidate["rule_event_id"]
    payload = json.loads(proposal["payload"])
    assert payload["spec"] == candidate["spec"]


def test_scan_is_idempotent(conn):
    create_activity_experience(conn)
    first = maturation.scan(conn)
    before = integrity.snapshot_event_log(conn)

    second = maturation.scan(conn)
    after = integrity.snapshot_event_log(conn)

    assert len(first) == 1
    assert second == []
    assert after == before


def test_activate_requires_accepted_proposal(conn):
    proposal_id = create_rule_proposal(conn)

    verdict = maturation.activate_rule(conn, proposal_id, override=True)

    assert verdict["decision"] == governance.BLOCKED
    assert verdict["blocked_by"] == governance.CONSTRAINT_RULE_SOURCE_ACCEPTED
    assert not conn.execute(
        "SELECT 1 FROM event_log WHERE event_type = 'rule_activated'"
    ).fetchone()
    assert conn.execute("SELECT COUNT(*) AS count FROM rule_projection").fetchone()[
        "count"
    ] == 0
    decision = event_payload(conn, "governance_decision")
    assert decision["action"] == governance.ACTION_RULE_ACTIVATE
    assert decision["decision"] == governance.BLOCKED


def test_activate_after_accept_creates_active_rule(conn):
    proposal_id = create_rule_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, proposals.ACCEPTED)

    verdict = maturation.activate_rule(conn, proposal_id)

    assert verdict["decision"] == governance.ALLOWED
    row = conn.execute("SELECT * FROM rule_projection").fetchone()
    assert row["rule_key"] == "activity_expectation:system.activity:14:active"
    assert row["status"] == maturation.ACTIVE
    assert json.loads(row["spec"]) == {"hour_utc": 14, "expected_value": "active"}
    activation_event = event_payload(conn, "rule_activated")
    assert activation_event["source_proposal"] == proposal_id
    decision = event_payloads(conn, "governance_decision")[-1]
    assert decision["action"] == governance.ACTION_RULE_ACTIVATE
    assert decision["decision"] == governance.ALLOWED


def test_activation_is_terminal(conn):
    proposal_id = create_accepted_active_rule(conn)

    verdict = maturation.activate_rule(conn, proposal_id, override=True)

    assert verdict["decision"] == governance.BLOCKED
    assert verdict["blocked_by"] == governance.CONSTRAINT_RULE_SINGLE_ACTIVATION
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'rule_activated'"
    ).fetchone()["count"] == 1


def test_accept_alone_activates_nothing(conn):
    proposal_id = create_rule_proposal(conn)

    proposals.review_proposal_governed(conn, proposal_id, proposals.ACCEPTED)

    assert conn.execute("SELECT COUNT(*) AS count FROM rule_projection").fetchone()[
        "count"
    ] == 0
    assert not conn.execute(
        "SELECT 1 FROM event_log WHERE event_type = 'rule_activated'"
    ).fetchone()


def test_active_rule_fires_inquiry_on_deviation(conn):
    create_accepted_active_rule(conn)
    evidence_id = insert_activity_evidence(conn, 0.0, "2026-06-10T14:20:00.000Z")

    written = rules.apply_activity_rule(conn)

    assert "inquiry_created" in written
    row = conn.execute("SELECT * FROM inquiry_log").fetchone()
    assert row["inquiry_type"] == "ExpectationInquiry"
    assert row["question_key"] == "expectation.deviation"
    assert row["source_event"] == evidence_id
    payload = json.loads(row["payload"])
    assert payload["rule_key"] == "activity_expectation:system.activity:14:active"
    assert payload["expected"] == "active"
    assert payload["observed"] == "idle"


def test_active_rule_silent_when_expectation_met(conn):
    create_accepted_active_rule(conn)
    insert_activity_evidence(conn, 1.0, "2026-06-10T14:20:00.000Z")

    written = rules.apply_activity_rule(conn)

    assert "inquiry_created" not in written
    assert conn.execute("SELECT COUNT(*) AS count FROM inquiry_log").fetchone()[
        "count"
    ] == 0


def test_no_effect_before_activation(conn):
    proposal_id = create_rule_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, proposals.ACCEPTED)
    insert_activity_evidence(conn, 0.0, "2026-06-10T14:20:00.000Z")

    written = rules.apply_activity_rule(conn)

    assert "inquiry_created" not in written
    assert conn.execute("SELECT COUNT(*) AS count FROM inquiry_log").fetchone()[
        "count"
    ] == 0


def test_maturation_replay_stable(conn):
    create_accepted_active_rule(conn)
    insert_activity_evidence(conn, 0.0, "2026-06-10T14:20:00.000Z")
    rules.apply_activity_rule(conn)
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert summary["active_rules"] == 1
    assert before == after
    assert conn.execute("SELECT COUNT(*) AS count FROM inquiry_log").fetchone()[
        "count"
    ] == 1


def test_integrity_accepts_maturation_events(conn):
    create_accepted_active_rule(conn)

    result = integrity.check(conn)

    assert result["ok"] is True
    assert result["active_rules"] == 1


def test_full_metabolism_end_to_end(conn):
    create_activity_experience(conn)
    proposed = maturation.scan(conn)
    proposal_id = proposed[0]["proposal_id"]
    proposals.review_proposal_governed(conn, proposal_id, proposals.ACCEPTED)
    maturation.activate_rule(conn, proposal_id)
    insert_activity_evidence(conn, 0.0, "2026-06-10T14:20:00.000Z")
    rules.apply_activity_rule(conn)
    inquiry_id = conn.execute("SELECT id FROM inquiry_log").fetchone()["id"]
    inquiries.record_inquiry_resolved_event(conn, inquiry_id, "War ein Sonderfall.")
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    result = integrity.check(conn)

    assert summary["active_rules"] == 1
    assert integrity.snapshot_projections(conn) == before
    assert result["ok"] is True
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'inquiry_resolved'"
    ).fetchone()["count"] == 1


def test_maturation_cli(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    create_activity_experience(conn)

    runner = CliRunner()
    scan = runner.invoke(cli.main, ["maturation", "scan"])
    proposal_id = rule_proposal(conn)["id"]
    blocked = runner.invoke(cli.main, ["rules", "activate", str(proposal_id)])
    reviewed = runner.invoke(
        cli.main,
        ["proposals", "review", str(proposal_id), "--accept"],
    )
    activated = runner.invoke(cli.main, ["rules", "activate", str(proposal_id)])
    listed = runner.invoke(cli.main, ["rules", "list"])
    explained = runner.invoke(cli.main, ["explain", "rule", "1"])

    assert scan.exit_code == 0
    assert "proposed 1 rule" in scan.output
    assert blocked.exit_code != 0
    assert "kernel:rule_source_accepted_v1" in blocked.output
    assert reviewed.exit_code == 0
    assert activated.exit_code == 0
    assert "activated" in activated.output
    assert listed.exit_code == 0
    assert "activity_expectation_v1" in listed.output
    assert explained.exit_code == 0
    assert "source_experience:" in explained.output


def test_query_status_counts_active_rules(conn):
    create_accepted_active_rule(conn)

    status = query.ask(conn, "status")
    rules_response = query.ask(conn, "regeln")

    assert status["status"]["active_rules"] == 1
    assert rules_response["kind"] == "rules"
    assert rules_response["rules"][0]["rule_type"] == maturation.RULE_TYPE


def create_activity_experience(conn, hour: int = 14) -> int:
    for minute in [0, 5, 10]:
        insert_activity_evidence(conn, 1.0, f"2026-06-10T{hour:02d}:{minute:02d}:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:00:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:05:00.000Z")
    recorded = experience.scan(conn)
    assert len(recorded) == 1
    return recorded[0]["experience_id"]


def create_rule_proposal(conn) -> int:
    create_activity_experience(conn)
    recorded = maturation.scan(conn)
    assert len(recorded) == 1
    return recorded[0]["proposal_id"]


def create_accepted_active_rule(conn) -> int:
    proposal_id = create_rule_proposal(conn)
    proposals.review_proposal_governed(conn, proposal_id, proposals.ACCEPTED)
    verdict = maturation.activate_rule(conn, proposal_id)
    assert verdict["decision"] == governance.ALLOWED
    return proposal_id


def rule_proposal(conn):
    row = conn.execute(
        """
        SELECT * FROM proposal_log
        WHERE proposal_type = ?
        ORDER BY id
        LIMIT 1
        """,
        (maturation.PROPOSAL_TYPE,),
    ).fetchone()
    assert row is not None
    return row


def event_payload(conn, event_type: str) -> dict:
    rows = event_payloads(conn, event_type)
    assert rows
    return rows[0]


def event_payloads(conn, event_type: str) -> list[dict]:
    rows = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = ? ORDER BY id",
        (event_type,),
    ).fetchall()
    return [json.loads(row["payload"]) for row in rows]


def insert_activity_evidence(conn, value: float, created_at: str) -> int:
    observation_payload = json.dumps(
        {
            "source": "mock",
            "raw_value": value,
            "unit": "binary",
            "metric_key": experience.ACTIVITY_METRIC_KEY,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    observation_id = conn.execute(
        """
        INSERT INTO event_log (event_type, payload, created_at)
        VALUES (?, ?, ?)
        """,
        ("observation_created", observation_payload, created_at),
    ).lastrowid
    evidence_payload = json.dumps(
        {
            "observation_id": observation_id,
            "metric_key": experience.ACTIVITY_METRIC_KEY,
            "metric_value": value,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    evidence_id = conn.execute(
        """
        INSERT INTO event_log (event_type, payload, created_at)
        VALUES (?, ?, ?)
        """,
        ("evidence_recorded", evidence_payload, created_at),
    ).lastrowid
    conn.commit()
    return int(evidence_id)
