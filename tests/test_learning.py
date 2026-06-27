import json
import sqlite3

from click.testing import CliRunner

from genus import cli, event_router, integrity, learning, reactors, sensor
from genus.db import init_schema

METRIC = "weather.temp_outside"


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _inject_reading(conn, value, created_at):
    # Inject an evidence reading with a controlled timestamp (the ledger sets
    # created_at itself, so the hourly model is tested via direct insert).
    payload = json.dumps(
        {"observation_id": 0, "metric_key": METRIC, "metric_value": value},
        sort_keys=True,
        separators=(",", ":"),
    )
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES ('evidence_recorded', ?, ?)",
        (payload, created_at),
    )
    conn.commit()


def _observe(conn, temp):
    return reactors.observe_weather_reading(conn, sensor.weather_reading(temp, "test"))


def test_forecast_value_learns_the_hourly_cycle():
    conn = _fresh()
    _inject_reading(conn, 10.0, "2026-06-25T08:00:00.000Z")
    _inject_reading(conn, 12.0, "2026-06-26T08:00:00.000Z")
    _inject_reading(conn, 20.0, "2026-06-25T14:00:00.000Z")

    value, support, method = learning.forecast_value(conn, METRIC, 8)
    assert value == 11.0  # mean of the two readings at hour 08
    assert support == 2
    assert method == "hourly_cycle_mean"
    conn.close()


def test_forecast_value_cold_start_falls_back_to_overall_mean():
    conn = _fresh()
    _inject_reading(conn, 10.0, "2026-06-25T08:00:00.000Z")
    value, _support, method = learning.forecast_value(conn, METRIC, 14)  # no hour-14 yet
    assert value == 10.0
    assert method == "overall_mean"
    conn.close()


def test_cycle_makes_and_scores_forecasts():
    conn = _fresh()
    _observe(conn, 10.0)  # first obs: forecasts, nothing to score
    _observe(conn, 11.0)  # scores the prior forecast, forecasts again
    _observe(conn, 12.0)

    made = conn.execute(
        "SELECT COUNT(*) AS c FROM event_log WHERE event_type = 'forecast_made'"
    ).fetchone()["c"]
    scored = conn.execute(
        "SELECT COUNT(*) AS c FROM event_log WHERE event_type = 'forecast_scored'"
    ).fetchone()["c"]
    assert made == 3
    assert scored == 2  # the first observation had no pending forecast

    report = learning.curve(conn)
    assert report["scored"] == 2
    assert report["mean_error"] is not None
    conn.close()


def test_forecast_events_pass_integrity_and_are_replay_stable():
    conn = _fresh()
    _observe(conn, 10.0)
    _observe(conn, 11.0)

    event_router.replay(conn)
    before = integrity.snapshot_projections(conn)
    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_learning_cli_runs(monkeypatch):
    conn = _fresh()
    _observe(conn, 10.0)
    _observe(conn, 11.0)

    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["learning"])

    assert result.exit_code == 0, result.output
    assert "scored forecasts" in result.output
