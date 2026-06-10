from click.testing import CliRunner

from genus import cli, integrity, query
from tests.conftest import observe_cpu_value


def test_ask_active_beliefs_returns_current_state(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    response = query.ask(conn, "was glaubst du")

    assert response["kind"] == "active_beliefs"
    assert response["beliefs"][0]["claim_key"] == "system.load"
    assert response["beliefs"][0]["claim_value"] == "high"


def test_ask_status_returns_projection_counts(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    response = query.ask(conn, "status")

    assert response["kind"] == "status"
    assert response["status"]["events"] == 8
    assert response["status"]["active_beliefs"] == 1
    assert response["status"]["pending_proposals"] == 1


def test_unknown_ask_returns_supported_patterns(conn):
    response = query.ask(conn, "sing mir ein lied")

    assert response["kind"] == "unknown"
    assert response["supported"]


def test_explain_belief_includes_evidence_and_observations(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    belief = conn.execute("SELECT * FROM belief_projection").fetchone()

    explanation = query.explain_belief(conn, int(belief["id"]))

    assert explanation["belief"]["claim_key"] == "system.load"
    assert explanation["created_by"]["event_type"] == "belief_created"
    assert len(explanation["supporting_evidence"]) == 3
    assert all("observation" in event for event in explanation["supporting_evidence"])


def test_why_proposal_links_event_belief_and_evidence(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    proposal = conn.execute("SELECT * FROM proposal_log").fetchone()

    explanation = query.explain_proposal(conn, int(proposal["id"]))

    assert explanation["proposal"]["proposal_type"] == "ResourceProposal"
    assert explanation["proposal_event"]["event_type"] == "proposal_created"
    assert explanation["source_event"]["event_type"] == "belief_created"
    assert explanation["source_belief"]["belief"]["claim_key"] == "system.load"
    assert len(explanation["source_belief"]["supporting_evidence"]) == 3


def test_query_cli_commands_do_not_write_events_or_rebuild_state(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    belief = conn.execute("SELECT * FROM belief_projection").fetchone()
    proposal = conn.execute("SELECT * FROM proposal_log").fetchone()
    before_events = integrity.snapshot_event_log(conn)
    before_projection = integrity.snapshot_projections(conn)

    runner = CliRunner()
    ask_result = runner.invoke(cli.main, ["ask", "was", "glaubst", "du"])
    explain_result = runner.invoke(cli.main, ["explain", "belief", str(belief["id"])])
    why_result = runner.invoke(cli.main, ["why", "proposal", str(proposal["id"])])

    assert ask_result.exit_code == 0
    assert explain_result.exit_code == 0
    assert why_result.exit_code == 0
    assert integrity.snapshot_event_log(conn) == before_events
    assert integrity.snapshot_projections(conn) == before_projection


def test_explain_belief_cli_shows_provenance(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    belief = conn.execute("SELECT * FROM belief_projection").fetchone()

    result = CliRunner().invoke(cli.main, ["explain", "belief", str(belief["id"])])

    assert result.exit_code == 0
    assert "BELIEF #" in result.output
    assert "supporting_evidence:" in result.output
    assert "transition_events:" in result.output
    assert "via observation" in result.output


def test_why_proposal_cli_shows_chain(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    proposal = conn.execute("SELECT * FROM proposal_log").fetchone()

    result = CliRunner().invoke(cli.main, ["why", "proposal", str(proposal["id"])])

    assert result.exit_code == 0
    assert "PROPOSAL #" in result.output
    assert "source_event:" in result.output
    assert "source_belief:" in result.output
