import sqlite3

from click.testing import CliRunner

from genus import cli, integrity, reactors, sensor, sources
from genus.db import init_schema

CLAIM = "weather.temp_outside"


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _observe(conn, temp):
    return reactors.observe_weather_reading(conn, sensor.mock_weather(temp))


def test_source_flows_from_observation_into_the_assertion_stream():
    conn = _fresh()
    _observe(conn, 18.0)
    stream = sources.assertions(conn, CLAIM)
    assert stream, "expected at least one assertion"
    assert all(row["source"] == "mock" for row in stream)
    assert stream[-1]["value"] == 18.0
    conn.close()


def test_lone_source_is_held_at_the_seed():
    conn = _fresh()
    for temp in (18.0, 19.0, 18.5):
        _observe(conn, temp)
    # only one source has spoken -> nothing to agree/disagree with -> unproven seed,
    # never a confident 1.0.
    assert sources.source_trust(conn, "mock") == sources.SOURCE_TRUST_SEED
    conn.close()


def test_threading_source_is_behaviour_preserving_and_replays_clean():
    conn = _fresh()
    for temp in (18.0, 18.0, 19.0):
        _observe(conn, temp)
    # integrity.check replays into a fresh db and compares projections: this proves the
    # belief lifecycle is unchanged by the added source provenance, and replay-stable.
    assert integrity.check(conn)["ok"] is True
    assert sources.assertions(conn, CLAIM)
    conn.close()


def _assert_source(conn, value, source):
    return reactors.observe_assertion(conn, CLAIM, value, source)


def test_two_agreeing_sources_earn_trust_with_no_contradiction():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)  # sensor source "mock"
    _assert_source(conn, 18.0, "provider-b")  # a second source, agreeing
    assert sources.source_trust(conn, "mock") == 1.0
    assert sources.source_trust(conn, "provider-b") == 1.0
    result = sources.consensus(conn, CLAIM)
    assert set(result["candidates"]) == {"mock", "provider-b"}
    assert result["contradiction"] is False
    conn.close()


def test_two_disagreeing_sources_lose_trust_and_flag_contradiction():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)
    _assert_source(conn, 30.0, "provider-b")  # far outside the claim's own spread
    assert sources.source_trust(conn, "mock") == 0.0
    assert sources.source_trust(conn, "provider-b") == 0.0
    result = sources.consensus(conn, CLAIM)
    assert result["contradiction"] is True
    conn.close()


def test_assertion_recorded_passes_integrity_and_replays_clean():
    conn = _fresh()
    _observe(conn, 18.0)
    _assert_source(conn, 18.0, "provider-b")
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_observe_assertion_cli_records_a_source(monkeypatch):
    conn = _fresh()
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(
        cli.main,
        ["observe-assertion", "--claim-key", CLAIM, "--value", "18.5", "--source", "wttr.in"],
    )
    # the command closes its own connection, so assert on its output, not the conn
    assert result.exit_code == 0, result.output
    assert "[ASR]" in result.output
    assert "wttr.in" in result.output


def test_sources_cli_runs(monkeypatch):
    conn = _fresh()
    for temp in (18.0, 18.0):
        _observe(conn, temp)
    _assert_source(conn, 18.0, "provider-b")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["sources"])
    assert result.exit_code == 0, result.output
    assert "trust" in result.output
    assert "provider-b" in result.output
