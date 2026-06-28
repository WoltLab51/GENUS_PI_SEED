import sqlite3

from genus import integrity, reactors, sensor, sources
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
