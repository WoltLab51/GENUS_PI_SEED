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


def _busy_idle_baseline(
    conn, ticks, busy_cpu=70.0, idle_cpu=0.0, hot_temp=58.0, cool_temp=46.0
):
    # Establish a CPU distribution WITH spread (busy and idle regimes) plus a
    # matching temperature spread, so the correlation has a premise to judge.
    for i in range(ticks):
        if i % 2 == 0:
            _tick(conn, busy_cpu, hot_temp)
        else:
            _tick(conn, idle_cpu, cool_temp)


def _thermal(conn):
    return conn.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'system.thermal' AND state = 'active'"
    ).fetchone()


def test_thermal_withholds_until_enough_history(conn):
    # Fewer than min_samples ticks (even with real CPU spread) -> no judgment.
    _busy_idle_baseline(conn, rules.THERMAL_MIN_SAMPLES - 1)

    assert conn.execute(
        "SELECT 1 FROM belief_projection WHERE claim_key = 'system.thermal'"
    ).fetchone() is None


def test_thermal_withholds_when_cpu_has_no_spread(conn):
    # The premise-of-meaning guard: an always-idle CPU has no high regime to be
    # decoupled from, so the correlation withholds however the temperature
    # wanders. This is exactly the idle-Pi case the live burn-in revealed.
    for _ in range(rules.THERMAL_MIN_SAMPLES + 4):
        _tick(conn, 0.0, 50.0)
    _tick(conn, 0.0, 90.0)   # hot, but the CPU never varies -> no verdict

    assert conn.execute(
        "SELECT 1 FROM belief_projection WHERE claim_key = 'system.thermal'"
    ).fetchone() is None


def test_thermal_anomalous_when_temp_high_and_cpu_not(conn):
    _busy_idle_baseline(conn, rules.THERMAL_MIN_SAMPLES + 1)
    _tick(conn, 0.0, 70.0)   # hot while the CPU is idle -> anomaly

    belief = _thermal(conn)
    assert belief["claim_value"] == rules.THERMAL_ANOMALOUS


def test_thermal_normal_when_both_high(conn):
    _busy_idle_baseline(conn, rules.THERMAL_MIN_SAMPLES + 1)
    _tick(conn, 90.0, 70.0)  # hot AND busy -> expected, normal

    belief = _thermal(conn)
    assert belief["claim_value"] == rules.THERMAL_NORMAL


def test_thermal_high_is_relative_to_each_core():
    # Both cores have CPU spread; the same 60C reading is an anomaly for the
    # normally-cool core and normal for the normally-hot one.
    cool = _fresh_conn()
    hot = _fresh_conn()
    _busy_idle_baseline(cool, rules.THERMAL_MIN_SAMPLES + 1, hot_temp=40.0, cool_temp=35.0)
    _busy_idle_baseline(hot, rules.THERMAL_MIN_SAMPLES + 1, hot_temp=92.0, cool_temp=85.0)
    _tick(cool, 0.0, 60.0)
    _tick(hot, 0.0, 60.0)

    cool_belief = _thermal(cool)
    hot_belief = _thermal(hot)
    cool.close()
    hot.close()

    assert cool_belief["claim_value"] == rules.THERMAL_ANOMALOUS
    assert hot_belief["claim_value"] == rules.THERMAL_NORMAL


def test_thermal_correlation_is_replay_stable(conn):
    _busy_idle_baseline(conn, rules.THERMAL_MIN_SAMPLES + 1)
    _tick(conn, 0.0, 70.0)
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True
