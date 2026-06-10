import json

import pytest
from click.testing import CliRunner

from genus import cli, event_router, inquiries, integrity, proposals, query
from tests.conftest import observe_cpu_value


def test_review_accept_changes_state(conn):
    proposal_id = create_high_proposal(conn)

    event_id = proposals.record_proposal_reviewed_event(
        conn, proposal_id, "accepted", "makes sense"
    )

    row = conn.execute("SELECT * FROM proposal_log WHERE id = ?", (proposal_id,)).fetchone()
    event = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    payload = json.loads(event["payload"])

    assert row["state"] == "accepted"
    assert row["decision"] == "accepted"
    assert row["reviewed_at"]
    assert event["event_type"] == "proposal_reviewed"
    assert {"proposal_id", "decision", "note"}.issubset(payload)
    assert payload["note"] == "makes sense"


def test_review_reject_changes_state(conn):
    proposal_id = create_high_proposal(conn)

    proposals.record_proposal_reviewed_event(conn, proposal_id, "rejected", "not useful")

    row = conn.execute("SELECT * FROM proposal_log WHERE id = ?", (proposal_id,)).fetchone()

    assert row["state"] == "rejected"
    assert row["decision"] == "rejected"
    assert row["reviewed_at"]


def test_review_twice_raises(conn):
    proposal_id = create_high_proposal(conn)
    proposals.record_proposal_reviewed_event(conn, proposal_id, "accepted")

    with pytest.raises(ValueError, match="already reviewed"):
        proposals.record_proposal_reviewed_event(conn, proposal_id, "rejected")


def test_review_unknown_proposal_raises(conn):
    with pytest.raises(ValueError, match="proposal not found"):
        proposals.record_proposal_reviewed_event(conn, 999, "accepted")


def test_review_invalid_decision_raises(conn):
    proposal_id = create_high_proposal(conn)

    with pytest.raises(ValueError, match="decision"):
        proposals.record_proposal_reviewed_event(conn, proposal_id, "maybe")


def test_resolve_inquiry_sets_answer_and_timestamp(conn):
    create_contradiction_cycle(conn)
    inquiry_id = conn.execute("SELECT id FROM inquiry_log").fetchone()["id"]

    event_id = inquiries.record_inquiry_resolved_event(conn, inquiry_id, "Backup lief")

    row = conn.execute("SELECT * FROM inquiry_log WHERE id = ?", (inquiry_id,)).fetchone()
    event = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    payload = json.loads(event["payload"])

    assert row["state"] == "resolved"
    assert row["answer"] == "Backup lief"
    assert row["resolved_at"]
    assert event["event_type"] == "inquiry_resolved"
    assert {"inquiry_id", "answer"}.issubset(payload)


def test_resolve_twice_raises(conn):
    create_contradiction_cycle(conn)
    inquiry_id = conn.execute("SELECT id FROM inquiry_log").fetchone()["id"]
    inquiries.record_inquiry_resolved_event(conn, inquiry_id, "Backup lief")

    with pytest.raises(ValueError, match="already resolved"):
        inquiries.record_inquiry_resolved_event(conn, inquiry_id, "doch anders")


def test_lifecycle_replay_stable(conn):
    create_contradiction_cycle(conn)
    proposal_ids = [
        row["id"] for row in conn.execute("SELECT id FROM proposal_log ORDER BY id").fetchall()
    ]
    inquiry_id = conn.execute("SELECT id FROM inquiry_log").fetchone()["id"]
    proposals.record_proposal_reviewed_event(conn, proposal_ids[0], "accepted", "ok")
    proposals.record_proposal_reviewed_event(conn, proposal_ids[1], "rejected", "no action")
    inquiries.record_inquiry_resolved_event(conn, inquiry_id, "Backup lief")
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert summary["proposals"] == 2
    assert summary["inquiries"] == 1
    assert after == before


def test_integrity_accepts_lifecycle_events(conn):
    create_contradiction_cycle(conn)
    proposal_id = conn.execute("SELECT id FROM proposal_log ORDER BY id").fetchone()["id"]
    inquiry_id = conn.execute("SELECT id FROM inquiry_log").fetchone()["id"]
    proposals.record_proposal_reviewed_event(conn, proposal_id, "accepted")
    inquiries.record_inquiry_resolved_event(conn, inquiry_id, "Backup lief")

    result = integrity.check(conn)

    assert result["ok"] is True
    assert result["issues"] == []


def test_accepted_proposal_executes_nothing(conn):
    proposal_id = create_high_proposal(conn)
    before_events = integrity.snapshot_event_log(conn)
    before_beliefs = integrity.snapshot_projections(conn)["beliefs"]
    before_inquiries = integrity.snapshot_projections(conn)["inquiries"]

    proposals.record_proposal_reviewed_event(conn, proposal_id, "accepted")

    after_events = integrity.snapshot_event_log(conn)
    after_snapshot = integrity.snapshot_projections(conn)
    new_events = after_events[len(before_events) :]

    assert [event["event_type"] for event in new_events] == ["proposal_reviewed"]
    assert after_snapshot["beliefs"] == before_beliefs
    assert after_snapshot["inquiries"] == before_inquiries


def test_review_cli_commands(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    create_contradiction_cycle(conn)

    runner = CliRunner()
    accept = runner.invoke(cli.main, ["proposals", "review", "1", "--accept"])
    reject_again = runner.invoke(cli.main, ["proposals", "review", "1", "--reject"])
    missing_flag = runner.invoke(cli.main, ["proposals", "review", "2"])
    resolve = runner.invoke(
        cli.main,
        ["inquiries", "resolve", "1", "--answer", "Backup lief"],
    )

    assert accept.exit_code == 0
    assert "[GOV] proposal 1 accepted" in accept.output
    assert reject_again.exit_code != 0
    assert missing_flag.exit_code != 0
    assert resolve.exit_code == 0
    assert "[GOV] inquiry 1 resolved" in resolve.output


def test_pending_list_shrinks_after_review(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    proposal_id = create_high_proposal(conn)
    proposals.record_proposal_reviewed_event(conn, proposal_id, "accepted")

    runner = CliRunner()
    pending = runner.invoke(cli.main, ["proposals", "list"])
    all_rows = runner.invoke(cli.main, ["proposals", "list", "--all"])

    assert pending.exit_code == 0
    assert "ResourceProposal" not in pending.output
    assert all_rows.exit_code == 0
    assert "accepted" in all_rows.output


def test_query_why_proposal_shows_review_step(conn):
    proposal_id = create_high_proposal(conn)
    proposals.record_proposal_reviewed_event(conn, proposal_id, "accepted", "yep")

    explanation = query.explain_proposal(conn, proposal_id)

    assert explanation["review_event"]["event_type"] == "proposal_reviewed"
    assert explanation["review_event"]["payload"]["decision"] == "accepted"
    assert explanation["review_event"]["payload"]["note"] == "yep"


def create_high_proposal(conn) -> int:
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    return conn.execute("SELECT id FROM proposal_log ORDER BY id").fetchone()["id"]


def create_contradiction_cycle(conn) -> None:
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)
