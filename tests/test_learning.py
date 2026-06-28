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
    # created_at itself, so the cycle model is tested via direct insert).
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


def _inject_scored(conn, predicted, actual):
    payload = json.dumps(
        {"forecast_event": 0, "metric_key": METRIC, "predicted_value": predicted,
         "actual_value": actual, "error": abs(predicted - actual)},
        sort_keys=True,
        separators=(",", ":"),
    )
    conn.execute(
        "INSERT INTO event_log (event_type, payload) VALUES ('forecast_scored', ?)",
        (payload,),
    )
    conn.commit()


def test_forecast_value_learns_the_hour_cycle():
    conn = _fresh()
    _inject_reading(conn, 10.0, "2026-06-25T08:00:00.000Z")
    _inject_reading(conn, 12.0, "2026-06-26T08:00:00.000Z")
    _inject_reading(conn, 20.0, "2026-06-25T14:00:00.000Z")

    value, support, method = learning.forecast_value(conn, METRIC, "hour", 8)
    assert value == 11.0  # mean of the two readings in hour 08
    assert support == 2
    assert method == "hour_cycle_mean"
    conn.close()


def test_forecast_value_learns_the_weekday_cycle():
    conn = _fresh()
    _inject_reading(conn, 5.0, "2026-06-22T09:00:00.000Z")  # Monday
    _inject_reading(conn, 7.0, "2026-06-29T09:00:00.000Z")  # Monday
    _inject_reading(conn, 50.0, "2026-06-27T09:00:00.000Z")  # Saturday

    value, support, method = learning.forecast_value(conn, METRIC, "weekday", 0)  # Monday
    assert value == 6.0  # mean of the two Mondays
    assert support == 2
    assert method == "weekday_cycle_mean"
    conn.close()


def test_forecast_value_cold_start_falls_back_to_overall_mean():
    conn = _fresh()
    _inject_reading(conn, 10.0, "2026-06-25T08:00:00.000Z")
    value, _support, method = learning.forecast_value(conn, METRIC, "hour", 14)
    assert value == 10.0
    assert method == "overall_mean"
    conn.close()


def test_cycle_makes_and_scores_forecasts_after_warmup():
    conn = _fresh()
    _observe(conn, 10.0)  # 1 reading: below MIN_HISTORY, no forecast yet
    _observe(conn, 11.0)  # 2 readings: forecasts, nothing to score
    _observe(conn, 12.0)  # scores the prior forecast, forecasts again
    _observe(conn, 13.0)

    made = conn.execute(
        "SELECT COUNT(*) AS c FROM event_log WHERE event_type = 'forecast_made'"
    ).fetchone()["c"]
    scored = conn.execute(
        "SELECT COUNT(*) AS c FROM event_log WHERE event_type = 'forecast_scored'"
    ).fetchone()["c"]
    assert made == 3
    assert scored == 2

    report = learning.curve(conn, METRIC)
    assert report["scored"] == 2
    assert report["mean_error"] is not None
    assert "skill" in report
    conn.close()


def test_curve_skill_rewards_beating_naive():
    conn = _fresh()
    # actuals vary widely (10, 20) and the model predicts them exactly (error 0); a
    # naive "guess the mean (15)" would be off by 5 each -> skill = 1 - 0/5 = 1.0.
    _inject_scored(conn, predicted=10.0, actual=10.0)
    _inject_scored(conn, predicted=20.0, actual=20.0)
    assert learning.curve(conn, METRIC)["skill"] == 1.0
    conn.close()


def test_curve_skill_is_zero_when_signal_is_too_flat_to_learn():
    conn = _fresh()
    # a near-constant signal: the model's error equals the naive error -> skill 0,
    # i.e. "nothing to learn" -- not mistaken for "improving".
    _inject_scored(conn, predicted=10.0, actual=10.1)
    _inject_scored(conn, predicted=10.0, actual=9.9)
    assert learning.curve(conn, METRIC)["skill"] == 0.0
    conn.close()


def test_forecast_events_pass_integrity_and_are_replay_stable():
    conn = _fresh()
    _observe(conn, 10.0)
    _observe(conn, 11.0)
    _observe(conn, 12.0)

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
    _observe(conn, 12.0)

    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["learning"])

    assert result.exit_code == 0, result.output
    assert "weather.temp_outside" in result.output
