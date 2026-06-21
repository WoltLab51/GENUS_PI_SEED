import sqlite3

from genus import event_router, integrity, rules
from genus.db import init_schema
from tests.conftest import observe_cpu_value, observe_temperature_value


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _tick(conn, cpu, temp):
    # One observe-all-like tick: CPU first, then temperature (which triggers the
    # cross-metric correlation against the just-recorded CPU).
    observe_cpu_value(conn, cpu)
    observe_temperature_value(conn, temp)


def _thermal(conn):
    return conn.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'system.thermal' AND state = 'active'"
    ).fetchone()


def test_thermal_withholds_until_enough_history(conn):
    for _ in range(rules.THERMAL_MIN_SAMPLES - 1):
        _tick(conn, 50.0, 50.0)

    assert conn.execute(
        "SELECT 1 FROM belief_projection WHERE claim_key = 'system.thermal'"
    ).fetchone() is None


def test_thermal_anomalous_when_temp_high_and_cpu_not(conn):
    for _ in range(rules.THERMAL_MIN_SAMPLES + 1):
        _tick(conn, 50.0, 50.0)   # establishes a "normal" for both
    _tick(conn, 10.0, 90.0)       # hot while the CPU is idle -> anomaly

    belief = _thermal(conn)
    assert belief["claim_value"] == rules.THERMAL_ANOMALOUS


def test_thermal_normal_when_both_high(conn):
    for _ in range(rules.THERMAL_MIN_SAMPLES + 1):
        _tick(conn, 50.0, 50.0)
    _tick(conn, 90.0, 90.0)       # hot but the CPU is busy too -> expected

    belief = _thermal(conn)
    assert belief["claim_value"] == rules.THERMAL_NORMAL


def test_thermal_high_is_relative_to_each_core():
    # The same 80C reading is an anomaly for a normally-cool core and normal for
    # a normally-hot one — "high" is each core's own percentile, never preset.
    cool = _fresh_conn()
    hot = _fresh_conn()
    for _ in range(rules.THERMAL_MIN_SAMPLES + 1):
        _tick(cool, 40.0, 40.0)   # this core normally runs cool
        _tick(hot, 40.0, 90.0)    # this core normally runs hot
    _tick(cool, 10.0, 80.0)
    _tick(hot, 10.0, 80.0)

    cool_belief = _thermal(cool)
    hot_belief = _thermal(hot)
    cool.close()
    hot.close()

    assert cool_belief["claim_value"] == rules.THERMAL_ANOMALOUS
    assert hot_belief["claim_value"] == rules.THERMAL_NORMAL


def test_thermal_correlation_is_replay_stable(conn):
    for _ in range(rules.THERMAL_MIN_SAMPLES + 1):
        _tick(conn, 50.0, 50.0)
    _tick(conn, 10.0, 90.0)
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True
