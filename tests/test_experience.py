import json

from click.testing import CliRunner

from genus import cli, event_router, experience, integrity, projection, query


def test_experience_scan_records_activity_daily_rhythm(conn):
    supporting = [
        insert_activity_evidence(conn, 1.0, "2026-06-10T14:00:00.000Z"),
        insert_activity_evidence(conn, 1.0, "2026-06-10T14:05:00.000Z"),
        insert_activity_evidence(conn, 1.0, "2026-06-10T14:10:00.000Z"),
    ]
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:00:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:05:00.000Z")

    recorded = experience.scan(conn)

    assert len(recorded) == 1
    assert recorded[0]["supporting_events"] == supporting
    row = conn.execute("SELECT * FROM experience_log").fetchone()
    assert row["experience_key"] == "activity_daily_rhythm:system.activity:active"
    assert row["derivation"] == experience.DERIVATION
    assert json.loads(row["supporting_events"]) == supporting
    proposal = conn.execute("SELECT * FROM proposal_log").fetchone()
    assert proposal["proposal_type"] == experience.PROPOSAL_TYPE
    assert proposal["state"] == "pending"


def test_experience_scan_is_idempotent(conn):
    for minute in [0, 5, 10]:
        insert_activity_evidence(conn, 0.0, f"2026-06-10T23:{minute:02d}:00.000Z")
    insert_activity_evidence(conn, 1.0, "2026-06-10T12:00:00.000Z")
    insert_activity_evidence(conn, 1.0, "2026-06-10T12:05:00.000Z")
    first = experience.scan(conn)
    before_events = integrity.snapshot_event_log(conn)

    second = experience.scan(conn)
    after_events = integrity.snapshot_event_log(conn)

    assert len(first) == 1
    assert second == []
    assert after_events == before_events
    assert conn.execute("SELECT COUNT(*) AS count FROM experience_log").fetchone()[
        "count"
    ] == 1


def test_experience_replay_is_stable(conn):
    for minute in [0, 5, 10]:
        insert_activity_evidence(conn, 1.0, f"2026-06-10T09:{minute:02d}:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:00:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:05:00.000Z")
    experience.scan(conn)
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert summary["experiences"] == 1
    assert before == after


def test_integrity_accepts_experience_event(conn):
    for minute in [0, 5, 10]:
        insert_activity_evidence(conn, 1.0, f"2026-06-10T07:{minute:02d}:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:00:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:05:00.000Z")
    experience.scan(conn)

    result = integrity.check(conn)

    assert result["ok"] is True
    assert result["experiences"] == 1


def test_query_status_and_experience_patterns(conn):
    for minute in [0, 5, 10]:
        insert_activity_evidence(conn, 1.0, f"2026-06-10T12:{minute:02d}:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:00:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:05:00.000Z")
    experience.scan(conn)

    status = query.ask(conn, "status")
    patterns = query.ask(conn, "welche muster")

    assert status["status"]["experiences"] == 1
    assert patterns["kind"] == "experiences"
    assert patterns["experiences"][0]["experience_type"] == experience.EXPERIENCE_TYPE


def test_explain_experience_links_evidence_and_proposal(conn):
    supporting = [
        insert_activity_evidence(conn, 1.0, "2026-06-10T15:00:00.000Z"),
        insert_activity_evidence(conn, 1.0, "2026-06-10T15:05:00.000Z"),
        insert_activity_evidence(conn, 1.0, "2026-06-10T15:10:00.000Z"),
    ]
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:00:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:05:00.000Z")
    experience.scan(conn)

    explanation = query.explain_experience(conn, 1)

    assert explanation["experience_event"]["event_type"] == "experience_recorded"
    assert [event["id"] for event in explanation["supporting_evidence"]] == supporting
    assert explanation["proposals"][0]["proposal_type"] == experience.PROPOSAL_TYPE


def test_experience_cli_scan_show_and_explain(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for minute in [0, 5, 10]:
        insert_activity_evidence(conn, 1.0, f"2026-06-10T18:{minute:02d}:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:00:00.000Z")
    insert_activity_evidence(conn, 0.0, "2026-06-10T02:05:00.000Z")

    runner = CliRunner()
    scan_result = runner.invoke(cli.main, ["experience", "scan"])
    show_result = runner.invoke(cli.main, ["experience", "show"])
    explain_result = runner.invoke(cli.main, ["explain", "experience", "1"])

    assert scan_result.exit_code == 0
    assert "recorded 1 experience" in scan_result.output
    assert show_result.exit_code == 0
    assert "ActivityDailyRhythm" in show_result.output
    assert explain_result.exit_code == 0
    assert "supporting_evidence:" in explain_result.output
    assert "proposals:" in explain_result.output


def test_experience_scan_ignores_uniform_cron_sampling(conn):
    for hour in [8, 9, 10]:
        for minute in [0, 5, 10]:
            insert_activity_evidence(
                conn,
                1.0,
                f"2026-06-10T{hour:02d}:{minute:02d}:00.000Z",
            )

    recorded = experience.scan(conn)

    assert recorded == []
    assert conn.execute("SELECT COUNT(*) AS count FROM experience_log").fetchone()[
        "count"
    ] == 0


def test_experience_scan_caps_proposals_for_multiple_new_patterns(conn):
    for minute in [0, 5, 10]:
        insert_activity_evidence(conn, 1.0, f"2026-06-10T14:{minute:02d}:00.000Z")
        insert_activity_evidence(conn, 0.0, f"2026-06-10T02:{minute:02d}:00.000Z")

    recorded = experience.scan(conn)

    assert len(recorded) == 2
    assert conn.execute("SELECT COUNT(*) AS count FROM proposal_log").fetchone()[
        "count"
    ] == 1


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
    projection.apply_evidence_recorded(conn, {  # keep the indexed value view in sync
        "metric_key": experience.ACTIVITY_METRIC_KEY, "metric_value": value,
        "_event_id": evidence_id, "_event_created_at": created_at})
    conn.commit()
    return int(evidence_id)
