import json
import sqlite3

from click.testing import CliRunner

from genus import cli, event_router, integrity, reactors, rules, sensor
from genus.db import init_schema


def _observe(conn, commits, measured_on="x1"):
    return reactors.observe_repo_reading(
        conn, sensor.repo_commits_reading(commits, measured_on)
    )


def _observe_churn(conn, lines, measured_on="x1"):
    return reactors.observe_repo_lines_reading(
        conn, sensor.repo_lines_reading(lines, measured_on)
    )


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


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


def test_repo_churn_withholds_until_enough_history(conn):
    # During burn-in GENUS has no sense of its own "normal" yet, so it withholds
    # the heavy/light judgment entirely — no imposed default.
    for _ in range(rules.REPO_CHURN_MIN_SAMPLES):
        _observe_churn(conn, 50)

    belief = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'repo.churn'"
    ).fetchone()
    assert belief is None


def test_repo_churn_heavy_relative_to_own_history(conn):
    for _ in range(rules.REPO_CHURN_MIN_SAMPLES + 1):
        _observe_churn(conn, 20)   # establishes a small "normal"
    _observe_churn(conn, 500)      # well above this core's own distribution

    belief = conn.execute(
        "SELECT * FROM belief_projection "
        "WHERE claim_key = 'repo.churn' AND state = 'active'"
    ).fetchone()
    assert belief["claim_value"] == "heavy"
    assert belief["derivation"] == "rule:repo_churn_binary_v1"


def test_repo_churn_light_relative_to_own_history(conn):
    for _ in range(rules.REPO_CHURN_MIN_SAMPLES + 1):
        _observe_churn(conn, 800)  # establishes a large "normal"
    _observe_churn(conn, 100)      # small for this core

    belief = conn.execute(
        "SELECT * FROM belief_projection "
        "WHERE claim_key = 'repo.churn' AND state = 'active'"
    ).fetchone()
    assert belief["claim_value"] == "light"


def test_repo_churn_is_relative_not_absolute():
    # The killer test: the same value is heavy for one core and light for
    # another, decided only by each core's own lived history — proof that the
    # threshold is never an imposed constant.
    low = _fresh_conn()
    high = _fresh_conn()
    for _ in range(rules.REPO_CHURN_MIN_SAMPLES + 1):
        _observe_churn(low, 10)
        _observe_churn(high, 1000)
    _observe_churn(low, 100)   # huge for the low core
    _observe_churn(high, 100)  # tiny for the high core

    low_belief = low.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'repo.churn' AND state = 'active'"
    ).fetchone()
    high_belief = high.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'repo.churn' AND state = 'active'"
    ).fetchone()
    low.close()
    high.close()

    assert low_belief["claim_value"] == "heavy"
    assert high_belief["claim_value"] == "light"


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
    # Commits drive repo.activity immediately (presence is binary >= 1)...
    activity = conn.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'repo.activity' AND state = 'active'"
    ).fetchone()
    assert activity["claim_value"] == "active"
    # ...churn is recorded as evidence, but on a cold core the belief withholds
    # until there is enough lived history to know what is heavy.
    churn_evidence = conn.execute(
        "SELECT 1 FROM event_log WHERE event_type = 'evidence_recorded' "
        "AND json_extract(payload, '$.metric_key') = 'repo.lines_changed_per_day'"
    ).fetchone()
    assert churn_evidence is not None
    churn_belief = conn.execute(
        "SELECT 1 FROM belief_projection WHERE claim_key = 'repo.churn'"
    ).fetchone()
    assert churn_belief is None


def test_repo_both_metrics_replay_stable(conn):
    _observe(conn, 4)
    for _ in range(rules.REPO_CHURN_MIN_SAMPLES + 1):
        _observe_churn(conn, 50)
    _observe_churn(conn, 900)   # forms a heavy churn belief against own history
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True
