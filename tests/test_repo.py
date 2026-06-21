import json

from click.testing import CliRunner

from genus import cli, event_router, integrity, reactors, sensor


def _observe(conn, commits, measured_on="x1"):
    return reactors.observe_repo_reading(
        conn, sensor.repo_commits_reading(commits, measured_on)
    )


def _observe_churn(conn, lines, measured_on="x1"):
    return reactors.observe_repo_lines_reading(
        conn, sensor.repo_lines_reading(lines, measured_on)
    )


def test_repo_commits_creates_active_belief(conn):
    _observe(conn, 3)

    belief = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'repo.activity'"
    ).fetchone()
    assert belief is not None
    assert belief["claim_value"] == "active"
    assert belief["state"] == "active"
    assert belief["derivation"] == "rule:repo_activity_binary_v1"


def test_repo_zero_commits_is_observed_quiet(conn):
    # A real run that finds zero commits IS an observation of quiet (X1 on, no
    # work) — distinct from no run at all, which records nothing.
    _observe(conn, 3)
    _observe(conn, 0)

    active = conn.execute(
        "SELECT * FROM belief_projection "
        "WHERE claim_key = 'repo.activity' AND state = 'active'"
    ).fetchone()
    assert active["claim_value"] == "quiet"


def test_repo_observation_records_provenance(conn):
    _observe(conn, 2, measured_on="x1")

    row = conn.execute(
        "SELECT payload FROM event_log "
        "WHERE event_type = 'observation_created' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    payload = json.loads(row["payload"])

    assert payload["measured_on"] == "x1"
    assert payload["source"] == "git.commits_per_day"
    assert payload["metric_key"] == "repo.commits_per_day"
    # counts only — the contents are never carried
    assert payload["unit"] == "count"


def test_repo_observe_is_replay_stable_and_integrity_passes(conn):
    _observe(conn, 5)
    _observe(conn, 0)
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True


def test_observe_repo_cli(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)

    result = CliRunner().invoke(
        cli.main,
        ["observe-repo", "--commits-per-day", "4", "--measured-on", "x1"],
    )

    assert result.exit_code == 0
    belief = conn.execute(
        "SELECT * FROM belief_projection "
        "WHERE claim_key = 'repo.activity' AND state = 'active'"
    ).fetchone()
    assert belief["claim_value"] == "active"


def test_observe_repo_cli_rejects_negative(monkeypatch, cli_conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)

    result = CliRunner().invoke(
        cli.main,
        ["observe-repo", "--commits-per-day", "-1"],
    )

    assert result.exit_code != 0


def test_repo_churn_heavy_at_or_above_threshold(conn):
    _observe_churn(conn, 300)

    belief = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'repo.churn'"
    ).fetchone()
    assert belief["claim_value"] == "heavy"
    assert belief["derivation"] == "rule:repo_churn_binary_v1"


def test_repo_churn_light_below_threshold(conn):
    _observe_churn(conn, 50)

    belief = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'repo.churn'"
    ).fetchone()
    assert belief["claim_value"] == "light"


def test_repo_commits_threshold_default_unchanged(conn):
    # The configurable threshold defaults to 1.0, so commit activity behaves as
    # before: one commit is already "active".
    _observe(conn, 1)

    belief = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'repo.activity'"
    ).fetchone()
    assert belief["claim_value"] == "active"


def test_observe_repo_records_commits_and_churn(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)

    result = CliRunner().invoke(
        cli.main,
        [
            "observe-repo",
            "--commits-per-day", "4",
            "--lines-changed", "500",
            "--measured-on", "x1",
        ],
    )

    assert result.exit_code == 0
    activity = conn.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'repo.activity' AND state = 'active'"
    ).fetchone()
    churn = conn.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'repo.churn' AND state = 'active'"
    ).fetchone()
    assert activity["claim_value"] == "active"
    assert churn["claim_value"] == "heavy"


def test_repo_both_metrics_replay_stable(conn):
    _observe(conn, 4)
    _observe_churn(conn, 500)
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True
