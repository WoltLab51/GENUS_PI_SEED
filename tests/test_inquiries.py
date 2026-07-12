from click.testing import CliRunner

from genus import cli, event_router, inquiries, reactors
from tests.conftest import observe_cpu_value


def test_contradiction_creates_inquiry(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    row = conn.execute("SELECT * FROM inquiry_log").fetchone()

    assert row["inquiry_type"] == "CauseInquiry"
    assert row["claim_key"] == "system.load"
    assert row["question_key"] == "cause.changed_state"
    assert row["state"] == "open"


def test_first_high_does_not_create_inquiry(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    count = conn.execute("SELECT COUNT(*) AS count FROM inquiry_log").fetchone()["count"]

    assert count == 0


def test_inquiry_log_rebuilds_on_replay(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    before = [dict(row) for row in conn.execute("SELECT * FROM inquiry_log").fetchall()]
    summary = event_router.replay(conn)
    after = [dict(row) for row in conn.execute("SELECT * FROM inquiry_log").fetchall()]

    assert summary["inquiries"] == 1
    assert after == before


def test_inquiries_list_shows_open_inquiries(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    result = CliRunner().invoke(cli.main, ["inquiries", "list"])

    assert result.exit_code == 0
    assert "CauseInquiry" in result.output
    assert "cause.changed_state" in result.output


def test_reconcile_resolves_only_false_acyclicity_alarms_in_one_replayable_event(conn):
    # A symmetric/associative relation may form rings; transitivity evidence alone must
    # never turn that into a hierarchy invariant. This reproduces the live `verwandt`
    # flood without requiring thousands of graph rows.
    reactors.observe_relation(conn, "A", "verwandt", "B", "test")
    reactors.observe_relation(conn, "B", "is_a", "A", "test")
    event_id = conn.execute("SELECT MAX(id) AS id FROM event_log").fetchone()["id"]
    false_id = inquiries.next_inquiry_id(conn)
    inquiries.record_inquiry_created_event(
        conn,
        inquiry_id=false_id,
        inquiry_type=inquiries.SOURCE_CONTRADICTION_TYPE,
        claim_key="B|verwandt|A|acyclic",
        source_belief=None,
        source_event=event_id,
        question_key=inquiries.SOURCE_CONTRADICTION_QUESTION,
        payload={"subject": "B", "predicate": "verwandt", "object": "A",
                 "kind": "acyclicity_violation", "review_recommended": True},
    )
    true_id = inquiries.next_inquiry_id(conn)
    inquiries.record_inquiry_created_event(
        conn,
        inquiry_id=true_id,
        inquiry_type=inquiries.SOURCE_CONTRADICTION_TYPE,
        claim_key="B|is_a|A|acyclic",
        source_belief=None,
        source_event=event_id,
        question_key=inquiries.SOURCE_CONTRADICTION_QUESTION,
        payload={"subject": "B", "predicate": "is_a", "object": "A",
                 "kind": "acyclicity_violation", "review_recommended": True},
    )

    report = inquiries.reconcile(conn)

    assert report["resolved"] == [false_id]
    assert inquiries.get_inquiry(conn, false_id)["state"] == inquiries.RESOLVED
    assert inquiries.get_inquiry(conn, true_id)["state"] == inquiries.OPEN
    bulk = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'inquiries_reconciled'"
    ).fetchone()
    assert bulk is not None

    before = [dict(row) for row in conn.execute("SELECT * FROM inquiry_log ORDER BY id")]
    event_router.replay(conn)
    after = [dict(row) for row in conn.execute("SELECT * FROM inquiry_log ORDER BY id")]
    assert after == before

    repaired = inquiries.reconcile(conn, repair_cycles=True)
    assert repaired["repaired_cycles"] == 1
    assert inquiries.get_inquiry(conn, true_id)["state"] == inquiries.RESOLVED
    assert conn.execute(
        "SELECT 1 FROM relation_projection WHERE subject='B' AND predicate='is_a' AND object='A'"
    ).fetchone() is None


def test_reconcile_collapses_duplicate_open_stability_questions(conn):
    for source_event in (1, 2, 3):
        inquiries.record_inquiry_created_event(
            conn,
            inquiry_id=inquiries.next_inquiry_id(conn),
            inquiry_type="StabilityInquiry",
            claim_key="system.network",
            source_belief=None,
            source_event=source_event,
            question_key="stability.unexpected_flip",
            payload={"observed": "flipped"},
        )

    report = inquiries.reconcile(conn)
    rows = conn.execute(
        "SELECT id, state FROM inquiry_log WHERE claim_key = ? ORDER BY id",
        ("system.network",),
    ).fetchall()

    assert len(report["resolved"]) == 2
    assert [row["state"] for row in rows] == ["resolved", "resolved", "open"]
