import json
import sqlite3

from click.testing import CliRunner

from genus import cli, event_router, integrity, rules
from genus.db import init_schema
from tests.conftest import observe_weather_value


def _observe_weather_series(conn, values):
    for value in values:
        observe_weather_value(conn, value)


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_weather_trend_rising(conn):
    _observe_weather_series(conn, [10.0 + i for i in range(rules.TREND_WINDOW)])

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'weather.trend'"
    ).fetchone()
    assert row["claim_value"] == rules.TREND_RISING
    assert row["state"] == "active"
    assert row["derivation"] == rules.WEATHER_TREND_DERIVATION


def test_weather_trend_falling(conn):
    _observe_weather_series(conn, [33.0 - i for i in range(rules.TREND_WINDOW)])

    row = conn.execute(
        "SELECT * FROM belief_projection "
        "WHERE claim_key = 'weather.trend' AND state = 'active'"
    ).fetchone()
    assert row["claim_value"] == rules.TREND_FALLING


def test_weather_trend_stable_within_own_scatter(conn):
    _observe_weather_series(conn, [20.0] * rules.TREND_WINDOW)

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'weather.trend'"
    ).fetchone()
    assert row["claim_value"] == rules.TREND_STABLE


def test_weather_trend_needs_full_window(conn):
    _observe_weather_series(conn, [10.0 + i for i in range(rules.TREND_WINDOW - 1)])

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'weather.trend'"
    ).fetchone()
    assert row is None


def test_weather_daily_swing_is_filtered_by_own_scatter():
    # A real day oscillates (warm afternoon, cool night). With self-calibrated
    # sensitivity the daily swing reads as stable, while a steady multi-day climb
    # of the same magnitude reads as rising — the same epsilon-from-own-scatter
    # logic that disk.trend uses, now on external material.
    swing = _fresh_conn()
    climb = _fresh_conn()
    # A full daily cycle: warm up, then cool back to the morning baseline. Over a
    # 24h window the last reading lands back near the first, so the net is ~0.
    half = rules.TREND_WINDOW // 2
    daily_cycle = [12.0 + i for i in range(half)] + [
        12.0 + (half - 1) - i for i in range(half)
    ]
    _observe_weather_series(swing, daily_cycle)
    _observe_weather_series(climb, [12.0 + i for i in range(rules.TREND_WINDOW)])

    swing_belief = swing.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'weather.trend' AND state = 'active'"
    ).fetchone()
    climb_belief = climb.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'weather.trend' AND state = 'active'"
    ).fetchone()
    swing.close()
    climb.close()

    assert swing_belief["claim_value"] == rules.TREND_STABLE
    assert climb_belief["claim_value"] == rules.TREND_RISING


def test_weather_observation_keeps_location_out_of_the_ledger(conn):
    observe_weather_value(conn, 22.5)

    payloads = [
        json.loads(row["payload"])
        for row in conn.execute(
            "SELECT payload FROM event_log ORDER BY id"
        ).fetchall()
    ]
    blob = json.dumps(payloads)
    for forbidden in ("lat", "lon", "latitude", "longitude"):
        assert forbidden not in blob


def test_weather_trend_is_replay_stable_and_integrity_passes(conn):
    _observe_weather_series(conn, [10.0 + i for i in range(rules.TREND_WINDOW)])
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True


def test_observe_weather_cli_writes_two_base_events(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)

    result = CliRunner().invoke(
        cli.main,
        ["observe-weather", "--temp-outside", "22.5", "--source", "open-meteo"],
    )

    assert result.exit_code == 0
    rows = conn.execute("SELECT event_type FROM event_log ORDER BY id").fetchall()
    # a single observation has too little history to forecast (MIN_HISTORY); the
    # 24/7 learning loop starts once a metric has two readings.
    assert [row["event_type"] for row in rows] == [
        "observation_created",
        "evidence_recorded",
    ]
    observation = json.loads(
        conn.execute(
            "SELECT payload FROM event_log WHERE event_type = 'observation_created'"
        ).fetchone()["payload"]
    )
    assert observation["metric_key"] == rules.WEATHER_TEMP_METRIC_KEY
    assert observation["provider"] == "open-meteo"
