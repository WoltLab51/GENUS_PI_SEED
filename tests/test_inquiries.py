from click.testing import CliRunner

from genus import cli, event_router
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
